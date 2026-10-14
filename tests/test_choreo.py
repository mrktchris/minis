"""V5 fight choreography: the seeded no-repeat picker, exchange grammar, variety over seeded matches, hitstop / slides in the
brain, growing beams + flash + move shakes in the effects, and the arena playing the same grammar (air-to-air, beams,
knockdown -> getup, the once-per-match ultimate with flash + shake)."""
import collections, json, random, shutil, sys, tempfile, unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG  # noqa: E402
from minis_core import arena as AR, choreo, effects, fx as fxmod, render, rounds, sim  # noqa: E402
from minis_core.atlas import Library, available  # noqa: E402
from minis_core.brain import LEFT, RIGHT, make_timeline  # noqa: E402
from minis_core.telemetry import Snapshot  # noqa: E402

LIB = Library()
HD = Library(hd=True)
FX = fxmod.default()
PAIRS = [('claude', 'codex'), ('gemini', 'cursor'), ('ollama', 'lmstudio'), ('generic', 'claude')]


def plan(seed, c1, c2, kind='match'):
    return dict(kind=kind, left='a', right='b', pos={'a': 500.0, 'b': 524.0}, t0=1000.0, seed=seed, chars={'a': c1, 'b': c2},
                mode='decided', scores={'a': 100.0, 'b': 100.0}, id='t:1', deadline=1003.0)


def seeded_matches(n=20):
    """-> (attack picks per character, anims per character, summaries) over n seeded matches across the roster pairs."""
    picks = collections.defaultdict(collections.Counter)
    anims = collections.defaultdict(set)
    sums = []
    for seed in range(n):
        c1, c2 = PAIRS[seed % len(PAIRS)]
        tl, t_end, s = rounds.make_match(plan(seed, c1, c2), {c1: LIB[c1], c2: LIB[c2]}, FX)
        sums.append((c1, c2, tl, s))
        for slot, ch in (('a', c1), ('b', c2)):
            for b in s['beats'][slot]:
                if b['kind'] in choreo.ATTACK_KINDS:
                    picks[ch][b['anim']] += 1
            anims[ch] |= {n for t, n, o in tl[slot] if not n.startswith('@')}
    return picks, anims, sums


class PickerRules(unittest.TestCase):
    def test_never_the_same_move_twice_in_a_row_and_at_most_twice_a_round(self):
        p = choreo.Picker(random.Random(3), LIB['claude'])
        seq = [p.pick(p.strikes()) for _ in range(12)]            # 6 strikes x 2 = exactly what a round allows
        self.assertTrue(all(a != b for a, b in zip(seq, seq[1:])), seq)
        self.assertTrue(all(c <= choreo.MAX_PER_ROUND for c in collections.Counter(seq).values()), seq)
        more = p.pick(p.strikes())                                # exhausted: the rule relaxes instead of failing
        self.assertIsNotNone(more)
        self.assertNotEqual(more, seq[-1])
        p.new_round()
        self.assertEqual(sum(p.used.values()), 0)
        self.assertGreater(sum(p.counts.values()), 12)           # the match tally survives the round

    def test_same_seed_same_exchange_different_seed_differs(self):
        A, D = LIB['claude'], LIB['codex']
        sit = dict(range='far', meter=0, ult_ok=True, dramatic=False, friendly=False, air=False, k=1)
        one = choreo.plan_exchange(random.Random(7), choreo.Picker(random.Random(7), A), choreo.Picker(random.Random(7), D), dict(sit))
        two = choreo.plan_exchange(random.Random(7), choreo.Picker(random.Random(7), A), choreo.Picker(random.Random(7), D), dict(sit))
        self.assertEqual(one, two)
        seen = {json.dumps(choreo.plan_exchange(random.Random(s), choreo.Picker(random.Random(s), A), choreo.Picker(random.Random(s), D), dict(sit)), sort_keys=True)
                for s in range(30)}
        self.assertGreater(len(seen), 15)                        # thirty seeds: many different exchanges

    def test_grammar_covers_openers_answers_combos_and_resets(self):
        A, D = LIB['claude'], LIB['codex']
        kinds, openers, outcomes, lens, resets, counters, taunts = set(), set(), set(), [], 0, 0, 0
        for s in range(300):
            rng = random.Random(s)
            sit = dict(range=('far' if s % 2 else 'close'), meter=(100 if s % 5 == 0 else 0), ult_ok=True, dramatic=(s % 7 == 0), friendly=False, air=False, k=3)
            ex = choreo.plan_exchange(rng, choreo.Picker(rng, A), choreo.Picker(rng, D), sit)
            kinds.add(ex['kind'])
            openers.add(ex['opener'])
            atk = [b for b in ex['beats'] if b['kind'] in choreo.ATTACK_KINDS]
            outcomes |= {b['outcome'] for b in atk}
            lens.append(len([b for b in atk if b['who'] == 'att']))
            resets += any(b['kind'] == 'move' and b['dx'] < 0 for b in ex['beats'])
            counters += any(b['kind'] == 'counter' for b in ex['beats'])
            taunts += any(b['kind'] == 'emote' for b in ex['beats'])
            for b in atk:
                self.assertIn(b['anim'], A.anim if b['who'] == 'att' else D.anim)
                self.assertGreaterEqual(b['hitstop'], 0)
        self.assertEqual(kinds, {'strike', 'special', 'super', 'ultimate'})
        self.assertEqual(openers, {None, 'dash', 'jump', 'sweep'})
        self.assertEqual(outcomes, {'hit', 'block', 'crouch_block', 'parry', 'whiff'})
        self.assertGreater(max(lens), 2)                         # combos: jab -> cross -> uppercut chains
        self.assertGreater(resets, 30)
        self.assertGreater(counters, 10)                         # parry -> counter
        self.assertGreater(taunts, 0)                            # a taunt after a whiffed ultimate


class Variety(unittest.TestCase):
    def test_twenty_seeded_matches_no_move_over_25pct_and_12_plus_distinct_moves_per_character(self):
        picks, anims, sums = seeded_matches(20)
        self.assertEqual(set(picks), set(available()))
        for ch, c in picks.items():
            n = sum(c.values())
            top, share = c.most_common(1)[0]
            self.assertLessEqual(share / n, 0.25, (ch, top, share, n, c))
            self.assertGreaterEqual(len(anims[ch]), 12, (ch, sorted(anims[ch])))
        played = set().union(*anims.values())
        for must in ('dash', 'jump', 'backdash', 'walk_back', 'block', 'block_hit', 'parry', 'crouch_block', 'knockdown', 'getup', 'taunt',
                     'hit', 'hit_heavy'):
            self.assertIn(must, played)
        kinds = collections.Counter(b['kind'] for c1, c2, tl, s in sums for slot in 'ab' for b in s['beats'][slot])
        for k in ('strike', 'special', 'super', 'ultimate', 'counter', 'move'):
            self.assertGreater(kinds[k], 0, kinds)
        self.assertGreater(sum(s['air'] for c1, c2, tl, s in sums), 20)      # air-to-air exchanges

    def test_the_ultimate_comes_once_per_match_at_a_dramatic_moment_with_flash_and_shake(self):
        picks, anims, sums = seeded_matches(20)
        n_ult = 0
        for c1, c2, tl, s in sums:
            for slot in 'ab':
                ults = [b for b in s['beats'][slot] if b['kind'] == 'ultimate']
                self.assertLessEqual(len(ults), 1, (c1, c2))
                n_ult += len(ults)
                if ults and ults[0]['outcome'] == 'hit':
                    self.assertTrue(any(n == '@flash' for t, n, o in tl[slot]), 'an ultimate that lands flashes')
                    self.assertTrue(any(n == '@shake' for t, n, o in tl[slot]), 'and shakes')
                    other = 'b' if slot == 'a' else 'a'
                    self.assertTrue(any(n == '@fx' and o.get('impact') for t, n, o in tl[other]), 'impact burst on the defender')
            # never in the first two exchanges of a round: the ultimate's move entry comes after at least two contacts in its round
            for slot in 'ab':
                moves = [(t, n, o) for t, n, o in tl[slot] if o.get('kind') == 'ultimate' and 'contact' in o]
                for t, n, o in moves:
                    r = [r for r in s['rounds'] if r['t0'] <= t <= r['t1'] + 1.0]
                    self.assertTrue(r, (t, s['rounds']))
                    before = [1 for w in 'ab' for t2, n2, o2 in tl[w] if 'contact' in o2 and r[0]['t0'] <= t2 < t]
                    self.assertGreaterEqual(len(before), 2)
        self.assertGreater(n_ult, 10)

    def test_knockdowns_get_up_and_hitstop_rides_on_the_contact(self):
        c1, c2 = 'claude', 'codex'
        tl, t_end, s = rounds.make_match(plan(5, c1, c2), {c1: LIB[c1], c2: LIB[c2]}, FX)
        for slot in 'ab':
            downs = [(t, o) for t, n, o in tl[slot] if n == 'knockdown' and o.get('hp', {}).get(slot, 0) > 0]
            getups = [t for t, n, o in tl[slot] if n == 'getup']
            for t, o in downs:
                self.assertTrue(any(t < g < t + 2.0 for g in getups), (slot, t, getups))
            for t, n, o in tl[slot]:
                if 'contact' in o and o.get('outcome') in ('hit', 'block', 'crouch_block', 'parry'):
                    self.assertGreater(o['hitstop'], 0, (n, o))
                if 'to' in o:
                    self.assertTrue(abs(o['to'] - 512.0) <= rounds.SPAN_PX + 1, o)   # slides stay around the bout centre

    def test_friendly_spar_uses_the_grammar_without_finishers(self):
        lib = Library()
        p = dict(kind='spar', left=LEFT, right=RIGHT, pos={LEFT: 400, RIGHT: 424}, t0=50.0, seed=11, chars={LEFT: 'gemini', RIGHT: 'ollama'})
        tl, t_end, projs = make_timeline('spar', p, lib, FX)
        names = collections.Counter(n for w in tl for t, n, o in tl[w] if not n.startswith('@'))
        self.assertNotIn('knockdown', names)
        self.assertNotIn('ko', names)
        for w in tl:
            for t, n, o in tl[w]:
                self.assertNotEqual(o.get('kind'), 'ultimate')
                self.assertNotEqual(o.get('kind'), 'super')
        self.assertEqual(names['bow'], 4)
        self.assertGreater(len(names), 8)
        a, b = make_timeline('spar', p, lib, FX), make_timeline('spar', p, lib, FX)
        self.assertEqual(a[0], b[0])


class BrainPlayback(unittest.TestCase):
    def test_hitstop_freezes_the_clock_and_slides_move_the_fighter(self):
        cfg, atl, brains = sim.make(1, dict(CFG), 1000.0)
        b = brains[LEFT]
        b.play('jab', 1000.0, loop=False)
        f_before = b.frame(1000.2)[0]
        b.stop = (1000.2, 1000.5)
        self.assertEqual(b.frame(1000.45)[0], f_before)             # held through the stop
        self.assertEqual(b.frame(1000.8)[0], b.atlas.locate('jab', 500.0, False)[0])      # resumes where it left off
        b.stop = None
        b.mode = 'script'
        b.x = 400.0
        b.script = dict(kind='match', plan=dict(pos={LEFT: 400.0, RIGHT: 424.0}), tl=[(1001.0, 'dash', {'to': 430.0, 'slide_ms': 350}),
                                                                                (1001.35, 'idle', {})], t_end=1003.0, projs=[])
        b.script_i = -1
        b._tick_script(1001.0)
        b._tick_script(1001.2)
        self.assertTrue(400.0 < b.x < 430.0, b.x)
        b._tick_script(1001.4)
        self.assertEqual(b.x, 430.0)
        self.assertIsNone(b.slide)

    def test_whiff_shake_and_flash_directives_reach_the_logs_and_the_player(self):
        cfg, atl, brains = sim.make(1, dict(CFG), 1000.0)
        b = brains[LEFT]
        b.mode = 'script'
        b.script = dict(kind='match', plan=dict(pos={LEFT: 400.0, RIGHT: 424.0}), tl=[
            (1000.0, '@whiff', {'react_to': 'jab'}), (1000.0, '@shake', {'frames': 4, 'amp': 3}), (1000.0, '@flash', {'alpha': 0.6})], t_end=1003.0, projs=[])
        b.script_i = -1
        b._tick_script(1000.01)
        self.assertEqual(list(b.hit_log), [(1000.0, 'whiff')])
        self.assertEqual([n for n in b.bout_log if n[0] == 'hit'][0][3], 'whiff')
        b.fxp.tick(1000.02)
        self.assertNotEqual(b.fxp.shake(1000.02), (0, 0))
        v = b.view(1000.02)
        self.assertAlmostEqual(v['flash'], 0.6)
        self.assertEqual(b.view(1000.5)['flash'], 0.0)

    def test_two_brains_agree_on_a_v5_match_and_both_see_slides_and_stops(self):
        cfg = dict(CFG, bout_min_s=999, bout_max_s=999, clash_min_s=999, clash_max_s=999, match_min_s=3, match_max_s=4, scoreboard=False)
        _, atl, brains = sim.make(4, cfg, 1000.0)
        for br in brains.values():
            br.record = lambda w, l, **kw: None
        tele = {LEFT: sim.FakeTelemetry(LEFT, [(0, 'working', 41.0)]), RIGHT: sim.FakeTelemetry(RIGHT, [(0, 'idle', 70.0)])}
        bus = {}
        xs = {LEFT: set(), RIGHT: set()}
        stops = {LEFT: 0, RIGHT: 0}
        for i in range(900):
            now = 1000 + i / 10.0
            sim.step(brains, tele, now, bus)
            for w, br in brains.items():
                if br.mode == 'script':
                    xs[w].add(round(br.x))
                    stops[w] += br.stop is not None
        self.assertTrue(brains[LEFT].last_match and brains[LEFT].last_match['rounds'])
        self.assertGreater(len(xs[LEFT]), 3)                        # dash-ins, backdashes and knockback moved them
        self.assertGreater(len(xs[RIGHT]), 3)
        self.assertGreater(stops[LEFT] + stops[RIGHT], 0)
        z0, z1 = brains[LEFT].zone
        self.assertTrue(all(z0 <= x <= z1 for w in xs for x in xs[w]))


class Beams(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='minis-beam-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        im = Image.new('RGBA', (256, 64), (0, 0, 0, 0))
        for x in range(256):
            for y in range(16, 48):
                im.putpixel((x, y), (120, 200, 255, 255))
        for x in range(0, 32):
            for y in range(32):
                im.putpixel((x, y), (255, 10, 0, 255))
        im.save(self.tmp / 'fx.png')
        meta = {'res': 2, 'effects': {
            'beam': {'frames': [{'x': 0, 'y': 16, 'w': 256, 'h': 32, 'ms': 100}, {'x': 0, 'y': 16, 'w': 256, 'h': 32, 'ms': 300},
                                {'x': 0, 'y': 16, 'w': 256, 'h': 32, 'ms': 200}], 'anchor': 'hand', 'offset': [128, 0], 'hit_frame': 1,
                     'shake': {'frames': 6, 'amp': 4}, 'grow': {'from_w': 16, 'to_w': 256, 'ms': 300}, 'flash': True},
            'burst': {'frames': [{'x': 0, 'y': 0, 'w': 32, 'h': 32, 'ms': 60}], 'anchor': 'center', 'hit_frame': 0},
        }}
        (self.tmp / 'fx.json').write_text(json.dumps(meta), encoding='utf-8')
        self.fx = fxmod.Fx(paths=[self.tmp / 'fx.json'])

    def test_grow_and_flash_are_read_and_absent_keys_fall_back(self):
        e = self.fx.get('beam')
        self.assertEqual(e.grow, {'from_w': 16, 'to_w': 256, 'ms': 300, 'retract_ms': 200})
        self.assertTrue(e.flash)
        self.assertEqual(e.extent(0), (0, 16, 1.0))
        self.assertEqual(e.extent(150)[1], 136.0)
        self.assertEqual(e.extent(300), (0, 256, 1.0))
        self.assertEqual(e.extent(400), (0, 256, 1.0))               # holds
        s, en, a = e.extent(500)
        self.assertTrue(0 < s < 256 and en == 256 and a < 1.0)        # retracts and fades over the last frame
        b = self.fx.get('burst')
        self.assertIsNone(b.grow)
        self.assertFalse(b.flash)
        self.assertIsNone(b.extent(10))
        self.assertIsNone(fxmod.Effect('x', [(Image.new('RGBA', (8, 8)), 50)], grow={'to_w': 'nope'}).grow)

    def test_beam_extends_from_the_hand_in_both_facings_and_reports_its_end(self):
        for facing in (1, -1):
            p = effects.EffectPlayer(self.fx, res=2, fps=30)
            inst = p.spawn('beam', 10.0, 300, 114, facing, hand=(36, -53))
            origin = p.beam_origin(inst)
            self.assertAlmostEqual(origin, 300 + facing * 36, delta=0.5)       # the beam leaves the hand
            p.tick(10.0)
            widths = []
            for t in (10.0, 10.15, 10.3, 10.4):
                pl = p.placements(t)
                self.assertEqual(len(pl), 1)
                im, left, top, layer, i = pl[0]
                widths.append(im.width)
                near = left if facing > 0 else left + im.width
                self.assertAlmostEqual(near, origin, delta=1.0)              # anchor edge stays put while it grows
                self.assertAlmostEqual(p.beam_end(i, t), origin + facing * im.width, delta=1.0)
            self.assertEqual(widths, sorted(widths))
            self.assertEqual(widths[0], 16)
            self.assertEqual(widths[-1], 256)
            self.assertEqual(p.reach('beam'), 256)
            im, left, top, layer, i = p.placements(10.5)[0]
            self.assertLess(im.width, 256)                                     # retracting: the start edge races to the end
            far = left + im.width if facing > 0 else left
            self.assertAlmostEqual(far, origin + facing * 256, delta=1.0)
            self.assertLess(im.getpixel((im.width // 2, im.height // 2))[3], 255)   # and fading
        self.assertEqual(effects.EffectPlayer(self.fx, res=1, fps=30).reach('beam'), 128)   # half size on the taskbar

    def test_flash_and_move_shake(self):
        p = effects.EffectPlayer(self.fx, res=2, fps=30)
        p.spawn('beam', 0.0, 100, 100, 1)
        p.tick(0.0)
        self.assertEqual(p.flash(0.05), 0.0)                                   # before the hit frame
        self.assertAlmostEqual(p.flash(0.11), 0.6)                             # hit frame at 100 ms: one frame of white
        self.assertEqual(p.flash(0.3), 0.0)
        p.flash_at(1.0, 0.5)
        self.assertEqual(p.flash(1.02), 0.5)
        self.assertNotEqual(p.shake(0.11), (0, 0))                             # the effect's own shake, from its hit frame
        q = effects.EffectPlayer(fxmod.Fx(paths=[]), res=1, fps=30)
        self.assertEqual(q.shake(0.0), (0, 0))
        q.add_shake(0.0, 3, 2.0)
        self.assertNotEqual(q.shake(0.01), (0, 0))
        self.assertEqual(q.shake(0.5), (0, 0))

    def test_compose_whitens_only_drawn_pixels(self):
        a = LIB['claude']
        view = dict(anim='idle', frame=0, x=500, facing=1, dim=False, proj=None, fx=[], banner=None, shake=(0, 0), flash=0.6)
        im, x0 = render.compose(a, a, view, Snapshot('claude', 'idle', 20.0), 0.0, CFG, show_plate=False)
        plain, _ = render.compose(a, a, dict(view, flash=0.0), Snapshot('claude', 'idle', 20.0), 0.0, CFG, show_plate=False)
        self.assertEqual(im.size, plain.size)
        self.assertNotEqual(im.tobytes(), plain.tobytes())
        pa, pb = plain.load(), im.load()
        brighter = 0
        for y in range(im.height):
            for x in range(im.width):
                if pa[x, y][3] == 0:
                    self.assertEqual(pb[x, y][3], 0)                           # transparent stays transparent (plate-safe taskbar)
                elif sum(pb[x, y][:3]) > sum(pa[x, y][:3]):
                    brighter += 1
        self.assertGreater(brighter, 100)


MON = (2560, 76, 4480, 1156)
FLOOR = 1108
WINS = [(11, 2560 + 300, 76 + 200, 2560 + 1200, 76 + 800), (12, 2560 + 1300, 76 + 300, 2560 + 1800, 76 + 900)]


def arena_match(seed, chars=('claude', 'codex'), secs=150):
    st = AR.Stage(MON, WINS, floor_y=FLOOR)
    ar = AR.Arena(st, {'a': HD[chars[0]], 'b': HD[chars[1]]}, FX, seed=seed, backdrop=None, now=0.0, record=lambda *a, **k: None)
    now = 0.0
    while ar.phase != 'done' and now < secs:
        now += 1 / 30.0
        ar.tick(now)
    return ar


class ArenaChoreo(unittest.TestCase):
    def test_arena_plays_the_grammar_air_exchanges_beams_knockdown_getup_and_one_ultimate(self):
        kinds_all = collections.Counter()
        moves = collections.Counter()
        for seed in range(4):
            ar = arena_match(seed)
            self.assertEqual(ar.phase, 'done', seed)
            ev = [e for e in ar.events]
            kinds = collections.Counter(e[0] for e in ev)
            kinds_all += kinds
            for e in ev:
                if e[0] == 'strike':
                    moves[e[2]['move']] += 1
            self.assertGreaterEqual(kinds['air_exchange'], 1, kinds)                 # air-to-air every match
            ults = collections.Counter(e[2]['who'] for e in ev if e[0] == 'ultimate')
            self.assertTrue(all(n <= 1 for n in ults.values()), ults)              # once per match per fighter
            for r in ar.rounds:
                self.assertLessEqual(r['dur'], rounds.ROUND_CAP_S + 1.5, r)
            t_down = [e[1] for e in ev if e[0] == 'knockdown' and not e[2].get('ko')]
            t_up = [e[1] for e in ev if e[0] == 'getup']
            for t in t_down:
                self.assertTrue(any(t < u < t + 3.0 for u in t_up), (t, t_up))      # knocked down but not out: kip up
        self.assertGreater(kinds_all['beam'], 0)
        self.assertGreater(kinds_all['flash'], 0)
        self.assertGreater(kinds_all['explosion'], 0)
        self.assertGreater(kinds_all['parry'] + kinds_all['block'], 3)
        self.assertGreater(kinds_all['reset'], 3)
        self.assertGreater(kinds_all['whiff'], 0)
        n = sum(moves.values())
        self.assertGreaterEqual(len(moves), 9, moves)
        self.assertLessEqual(moves.most_common(1)[0][1] / n, 0.25, moves)

    def test_beam_ultimate_lands_on_the_defender_with_knockback_along_the_beam_and_the_flash_is_one_full_frame(self):
        st = AR.Stage(MON, WINS, floor_y=FLOOR)
        ar = AR.Arena(st, {'a': HD['claude'], 'b': HD['codex']}, FX, seed=2, backdrop=None, now=0.0, record=lambda *a, **k: None)
        now = 0.0
        while ar.phase != 'fight':
            now += 1 / 30.0
            ar.tick(now)
        a, b = ar.f['a'], ar.f['b']
        a.x, a.y, a.grounded, a.vx, a.vy = 600.0, float(st.floor_y), True, 0.0, 0.0
        b.x, b.y, b.grounded, b.vx, b.vy = 900.0, float(st.floor_y), True, 0.0, 0.0
        ult = a.atlas.ultimate()
        reach = ar._reach('a', ult)
        self.assertGreater(reach, 0)                                             # Claude's ultimate is a beam
        beat = dict(who='att', kind='ultimate', anim=ult, dmg=40, outcome='hit', pre=None, react='knockdown', hitstop=300, knock=36, down=True)
        ar.exchange = dict(att='a', dfn='b', beats=[beat], i=0, state='approach', t=now, deadline=now + 6.0, air=False, kind='ultimate',
                           opener=None, range_after='far', hit=False)
        ar.cooldown_until = 0.0
        hp0 = b.hp
        t_hit = None
        surf = AR.Surface(st.w, st.h)
        comp = AR.Compositor(ar, surf)
        comp.render(now)
        full = []
        for i in range(30 * 8):
            now += 1 / 30.0
            ar.tick(now)
            d = comp.render(now)
            if d == [(0, 0, st.w, st.h)]:
                full.append(round(now, 2))
            if t_hit is None and b.hp < hp0:
                t_hit = now
                self.assertLessEqual(abs(a.x - b.x), reach + 8)                  # the beam reaches the hurtbox
                self.assertGreaterEqual(abs(a.x - b.x), AR.REACH_PX)            # fired from range, not point blank
                self.assertEqual(b.hp, hp0 - 40)
                self.assertTrue(b.down)
                self.assertGreater(b.vx * a.facing, 900)                        # knockback along the beam
                self.assertTrue(a.stopped(now) and b.stopped(now))               # hitstop on contact, both
                self.assertEqual(a.frame(now), a.frame(now + 0.2))               # the clock really stands still
                self.assertGreater(ar.fxp.flash(now), 0)
                names = [i.effect.name for i in ar.fxp.active]
                self.assertTrue(any(n in ('explosion', f'{ult}_impact') for n in names), names)   # impact burst at the beam end
            if ar.phase != 'fight':
                break
        self.assertIsNotNone(t_hit, [e for e in ar.events][-12:])
        self.assertGreaterEqual(len(full), 2)                                    # the flash frame and the frame that clears it
        self.assertTrue(any(abs(t - t_hit) < 0.1 for t in full), (full, t_hit))
        self.assertIn('ultimate', [e[0] for e in ar.events])
        st_json = json.dumps(ar.state())                                         # the heartbeat carries the recent events
        self.assertIn('"events"', st_json)
        self.assertTrue(any(k == 'beam' and name == ult for k, t, name in ar.state()['events']))   # the heartbeat names the effect that fired


if __name__ == '__main__':
    unittest.main()
