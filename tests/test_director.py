import json, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG, Isolated  # noqa: E402
from minis_core import director as D  # noqa: E402
from minis_core.sources import Activity  # noqa: E402


def act(sid, state='idle', last=0.0, ch=None):
    return Activity(sid, sid.title(), ch or sid, state, last_active=last)


def make(**over):
    return D.Director(dict(CFG, **over), resolve=lambda c: c)


NOBOT = dict(sparring_bot=False)


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
        d = make(dormant_hours=0, **NOBOT)                           # no dormant memory: the V3 rule on its own
        d.step([act('claude', last=999), act('cursor', last=998)], 1000)
        self.assertEqual(d.step([act('claude', last=999)], 1002)['b'], 'cursor')   # one bad poll
        self.assertEqual(d.step([act('claude', last=999), act('cursor', last=998)], 1004)['b'], 'cursor')
        d.step([act('claude', last=999)], 1006)
        self.assertIsNone(d.step([act('claude', last=999)], 1013)['b'])     # gone for > 6 s: slot freed

    def test_empty_slot_is_refilled_and_nothing_means_nothing(self):
        d = make(**NOBOT)
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
        cfg = dict(CFG, **NOBOT)
        r = D.Runner(cfg, src, D.Director(cfg, resolve=lambda c: c))
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


class DormantPartner(unittest.TestCase):
    """V5.1: the most recently used other program keeps its slot, asleep, after its detector stops reporting it."""

    def test_vanished_source_keeps_its_slot_as_dormant_until_dormant_hours(self):
        d = make(**NOBOT)
        d.step([act('claude', last=999), act('codex', last=990)], 1000)
        for t in (1010, 1100, 1000 + 23 * 3600):                      # codex gone (session file aged out): still slot b
            self.assertEqual(d.step([act('claude', 'working', last=t)], t), {'a': 'claude', 'b': 'codex'})
            self.assertTrue(d.dormant['b'])
        out = d.assignment(1000 + 23 * 3600)
        self.assertEqual(out['b'], {'source': 'codex', 'character': 'codex', 'program': 'Codex', 'dormant': True})
        self.assertNotIn('dormant', out['a'])
        t = 990 + 24 * 3600 + 1                                     # 24 h after its last activity: let go (after the grace)
        d.step([act('claude', last=t)], t)
        got = d.step([act('claude', last=t)], t + CFG['director_grace_s'] + 1)
        self.assertEqual(got, {'a': 'claude', 'b': None})

    def test_dormant_partner_comes_back_live_without_a_change_of_slot(self):
        d = make(**NOBOT)
        d.step([act('claude', last=999), act('codex', last=990)], 1000)
        d.step([act('claude', last=999)], 1100)
        self.assertTrue(d.dormant['b'])
        d.step([act('claude', last=999), act('codex', 'working', last=1200)], 1200)
        self.assertEqual(d.slots, {'a': 'claude', 'b': 'codex'})
        self.assertFalse(d.dormant['b'])

    def test_only_an_active_program_replaces_the_dormant_partner(self):
        d = make(**NOBOT)
        d.step([act('claude', last=999), act('codex', last=990)], 1000)
        d.step([act('claude', last=999)], 1100)                                      # codex dormant
        got = d.step([act('claude', last=999), act('cursor', last=0.0)], 1200)       # cursor running, never active: no
        self.assertEqual(got, {'a': 'claude', 'b': 'codex'})
        got = d.step([act('claude', last=999), act('cursor', 'working', last=1300)], 1300)   # cursor active: yes
        self.assertEqual(got, {'a': 'claude', 'b': 'cursor'})
        self.assertFalse(d.dormant['b'])

    def test_the_most_recently_active_vanished_program_is_the_one_kept(self):
        d = make(**NOBOT)
        d.step([act('claude', 'working', last=1000), act('cursor', last=900)], 1000)
        d.step([act('claude', 'working', last=1000), act('gemini', 'working', last=1100)], 1100)     # cursor gone, gemini in
        self.assertEqual(d.slots, {'a': 'claude', 'b': 'gemini'})
        got = d.step([act('claude', 'working', last=1300)], 1300)                                 # gemini gone too
        self.assertEqual(got, {'a': 'claude', 'b': 'gemini'})                                    # not cursor: gemini is newer

    def test_never_active_programs_are_not_remembered(self):
        d = make(**NOBOT)
        d.step([act('claude', last=999), act('cursor', last=0.0)], 1000)                         # cursor idle from the start
        self.assertEqual(d.slots['b'], 'cursor')
        d.step([act('claude', last=999)], 1002)                                                  # cursor closed
        got = d.step([act('claude', last=999)], 1002 + CFG['director_grace_s'] + 1)
        self.assertEqual(got, {'a': 'claude', 'b': None})                                        # freed, not kept asleep

    def test_restored_memory_fills_the_empty_slot_at_startup(self):
        seen = {'codex': {'last_active': 3600.0, 'character': 'codex', 'program': 'Codex'},
                'cursor': {'last_active': 100.0, 'character': 'cursor', 'program': 'Cursor'},
                'junk': 'not a record', 'sparring': {'last_active': 5000.0}}
        d = D.Director(dict(CFG, **NOBOT), resolve=lambda c: c, seen=seen)
        got = d.step([act('claude', 'working', last=5000)], 5000)
        self.assertEqual(got, {'a': 'claude', 'b': 'codex'})
        self.assertEqual(d.assignment(5000)['b']['program'], 'Codex')


class SparringBot(unittest.TestCase):
    def test_a_lone_fighter_gets_the_bot_and_the_bot_yields_to_anything_real(self):
        d = make()
        self.assertEqual(d.step([act('claude', last=999)], 1000), {'a': 'claude', 'b': 'sparring'})
        self.assertEqual(d.assignment(1000)['b'], {'source': 'sparring', 'character': 'generic', 'program': 'Sparring bot', 'bot': True})
        self.assertEqual(d.step([act('claude', last=999), act('cursor', last=0.0)], 1002), {'a': 'claude', 'b': 'cursor'})   # idle is enough
        self.assertEqual(d.step([act('claude', last=999)], 1004), {'a': 'claude', 'b': 'cursor'})                         # grace ...
        self.assertEqual(d.step([act('claude', last=999)], 1020), {'a': 'claude', 'b': 'sparring'})                       # ... then the bot again

    def test_bot_takes_the_empty_side_only(self):
        d = make()
        d.step([act('claude', last=999), act('codex', last=1000)], 1000)
        self.assertEqual(d.slots, {'a': 'codex', 'b': 'claude'})
        d.step([act('claude', last=999)], 1000 + 25 * 3600)                                   # codex aged out of dormancy too
        got = d.step([act('claude', last=999)], 1000 + 25 * 3600 + 10)
        self.assertEqual(got, {'a': 'sparring', 'b': 'claude'})

    def test_no_programs_means_no_bot_and_a_dormant_partner_beats_the_bot(self):
        d = make()
        self.assertEqual(d.step([], 1000), {'a': None, 'b': None})
        d.step([act('claude', last=999), act('codex', last=990)], 1000)
        self.assertEqual(d.step([act('claude', last=999)], 1100), {'a': 'claude', 'b': 'codex'})

    def test_bot_can_be_switched_off(self):
        d = make(**NOBOT)
        self.assertEqual(d.step([act('claude', last=999)], 1000), {'a': 'claude', 'b': None})


class Seen(Isolated):
    def test_runner_persists_what_it_saw_and_a_new_director_starts_from_it(self):
        class Src:
            acts = [act('claude', 'working', last=1000), act('codex', last=900)]

            def poll(self, now):
                return self.acts
        src = Src()
        r = D.Runner(dict(CFG, **NOBOT), src)
        r.step(1000.0)
        seen = D.read_seen()
        self.assertEqual(seen['codex'], {'last_active': 900.0, 'character': 'codex', 'program': 'Codex'})
        self.assertEqual(seen['claude']['last_active'], 1000.0)
        src.acts = [act('claude', 'working', last=1010)]
        r.step(1010.0)
        self.assertEqual(D.read_seen()['claude']['last_active'], 1000.0)             # throttled: at most every 30 s
        r.step(1031.0)
        self.assertEqual(D.read_seen()['claude']['last_active'], 1031.0)
        r2 = D.Runner(dict(CFG, **NOBOT), src)                                        # a restarted director remembers codex
        data, _ = r2.step(1040.0)
        self.assertEqual((data['b']['source'], data['b'].get('dormant')), ('codex', True))
        self.assertEqual([p.name for p in self.data.iterdir() if p.name.endswith('.tmp')], [])

    def test_seen_tolerates_missing_and_corrupt(self):
        self.assertEqual(D.read_seen(), {})
        (self.data / 'seen.json').write_text('{oops', encoding='utf-8')
        self.assertEqual(D.read_seen(), {})
        (self.data / 'seen.json').write_text('[1, 2]', encoding='utf-8')
        self.assertEqual(D.read_seen(), {})


if __name__ == '__main__':
    unittest.main()
