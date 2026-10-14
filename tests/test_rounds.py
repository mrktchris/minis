"""Rounds, HP, winners and record.json (docs/V4-WORKORDER.md "Rounds and winners")."""
import collections, json, os, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG, Isolated  # noqa: E402
from minis_core import rounds, sim, fx, control  # noqa: E402
from minis_core.atlas import Library  # noqa: E402
from minis_core.brain import LEFT, RIGHT, Brain, make_timeline  # noqa: E402

LIB = Library()
ATL = {c: LIB[c] for c in ('claude', 'codex', 'gemini', 'cursor')}


def plan(seed=5, mode='decided', scores=None, chars=('claude', 'codex')):
    return dict(kind='match', left='a', right='b', pos={'a': 500.0, 'b': 524.0}, t0=1000.0, seed=seed, chars={'a': chars[0], 'b': chars[1]},
                mode=mode, scores=scores or {'a': 100.0, 'b': 100.0}, id='t:1', deadline=1003.0)


class Math(unittest.TestCase):
    def test_health_score_formula(self):
        self.assertEqual(rounds.health_score('idle', 30.0), 70 + 20)
        self.assertEqual(rounds.health_score('working', 30.0), 70 + 20 + 10)
        self.assertEqual(rounds.health_score('limit', 95.0), 5)
        self.assertEqual(rounds.health_score('idle', None), 50 + 20)               # unknown context counts as 50 %
        self.assertEqual(rounds.score_of_bus({'state': 'working', 'ctx': 40.0}), 60 + 20 + 10)
        self.assertEqual(rounds.score_of_bus(None), 70)

    def test_damage_table(self):
        a = ATL['claude']
        self.assertEqual(rounds.damage_of(a, 'jab'), 12)
        self.assertEqual(rounds.damage_of(a, 'cross'), 24)
        self.assertEqual(rounds.damage_of(a, 'roundhouse'), 36)
        self.assertEqual(rounds.damage_of(a, a.ultimate()), 40)                   # the ultimate (or the super until the art lands)
        sig = a.signature()
        self.assertEqual(a.ultimate(), sig['ultimate'] or sig['super'])
        legacy = Library()['codex']
        legacy.meta['signature'] = {'strike': 'jab', 'special': 'deploy', 'super': 'sudo'}
        self.assertEqual(legacy.ultimate(), 'sudo')                            # no ultimate in the atlas: the super stands in

    def test_attacker_probability(self):
        self.assertEqual(rounds.p_left('random', {'a': 130, 'b': 10}, 'a', 'b'), 0.5)
        self.assertEqual(rounds.p_left('decided', {'a': 60, 'b': 60}, 'a', 'b'), 0.5)        # a tie is a coin flip
        self.assertAlmostEqual(rounds.p_left('decided', {'a': 90, 'b': 30}, 'a', 'b'), 0.75)


class Timeline(unittest.TestCase):
    def test_best_of_three_hp_and_caps(self):
        tl, t_end, s = rounds.make_match(plan(), ATL, fx.default())
        self.assertEqual(max(s['wins'].values()), 2)
        self.assertIn(len(s['rounds']), (2, 3))
        self.assertLess(t_end - 1000.0, 3 * (rounds.ROUND_CAP_S + 8) + 10)
        for r in s['rounds']:
            self.assertLessEqual(r['t1'] - r['t0'], rounds.ROUND_CAP_S + 2.0)
            if r['ko']:
                self.assertEqual(min(r['hp'].values()), 0)
            self.assertEqual(sorted(r['hp'].values()), sorted(r['hp'].values()))
        trace = rounds.hp_trace(tl)
        self.assertEqual(trace[0][1], {'a': 100, 'b': 100})
        for (t0, h0), (t1, h1) in zip(trace, trace[1:]):
            self.assertLessEqual(t0, t1)
            for w in 'ab':
                self.assertTrue(0 <= h1[w] <= 100)
        # damage never exceeds the table: every drop is 12 / 24 / 36 / 40, or the remainder down to 0 on a KO
        drops = collections.Counter()
        for (t0, h0), (t1, h1) in zip(trace, trace[1:]):
            for w in 'ab':
                d = h0[w] - h1[w]
                if d > 0:
                    drops[d] += 1
                    self.assertTrue(d in (12, 24, 36, 40) or (h1[w] == 0 and d <= 40) or d == 100, (d, h0, h1))
        self.assertTrue(any(d in (12, 24, 36) for d in drops), drops)

    def test_same_plan_same_timeline_different_seed_differs(self):
        a, _, sa = rounds.make_match(plan(seed=9), ATL, fx.default())
        b, _, sb = rounds.make_match(plan(seed=9), ATL, fx.default())
        c, _, sc = rounds.make_match(plan(seed=10), ATL, fx.default())
        self.assertEqual(a, b)
        self.assertEqual(sa, sb)
        self.assertNotEqual(a, c)

    def test_decided_mode_is_biased_random_is_not(self):
        wins = collections.Counter()
        for seed in range(120):
            wins[rounds.make_match(plan(seed, 'decided', {'a': 130.0, 'b': 40.0}), ATL)[2]['winner']] += 1
        self.assertGreater(wins['a'], 95, wins)
        even = collections.Counter()
        for seed in range(120):
            even[rounds.make_match(plan(seed, 'random', {'a': 130.0, 'b': 40.0}), ATL)[2]['winner']] += 1
        self.assertGreater(even['b'], 35, even)
        self.assertGreater(even['a'], 35, even)

    def test_directives_and_texts(self):
        tl, t_end, s = rounds.make_match(plan(), ATL, fx.default())
        names = {n for w in tl for t, n, o in tl[w] if n.startswith('@')}
        self.assertEqual(names, {'@hp', '@fx', '@banner', '@record'})
        banners = [o['banner'] for t, n, o in tl['a'] if n == '@banner']
        self.assertEqual(banners[:2], ['round1', 'fight'])
        self.assertIn('ko', banners)
        self.assertEqual(banners[-1], 'winner')
        self.assertFalse(any(n in ('@banner', '@record') for t, n, o in tl['b']))      # the left side owns texts + record
        rec = [o for t, n, o in tl['a'] if n == '@record'][0]
        self.assertEqual((rec['winner'], rec['loser']), (s['winner'], s['loser']))
        self.assertEqual(rec['chars'], {'a': 'claude', 'b': 'codex'})
        ults = [o for w in tl for t, n, o in tl[w] if n == '@fx' and o.get('kind') == 'ultimate']
        allowed = {n for a in (ATL['claude'], ATL['codex']) for _, n, _ in a.move_fx(a.ultimate())}
        self.assertTrue(ults and all(o['fx'] in allowed for o in ults), (ults, allowed))

    def test_every_roster_pair_can_play_a_match(self):
        from minis_core.atlas import available
        chars = available()
        for i, c1 in enumerate(chars):
            for c2 in chars[i:]:
                lib = {c1: LIB[c1], c2: LIB[c2]}
                tl, t_end, s = rounds.make_match(plan(3, chars=(c1, c2)), lib, fx.default())
                self.assertIn(s['winner'], ('a', 'b'), (c1, c2))


class TwoBrains(unittest.TestCase):
    """Two Brains (as in two processes) agree on HP and the winner; only the left side records."""

    def run_match(self, seed=4, mode='decided', secs=90, states=('working', 'idle'), ctx=(41.0, 70.0)):
        rec = []
        cfg = dict(CFG, bout_min_s=999, bout_max_s=999, clash_min_s=999, clash_max_s=999, match_min_s=3, match_max_s=4, scoreboard=False)
        _, atl, brains = sim.make(seed, cfg, 1000.0)
        for b in brains.values():
            b.record = lambda w, l, **kw: rec.append((w, l))
            b.winners = mode
        tele = {LEFT: sim.FakeTelemetry(LEFT, [(0, states[0], ctx[0])]), RIGHT: sim.FakeTelemetry(RIGHT, [(0, states[1], ctx[1])])}
        bus = {}
        hp = {LEFT: [], RIGHT: []}
        banners = []
        for i in range(int(secs * 10)):
            now = 1000 + i / 10.0
            sim.step(brains, tele, now, bus)
            for w, b in brains.items():
                if b.hp is not None:
                    hp[w].append((now, b.hp, bus[w].get('hp')))
                v = b.view(now)
                if b.banner:
                    banners.append(b.banner['kind'])
        return brains, rec, hp, banners

    def test_a_match_plays_from_usage_with_hp_texts_and_one_record(self):
        brains, rec, hp, banners = self.run_match()
        bouts = [n for n in brains[LEFT].bout_log if n[0] == 'bout']
        self.assertTrue(bouts and bouts[0][3] == 'match', bouts)
        results = [n for n in brains[LEFT].bout_log if n[0] == 'result']
        self.assertEqual(len(rec), len(results))                         # written once per match, by the left side only
        self.assertGreaterEqual(len(rec), 1)
        self.assertEqual(set(rec[0]), {'claude', 'codex'})
        self.assertTrue(hp[LEFT] and hp[RIGHT])
        self.assertTrue(all(h == p for _, h, p in hp[LEFT]))              # HP is on the bus
        self.assertEqual(hp[LEFT][0][1], 100)
        self.assertTrue(any(h == 0 for _, h, _ in hp[LEFT] + hp[RIGHT]))
        self.assertTrue({'round1', 'fight', 'ko', 'winner'} <= set(banners), set(banners))
        if brains[LEFT].script is None:                                   # cleared after the match (unless the next one is on)
            self.assertIsNone(brains[LEFT].hp)
            self.assertIsNone(brains[LEFT].banner)
        plan = brains[LEFT].last_match
        self.assertEqual(plan['mode'], 'decided')

    def test_both_sides_derive_the_same_scores_and_mode(self):
        cfg = dict(CFG, scoreboard=False)
        _, atl, brains = sim.make(2, cfg, 1000.0)
        tele = {LEFT: sim.FakeTelemetry(LEFT, [(0, 'working', 40.0)]), RIGHT: sim.FakeTelemetry(RIGHT, [(0, 'idle', 70.0)])}
        bus = {}
        sim.step(brains, tele, 1000.0, bus)
        sim.step(brains, tele, 1000.2, bus)
        brains[LEFT].winners = 'random'
        p = brains[LEFT]._plan('match', 1000.3)
        self.assertEqual(p['mode'], 'random')
        self.assertEqual(p['scores'], {'a': 90.0, 'b': 50.0})             # (100-40)+20+10 ; (100-70)+20
        self.assertEqual(p['kind'], 'match')

    def test_random_mode_reaches_the_timeline(self):
        brains, rec, hp, banners = self.run_match(mode='random')
        self.assertEqual(brains[LEFT].last_match['mode'], 'random')
        self.assertEqual(len(rec), 1)


class Record(Isolated):
    def test_record_json_is_atomic_and_counts_w_l(self):
        self.assertTrue(rounds.record_result('claude', 'codex', now=5.0))
        self.assertTrue(rounds.record_result('codex', 'claude', now=6.0, where='arena'))
        self.assertTrue(rounds.record_result('claude', 'gemini', now=7.0))
        rec = rounds.read_record()
        self.assertEqual(rounds.record_for(rec, 'claude'), (2, 1))
        self.assertEqual(rounds.record_for(rec, 'codex'), (1, 1))
        self.assertEqual(rounds.record_for(rec, 'gemini'), (0, 1))
        self.assertEqual(rounds.record_for(rec, 'nobody'), (0, 0))
        self.assertEqual(rec['matches'], 3)
        self.assertEqual(rec['last']['where'], 'taskbar')
        self.assertEqual([p.name for p in self.data.iterdir() if p.name.endswith('.tmp')], [])
        (self.data / 'record.json').write_text('{broken', encoding='utf-8')
        self.assertEqual(rounds.read_record(), {})
        self.assertTrue(rounds.record_result('claude', 'codex'))          # a corrupt file is replaced, not a crash
        self.assertEqual(rounds.record_for(rounds.read_record(), 'claude'), (1, 0))

    def test_winners_switch_lives_in_control_json(self):
        self.assertEqual(control.winners(), 'decided')
        self.assertTrue(control.set_winners('random'))
        self.assertEqual(control.winners(), 'random')
        self.assertEqual(json.loads((self.data / 'control.json').read_text())['winners'], 'random')
        with self.assertRaises(ValueError):
            control.set_winners('coin')
        self.assertTrue(control.set_winners('decided'))
        self.assertEqual(control.winners(), 'decided')


if __name__ == '__main__':
    unittest.main()
