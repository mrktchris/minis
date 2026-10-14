import json, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG, Isolated  # noqa: E402
from minis_core import director as D  # noqa: E402
from minis_core.sources import Activity  # noqa: E402


def act(sid, state='idle', last=0.0, ch=None):
    return Activity(sid, sid.title(), ch or sid, state, last_active=last)


def make():
    return D.Director(CFG, resolve=lambda c: c)


class Assignment(unittest.TestCase):
    def test_two_most_recent_get_slots_the_third_waits(self):
        d = make()
        got = d.step([act('claude', last=900), act('codex', last=990), act('cursor', last=950)], 1000)
        self.assertEqual(got, {'a': 'codex', 'b': 'cursor'})

    def test_working_counts_as_active_now(self):
        d = make()
        got = d.step([act('claude', 'working', last=10), act('codex', last=990), act('cursor', last=980)], 1000)
        self.assertEqual(set(got.values()), {'claude', 'codex'})

    def test_slot_is_kept_while_its_source_was_active_within_60s(self):
        d = make()
        d.step([act('claude', last=999), act('codex', last=998)], 1000)
        got = d.step([act('claude', last=999), act('codex', last=998), act('cursor', 'working', last=1030)], 1030)
        self.assertEqual(got, {'a': 'claude', 'b': 'codex'})            # both idle for only ~31 s

    def test_idle_slot_is_handed_to_an_active_newcomer(self):
        d = make()
        d.step([act('claude', last=999), act('codex', last=998)], 1000)
        got = d.step([act('claude', last=1050), act('codex', last=998), act('cursor', 'working', last=1080)], 1080)
        self.assertEqual(got, {'a': 'claude', 'b': 'cursor'})           # codex idle 82 s > 60 s; claude only 30 s

    def test_the_longest_idle_slot_is_replaced_first(self):
        d = make()
        d.step([act('claude', last=999), act('codex', last=998)], 1000)
        got = d.step([act('claude', last=900), act('codex', last=990), act('cursor', 'working', last=1100)], 1100)
        self.assertEqual(got['a'], 'cursor')                             # claude idle 200 s, codex 110 s
        self.assertEqual(got['b'], 'codex')

    def test_an_idle_newcomer_does_not_displace_anyone(self):
        d = make()
        d.step([act('claude', last=100), act('codex', last=100)], 1000)
        got = d.step([act('claude', last=100), act('codex', last=100), act('cursor', last=0.0)], 2000)
        self.assertEqual(got, {'a': 'claude', 'b': 'codex'})

    def test_waiting_is_not_idle(self):
        d = make()
        d.step([act('claude', 'waiting', last=10), act('codex', last=990)], 1000)
        got = d.step([act('claude', 'waiting', last=10), act('codex', last=990), act('cursor', 'working', last=1500)], 1500)
        self.assertEqual(got['a'], 'claude')                            # an approval prompt keeps its fighter

    def test_a_brief_disappearance_keeps_the_slot(self):
        d = make()
        d.step([act('claude', last=999), act('cursor', last=998)], 1000)
        self.assertEqual(d.step([act('claude', last=999)], 1002)['b'], 'cursor')   # one bad poll
        self.assertEqual(d.step([act('claude', last=999), act('cursor', last=998)], 1004)['b'], 'cursor')
        d.step([act('claude', last=999)], 1006)
        self.assertIsNone(d.step([act('claude', last=999)], 1013)['b'])     # gone for > 6 s: slot freed

    def test_empty_slot_is_refilled_and_nothing_means_nothing(self):
        d = make()
        self.assertEqual(d.step([], 1000), {'a': None, 'b': None})
        self.assertEqual(d.step([act('ollama', last=990)], 1002), {'a': 'ollama', 'b': None})

    def test_assignment_resolves_characters(self):
        d = D.Director(CFG, resolve=lambda c: c if c in ('claude', 'generic') else 'generic')
        d.step([act('claude', last=999), act('aider', last=998, ch='generic'), act('mystery', last=1, ch='mystery')], 1000)
        out = d.assignment(1000)
        self.assertEqual(out['a'], {'source': 'claude', 'character': 'claude', 'program': 'Claude'})
        self.assertEqual(out['b'], {'source': 'aider', 'character': 'generic', 'program': 'Aider'})
        self.assertEqual(out['ts'], 1000)


class Files(Isolated):
    def test_runner_writes_assign_json_atomically_on_change_and_as_heartbeat(self):
        class Src:
            acts = [act('claude', last=999)]

            def poll(self, now):
                return self.acts
        src = Src()
        r = D.Runner(CFG, src, D.Director(CFG, resolve=lambda c: c))
        r.step(1000.0)
        data = json.loads((self.data / 'assign.json').read_text(encoding='utf-8'))
        self.assertEqual((data['a']['source'], data['b'], data['ts']), ('claude', None, 1000.0))
        r.step(1002.0)
        self.assertEqual(D.read_assign()['ts'], 1000.0)                 # unchanged: not rewritten
        src.acts = [act('claude', last=999), act('codex', last=1003)]
        r.step(1004.0)
        self.assertEqual(D.read_assign()['b']['source'], 'codex')
        r.step(1015.0)
        self.assertEqual(D.read_assign()['ts'], 1015.0)                 # heartbeat every 10 s
        self.assertEqual([p.name for p in self.data.iterdir() if p.name.endswith('.tmp')], [])

    def test_reading_tolerates_missing_corrupt_and_malformed(self):
        self.assertIsNone(D.read_assign())
        (self.data / 'assign.json').write_text('{oops', encoding='utf-8')
        self.assertIsNone(D.read_assign())
        bad = {'a': {'source': 5}, 'b': 'claude', 'ts': 1}
        self.assertIsNone(D.slot_assignment(bad, 'a'))
        self.assertIsNone(D.slot_assignment(bad, 'b'))
        self.assertIsNone(D.slot_assignment(None, 'a'))
        good = {'a': {'source': 'codex', 'character': 'codex', 'program': 'Codex'}}
        self.assertEqual(D.slot_assignment(good, 'a')['character'], 'codex')


if __name__ == '__main__':
    unittest.main()
