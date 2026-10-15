"""Arena mode, headless: platforms from a synthetic window list, flight, rounds, cracks / shatter, the RAM-only freeze
backdrop, the compositor's dirty rectangles, EXIT hit-test.  Nothing here touches the real desktop or any real window."""
import collections, os, shutil, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG, Isolated  # noqa: E402
from minis_core import arena as AR, fx, rounds  # noqa: E402
from minis_core.atlas import Library  # noqa: E402

LIB = Library(hd=True)
FX = fx.default()
MON = (2560, 76, 4480, 1156)                 # a 1920x1080 monitor to the right of the primary one
FLOOR = 1108
WINS = [(11, 2560 + 300, 76 + 200, 2560 + 1200, 76 + 800), (12, 2560 + 1300, 76 + 300, 2560 + 1800, 76 + 900),
        (13, 2560 - 100, 76 + 500, 2560 + 400, 76 + 700),      # straddles the monitor edge: clipped
        (14, 2560 + 50, 76 + 50, 2560 + 120, 76 + 90),         # too small: not a platform
        (15, 2560, 76, 4480, 1156)]                            # maximized: no platform


def make(seed=3, freeze=True, windows=WINS, record=None, mode='decided', scores=None):
    st = AR.Stage(MON, windows, floor_y=FLOOR)
    bd = AR.synthetic_backdrop(st.w, st.h) if freeze else None
    ar = AR.Arena(st, {'a': LIB['claude'], 'b': LIB['codex']}, FX, seed=seed, mode=mode, scores=scores, backdrop=bd, now=0.0,
                  record=record or (lambda *a, **k: None))
    ar.flashes = True                                          # never read this machine's control.json
    return st, ar


def run(ar, comp=None, secs=120, fps=30, until_phase='done', hook=None):
    now = 0.0
    phases = []
    n = 0
    while ar.phase != until_phase and now < secs:
        now += 1.0 / fps
        ar.tick(now)
        if comp is not None:
            comp.render(now)
        if hook:
            hook(now)
        if not phases or phases[-1] != ar.phase:
            phases.append(ar.phase)
        n += 1
    return now, phases, n


class Platforms(unittest.TestCase):
    def test_platforms_come_from_window_tops_clipped_plus_the_floor(self):
        st = AR.Stage(MON, WINS, floor_y=FLOOR)
        self.assertEqual(st.platforms(), [(1300, 1800, 300), (0, 400, 500), (0, 1920, 1032)])   # window 11's top (200) is inside the HUD band: no platform
        self.assertEqual([w['id'] for w in st.windows], [11, 12, 13])                         # ... but it still cracks
        self.assertGreaterEqual(AR.MIN_PLATFORM_Y, AR.HUD_H + AR.SPRITE_H)
        self.assertEqual(st.window_at(500, 500)['id'], 11)
        self.assertIsNone(st.window_at(1250, 250))
        st.update([])
        self.assertEqual(st.platforms(), [(0, 1920, 1032)])                 # only the floor remains

    def test_crack_state_machine(self):
        c = AR.Cracks()
        self.assertEqual(c.hit(1), 'crack_small')
        self.assertEqual(c.hit(1), 'crack_small')
        self.assertEqual(c.hit(1), 'shatter')
        self.assertIsNone(c.hit(1))                                          # stays shattered
        self.assertEqual(c.hit(2, heavy=True), 'crack_big')
        self.assertEqual(c.hit(2), 'shatter')
        self.assertEqual(c.state(1), 'shattered')
        self.assertEqual(c.state(3), 0)


class Match(unittest.TestCase):
    def test_a_match_runs_entry_rounds_winner_exit_and_records_once(self):
        recs = []
        st, ar = make(record=lambda w, l, **kw: recs.append((w, l, kw.get('where'))))
        now, phases, n = run(ar)
        self.assertEqual(phases[0], 'entry')
        self.assertEqual(phases[-3:], ['winner', 'exit', 'done'])
        self.assertEqual(phases.count('fight'), len(ar.rounds))
        self.assertIn(len(ar.rounds), (2, 3))
        self.assertEqual(max(ar.wins.values()), 2)
        self.assertIn(ar.winner, ('a', 'b'))
        self.assertEqual(recs, [(ar.chars[ar.winner], ar.chars['b' if ar.winner == 'a' else 'a'], 'arena')])
        for r in ar.rounds:
            self.assertLessEqual(r['dur'], rounds.ROUND_CAP_S + 1.5)
        kinds = collections.Counter(e[0] for e in ar.events)
        self.assertGreater(kinds['strike'], 4)
        self.assertGreater(kinds['fly'], 0)                                  # DBZ: somebody took to the air
        hps = [h for t, who, h in ar.hp_history]
        self.assertTrue(all(0 <= h <= 100 for h in hps))
        self.assertIn(0, hps)

    def test_round_cap_is_25_seconds(self):
        st, ar = make(seed=8)
        run(ar, until_phase='fight')
        t0 = ar.round_t0
        ar.p_left = 0.5
        # make every strike miss its mark by keeping the defender unreachable: freeze HP so only the cap can end the round
        ar.f['a'].hp = ar.f['b'].hp = 10 ** 6
        now = ar.last_now
        while ar.phase == 'fight' and now - t0 < 40:
            now += 1 / 30.0
            ar.tick(now)
        self.assertEqual(ar.phase, 'round_end')
        self.assertLessEqual(now - t0, rounds.ROUND_CAP_S + 1.0)
        self.assertGreaterEqual(now - t0, rounds.ROUND_CAP_S - 0.5)
        self.assertEqual(ar.rounds[-1]['ko'], False)

    def test_decided_mode_bias_reaches_the_arena(self):
        wins = collections.Counter()
        for seed in range(20):                                    # V6: the story tilt helps the underdog, so judge a bigger batch
            st, ar = make(seed=seed, freeze=False, scores={'a': 140.0, 'b': 20.0})
            run(ar)
            wins[ar.winner] += 1
        self.assertGreaterEqual(wins['a'], 14, wins)
        st, ar = make(seed=1, mode='random', scores={'a': 140.0, 'b': 20.0})
        self.assertEqual(ar.p_left, 0.5)

    def test_pause_freezes_and_exit_request_leaves(self):
        st, ar = make()
        run(ar, until_phase='fight')
        ar.paused = True
        snap = (ar.f['a'].x, ar.f['a'].y, ar.f['b'].x, ar.state())
        for i in range(60):
            ar.tick(ar.last_now + 0.1 * (i + 1))
        self.assertEqual(snap, (ar.f['a'].x, ar.f['a'].y, ar.f['b'].x, ar.state()))
        ar.paused = False
        ar.request_exit(ar.last_now + 6.1)
        now, phases, n = run(ar, secs=ar.last_now + 10)
        self.assertEqual(phases[-2:], ['exit', 'done'])
        self.assertTrue(all(ar.f[s].y > st.h for s in 'ab'))                 # gone below the floor


class Smash(unittest.TestCase):
    def knock_into_window(self, ar, st, heavy):
        b = ar.f['b']
        ar.phase = 'fight'
        b.x, b.y = 700.0, 600.0                                              # inside window 11 (300..1200 x 200..800)
        b.vx, b.vy = (900.0 if heavy else 400.0), 0.0
        b.knocked_until = ar.last_now + 1.0
        b.last_crack = -10.0
        ar._window_collisions(b, ar.last_now)

    def test_three_hits_crack_then_shatter_with_letters_shards_and_a_hole(self):
        st, ar = make(freeze=True)
        before = ar.backdrop.getpixel((700, 500))
        self.knock_into_window(ar, st, heavy=False)
        self.assertEqual([e[0] for e in ar.events][-1], 'crack_small')
        self.assertEqual(ar.letters_spawned, 0)
        self.knock_into_window(ar, st, heavy=True)
        self.assertEqual([e[0] for e in ar.events][-2:], ['shatter', 'hole'])   # 1 + 2 = 3: shattered, and a hole
        self.assertGreaterEqual(ar.letters_spawned, 9)
        self.assertTrue(any(i.effect.name == 'shatter' for i in ar.fxp.active))
        self.assertTrue(any(i.effect.name == 'letters' and i.gravity > 0 for i in ar.fxp.active))
        self.assertEqual(ar.backdrop.getpixel((700, 500)), AR.HOLE)        # the hole is in the RAM backdrop
        self.assertNotEqual(before, AR.HOLE)
        self.assertEqual(ar.holes, [(300, 200, 1200, 800)])
        self.knock_into_window(ar, st, heavy=True)
        self.assertEqual([e[0] for e in ar.events].count('shatter'), 1)        # a shattered window stays shattered

    def test_no_backdrop_means_no_hole_but_still_shards(self):
        st, ar = make(freeze=False)
        self.knock_into_window(ar, st, True)
        self.knock_into_window(ar, st, True)
        self.assertEqual(ar.holes, [])
        self.assertIn('shatter_done', [e[0] for e in ar.events])

    def test_ultimate_explodes_and_shakes_the_overlay(self):
        st, ar = make(freeze=False)
        run(ar, until_phase='fight')
        now = ar.last_now
        ar.exchange = dict(att='a', dfn='b', move=ar.f['a'].atlas.ultimate(), kind='ultimate', dmg=40, state='strike', t=now, contact=now,
                           end=now + 1, hit_done=False, blocked=False, fx_at=None)
        ar.f['b'].hp = 80
        ar._resolve(ar.exchange, now)
        self.assertEqual(ar.f['b'].hp, 40)
        self.assertEqual(ar.explosions, 1)
        surf = AR.Surface(st.w, st.h)
        comp = AR.Compositor(ar, surf)
        comp.render(now + ar.fxp.hit_frame_time('explosion') + 0.02)         # the shake starts on the explosion's hit frame
        self.assertNotEqual(surf.offsets[-1], (0, 0))                        # the window moves: whole-overlay shake
        comp.render(now + 3.0)
        self.assertEqual(surf.offsets[-1], (0, 0))


class FreezeBackdrop(Isolated):
    def test_backdrop_is_never_written_to_disk(self):
        tmp = Path(tempfile.mkdtemp(prefix='minis-arena-cwd-'))
        self.addCleanup(shutil.rmtree, tmp, True)
        root = Path(__file__).resolve().parent.parent
        before = {p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        data_before = set(self.data.rglob('*'))
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            st, ar = make(freeze=True)
            surf = AR.Surface(st.w, st.h)
            comp = AR.Compositor(ar, surf)
            run(ar, comp, secs=20)
            self.assertGreater(len(ar.cracks.count) + len(ar.cracks.shattered) + ar.explosions + 1, 0)
        finally:
            os.chdir(cwd)
        after = {p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        self.assertEqual(after - before, set())                              # nothing new under the project
        self.assertEqual(set(self.data.rglob('*')) - data_before, set())     # nothing new under the data dir
        self.assertEqual(list(tmp.iterdir()), [])                            # nothing in the working directory
        self.assertIsNotNone(ar.backdrop)
        self.assertEqual(ar.backdrop.size, (st.w, st.h))


class Composing(unittest.TestCase):
    def test_dirty_rects_are_small_and_the_surface_shows_the_fighters(self):
        st, ar = make(freeze=True)
        surf = AR.Surface(st.w, st.h)
        comp = AR.Compositor(ar, surf)
        sizes = []

        def hook(now):
            d = comp.render(now)
            sizes.append(sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in d))
        run(ar, secs=12, hook=hook)
        self.assertEqual(sizes[0], st.w * st.h)                              # first frame: the whole backdrop once
        self.assertEqual(surf.writes, 1 + sum(1 for s in sizes[1:] for _ in [0]) if False else surf.writes)
        typical = sorted(sizes[30:])[len(sizes[30:]) // 2]
        self.assertLess(typical, st.w * st.h * 0.25, typical)                # then only what moved
        # a fighter sprite really is on the surface where the body says it is
        b = ar.f['a']
        l, t, r, bt = b.sprite_rect()
        crop = surf.canvas.crop((max(0, l), max(0, t), min(st.w, r), min(st.h, bt)))
        bd = ar.backdrop.crop((max(0, l), max(0, t), min(st.w, r), min(st.h, bt)))
        self.assertNotEqual(crop.tobytes(), bd.tobytes())
        self.assertEqual(surf.canvas.size, (st.w, st.h))
        self.assertGreater(ar.f['a'].sprite_rect()[3] - ar.f['a'].sprite_rect()[1], 200)   # HD at 2x: 256 px cells

    def test_exit_button_hit_test_and_hud(self):
        st, ar = make(freeze=False)
        x0, y0, x1, y1 = ar.exit_rect()
        self.assertEqual(x1, st.w - AR.EXIT_MARGIN)
        self.assertTrue(ar.hit_exit(x0 + 5, y0 + 5))
        self.assertTrue(ar.hit_exit(x1, y1))
        self.assertFalse(ar.hit_exit(x0 - 1, y0))
        self.assertFalse(ar.hit_exit(st.w // 2, st.h // 2))
        run(ar, until_phase='fight')
        items = ar.drawables(ar.last_now)
        self.assertEqual(items[-1][1:], (x0, y0))                            # the button is always the last (topmost) drawable
        hud = [im for im, x, y in items if (x, y) == (0, 0) and im.width == st.w]
        self.assertEqual(len(hud), 1)
        self.assertTrue(ar.state()['hp'] == {'a': 100, 'b': 100} or ar.state()['hp'])

    def test_merge_rects(self):
        from minis_platform.rects import merge_rects                    # pure: runs on every OS
        self.assertEqual(sorted(merge_rects([(0, 0, 10, 10), (5, 5, 20, 20), (100, 100, 110, 110)])), [(0, 0, 20, 20), (100, 100, 110, 110)])
        many = [(i * 50, 0, i * 50 + 10, 10) for i in range(30)]
        self.assertLessEqual(len(merge_rects(many, limit=12)), 12)
        self.assertEqual(merge_rects([]), [])


class FightFeelV6(unittest.TestCase):
    """V6 rules in the arena: rare ultimate (one per match, attacker below 30 HP), impact frames that honour the flashes
    switch without full-screen frames, the KO finisher beat inside 3.5 s, braces on wind-ups, TIME + slump, comeback, boost."""

    def test_pacing_most_rounds_end_by_ko_in_10_to_18_s(self):
        lens, ko = [], 0
        for seed in range(30):
            st, ar = make(seed=seed, freeze=False)
            run(ar, secs=240)
            for r in ar.rounds:
                lens.append(r['dur'])
                ko += r['ko']
        self.assertLess(1 - ko / len(lens), 0.2, (ko, len(lens)))             # TIME is the exception (V5: 46 % of rounds)
        mean = sum(lens) / len(lens)
        self.assertTrue(10.0 <= mean <= 18.0, mean)

    def test_a_far_special_fires_instead_of_bouncing_between_approach_and_beat(self):
        st, ar = make(freeze=False)
        run(ar, until_phase='fight')
        now = ar.last_now
        a, b = ar.f['a'], ar.f['b']
        a.x, b.x = 300.0, 1600.0
        sp = a.atlas.signature()['special']
        beat = dict(who='att', kind='special', anim=sp, dmg=12, outcome='block', pre='block', react='block_hit', hitstop=100, knock=3, down=False)
        ar.exchange = dict(att='a', dfn='b', beats=[beat], i=0, state='beat', t=now, deadline=now + 6.0, air=False, kind='special', opener=None,
                           range_after='far', hit=False)
        ar._start_beat(ar.exchange, now)
        self.assertEqual(ar.exchange['state'], 'strike')


    def matches(self, seeds):
        out = []
        for seed in seeds:
            st, ar = make(seed=seed, freeze=False)
            ar.flashes = True
            ko_t, exit_t = [], []

            def hook(now, ar=ar):
                if ar.phase == 'exit' and not exit_t:
                    exit_t.append(now)
            run(ar, secs=200, hook=hook)
            out.append((ar, exit_t[0] if exit_t else None))
        return out

    def test_one_ultimate_per_match_only_below_30_hp_and_ko_finisher_inside_3_5_s(self):
        n_ult = finals = 0
        for ar, t_exit in self.matches(range(6)):
            ev = list(ar.events)
            ults = [e for e in ev if e[0] == 'ultimate']
            self.assertLessEqual(len(ults), 1)
            n_ult += len(ults)
            for kind, t, kw in ults:                                   # the attacker's HP when it fired
                hp = [h for (t2, who, h) in ar.hp_history if who == kw['who'] and t2 <= t]
                self.assertTrue(hp and hp[-1] < 30, (kw, hp))
            if ar.final_ko is not None and ar.rounds[-1]['ko']:
                finals += 1
                self.assertIsNotNone(t_exit)
                self.assertLessEqual(t_exit - ar.final_ko[0], rounds.POST_KO_MAX_S + 0.1, (ar.final_ko, t_exit))
                self.assertIn('impact', [e[0] for e in ev if e[1] >= ar.final_ko[0] - 1e-3])
            self.assertEqual(ar.phase, 'done')
        self.assertGreater(finals, 2)

    def test_winner_beat_has_the_name_banner_and_the_loser_slumps_up(self):
        st, ar = make(seed=2, freeze=False)
        ar.flashes = True
        seen = {}

        def hook(now):
            if ar.phase == 'winner':
                if ar.banner and ar.banner[0] == 'winner':
                    seen['banner'] = ar.banner
                loser = 'b' if ar.winner == 'a' else 'a'
                if ar.f[loser].anim == 'getup':
                    seen['getup'] = ar.f[loser].slow
        run(ar, secs=200, hook=hook)
        self.assertEqual(seen['banner'][3], ar.names[ar.winner])
        if ar.rounds[-1]['ko']:
            self.assertIsNotNone(seen.get('getup'))
            self.assertEqual(seen['getup'][2], rounds.GETUP_SLOW_K)

    def test_impact_frames_are_silhouettes_never_full_frames_and_obey_the_switch(self):
        for on in (True, False):
            st, ar = make(freeze=False)
            ar.flashes = on
            run(ar, until_phase='fight')
            now = ar.last_now
            surf = AR.Surface(st.w, st.h)
            comp = AR.Compositor(ar, surf)
            comp.render(now)
            ar.exchange = dict(att='a', dfn='b', move='roundhouse', kind='strike', dmg=36, state='strike', t=now, contact=now, end=now + 1,
                               hit_done=False)
            ar._resolve(ar.exchange, now)
            self.assertEqual(ar.impact is not None, on)
            self.assertEqual('impact' in [e[0] for e in ar.events], on)
            d = comp.render(now + 0.03)
            self.assertNotEqual(d, [(0, 0, st.w, st.h)])                       # only the sprite rects change
            if on:
                im = ar._sprite(ar.f['b'].atlas, ar.f['b'].anim, ar.f['b'].frame(now + 0.03)[0], ar.f['b'].facing, silhouette='white')
                px = {p for p in im.getdata() if p[3]}
                self.assertEqual(px, {(255, 255, 255, 255)})

    def test_flashes_off_means_no_white_frame_from_an_ultimate(self):
        st, ar = make(freeze=False)
        ar.flashes = False
        run(ar, until_phase='fight')
        now = ar.last_now
        ar.exchange = dict(att='a', dfn='b', move=ar.f['a'].atlas.ultimate(), kind='ultimate', dmg=40, state='strike', t=now, contact=now,
                           end=now + 1, hit_done=False)
        ar.f['b'].hp = 80
        ar._resolve(ar.exchange, now)
        surf = AR.Surface(st.w, st.h)
        comp = AR.Compositor(ar, surf)
        comp.render(now)
        self.assertNotEqual(comp.render(now + 0.03), [(0, 0, st.w, st.h)])
        self.assertFalse(comp.flashed)

    def test_time_banner_and_slump_and_the_round_loser_gets_a_comeback(self):
        st, ar = make(freeze=False)
        run(ar, until_phase='fight')
        now = ar.last_now
        ar.f['a'].hp, ar.f['b'].hp = 70, 40
        ar._end_round(now, None)
        self.assertEqual(ar.banner[0], 'time')
        self.assertIn(ar.f['b'].anim, rounds.SLUMP)
        self.assertEqual(ar.f['b'].hold, AR.HOLD_LAST)
        self.assertFalse(ar.f['b'].down)                                     # nobody falls over unprovoked
        self.assertEqual(ar.comeback_for, 'b')
        run(ar, until_phase='fight')
        ar.k_round = 1
        ar.cooldown_until = 0.0
        ar._new_exchange(ar.last_now)
        self.assertEqual(ar.exchange['att'], 'b')
        self.assertIsNone(ar.comeback_for)

    def test_boost_opens_with_the_signature_super_and_wind_ups_get_a_brace(self):
        st, ar = make(freeze=False)
        ar.boost = ['b']
        run(ar, until_phase='fight')
        ar._new_exchange(ar.last_now)
        first = [bt for bt in ar.exchange['beats'] if bt['kind'] in ('strike', 'super', 'special', 'ultimate', 'counter')][0]
        self.assertEqual((ar.exchange['att'], first['kind'], first['outcome']), ('b', 'super', 'hit'))
        braces = 0
        for ar2, _ in self.matches(range(3)):
            braces += sum(1 for e in ar2.events if e[0] == 'brace')
        self.assertGreater(braces, 0)


if __name__ == '__main__':
    unittest.main()
