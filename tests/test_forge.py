"""Desktop weapons (minis_core/forge.py, docs/ARENA.md "Forging"), headless and hermetic.

Nothing here grabs the real screen: every "screen" is a synthetic image made in this file (a noise pattern no art uses),
and grab_monitor itself refuses under MINIS_TESTING.  The privacy tests patch every write path a process has (open, Path
writes, os.write, Image.save, json, logging) during a real headless arena run and prove no captured pixel reaches any."""
import builtins, collections, io, json, logging, os, pickle, random, sys, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG, Isolated  # noqa: E402
from PIL import Image  # noqa: E402
from minis_core import arena as AR, control, forge as FG, fx  # noqa: E402
from minis_core.atlas import Library  # noqa: E402

LIB = Library(hd=True)
FX = fx.default()
MON = (0, 0, 1280, 720)
FLOOR = 672
WINS = [(21, 120, 230, 640, 600), (22, 700, 300, 1180, 640)]
PALETTE_N = 4096


def signature(w=1280, h=720, seed=9):
    """A synthetic 'screen' that is obviously not one: 4x4 blocks, each one of PALETTE_N random colours (blocks survive the
    weapon's resampling exactly, so the colours stay recognisable wherever they end up)."""
    rnd = random.Random(seed)
    pal = [(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(PALETTE_N)]
    small = Image.new('RGB', (w // 4, h // 4))
    small.putdata([pal[rnd.randrange(PALETTE_N)] for _ in range((w // 4) * (h // 4))])
    return small.resize((w, h), Image.NEAREST).convert('RGBA'), set(pal)


SIG, SIG_COLORS = signature()


def sig_pixels(im):
    """How many opaque pixels of `im` carry a signature colour next to another one: real pixels come in runs, a lone match
    is a coincidence of the art's own colours."""
    raw = im.convert('RGBA').tobytes()
    n = 0
    prev = False
    w = im.width
    for k, i in enumerate(range(0, len(raw), 4)):
        cur = raw[i + 3] == 255 and (raw[i], raw[i + 1], raw[i + 2]) in SIG_COLORS
        if cur and prev:
            n += 1
        prev = cur and (k + 1) % w != 0
    return n


def chunks(img, n=160, size=12, seed=3):
    """Byte runs of the signature in every raw encoding a leak could use (RGBA, RGB, BGRA)."""
    rnd = random.Random(seed)
    out = []
    for mode, raw in (('RGBA', img.tobytes()), ('RGB', img.convert('RGB').tobytes()),
                      ('BGRA', img.tobytes('raw', 'BGRA'))):
        for _ in range(n):
            i = rnd.randrange(0, len(raw) - size)
            out.append(raw[i:i + size])
    return out


def screen(img=SIG, wins=WINS):
    st = AR.Stage(MON, wins, floor_y=FLOOR)
    return FG.ScreenImage(img, rects=[(w['id'], w['l'], w['t'], w['r'], w['b']) for w in st.windows])


def arena(seed=3, chars=('claude', 'knight'), forge=True, scr='sig', **options):
    st = AR.Stage(MON, WINS, floor_y=FLOOR)
    s = screen() if scr == 'sig' else scr
    ar = AR.Arena(st, {'a': LIB[chars[0]], 'b': LIB[chars[1]]}, FX, seed=seed, now=0.0, record=lambda *a, **k: None, options=options,
                  screen=s, forge=forge)
    ar.flashes = True
    return st, ar


def step(ar, secs, comp=None, until=None, fps=30):
    now = ar.last_now
    for _ in range(int(secs * fps)):
        now += 1.0 / fps
        ar.tick(now)
        if comp is not None:
            comp.render(now)
        if until is not None and until(ar):
            break
    return now


def to_fight(ar):
    step(ar, 30, until=lambda ar: ar.phase == 'fight')
    ar.exchange, ar.cooldown_until, ar.next_hazard = None, 1e9, 1e9


class Shapes(unittest.TestCase):
    def test_every_roster_character_has_a_family_and_each_family_its_shape(self):
        for c in LIB.characters() if hasattr(LIB, 'characters') else FG.FAMILY_OF:
            self.assertIn(FG.family_for(LIB[c]), FG.FAMILIES, c)
        self.assertEqual(FG.family_for(LIB['knight']), 'greatsword')
        self.assertEqual(FG.family_for(LIB['cursor']), 'spear')
        self.assertEqual(FG.family_for(LIB['oni']), 'club')
        self.assertEqual(FG.family_for(LIB['codex']), 'shards')

        def bbox(fam):
            m, grip, cy = FG.silhouette(fam)
            x0, y0, x1, y1 = m.getbbox()
            return m, x1 - x0, y1 - y0, grip
        dims = {f: bbox(f) for f in FG.FAMILIES}
        self.assertGreater(dims['blade'][1] / dims['blade'][2], 5.0)               # a long thin strip
        self.assertGreater(dims['spear'][1], max(dims[f][1] for f in ('blade', 'greatsword', 'axe', 'club')))   # the longest
        self.assertLess(dims['club'][1], dims['blade'][1])                          # short and heavy
        self.assertGreater(dims['greatsword'][2], dims['blade'][2] * 1.6)            # a broad blade
        m = dims['axe'][0]
        col = lambda x: sum(1 for y in range(m.height) if m.getpixel((x, y)))
        self.assertGreater(col(m.width - FG.PAD - 46), 3 * col(FG.PAD + 20))         # the head at the end, the haft at the grip
        m = dims['spear'][0]
        self.assertLess(col.__call__(FG.PAD + 60) if False else sum(1 for y in range(m.height) if m.getpixel((FG.PAD + 60, y))), 12)   # thin shaft
        for f, (m, w, h, grip) in dims.items():
            self.assertTrue(m.getpixel((int(grip[0]), int(grip[1]))), f)              # the grip is on the weapon

    def test_pixels_are_clipped_to_the_silhouette_with_a_rim_and_cracks_grow(self):
        tex = SIG.crop((300, 300, 560, 334))
        art = FG.build_weapon('blade', tex, (255, 140, 40), seed=4)
        base, mask = art['levels'][0], art['mask']
        halo = mask.filter(__import__('PIL.ImageFilter', fromlist=['x']).MaxFilter(17))
        a = base.getchannel('A')
        for y in range(0, base.height):
            for x in range(0, base.width, 3):
                if not halo.getpixel((x, y)):
                    self.assertEqual(a.getpixel((x, y)), 0, (x, y))                    # nothing outside the shape (+ its glow)
        x, y = base.width // 2 + 20, int(art['cy'])                                    # the middle of the blade: the real pixels
        r, g, b, al = base.getpixel((x, y))
        self.assertIn((r, g, b), SIG_COLORS)
        self.assertGreater(sig_pixels(base), 1500)
        diffs = [sum(1 for p, q in zip(art['levels'][0].tobytes()[3::4], lv.tobytes()[3::4]) if p != q) +
                 sum(1 for p, q in zip(art['levels'][0].tobytes(), lv.tobytes()) if p != q) for lv in art['levels'][1:]]
        self.assertEqual(len(art['levels']), FG.CRACKS_TO_SHATTER + 1)
        self.assertTrue(diffs[0] < diffs[1] < diffs[2], diffs)                          # progressive cracks
        rim = [base.getpixel((x, y)) for x in range(base.width) for y in range(base.height)
               if not mask.getpixel((x, y)) and mask.filter(__import__('PIL.ImageFilter', fromlist=['x']).MaxFilter(3)).getpixel((x, y))][:50]
        self.assertTrue(all(p[0] > 200 and p[1] > 200 and p[2] > 200 for p in rim), rim[:5])   # a bright rim: reads on any desktop

    def test_shape_mode_textures_carry_no_pixels(self):
        tex = FG.shape_texture((200, 40), 3, 'glass')
        self.assertEqual(sig_pixels(tex), 0)
        art = FG.build_weapon('greatsword', tex, (70, 170, 255))
        self.assertEqual(sig_pixels(art['levels'][0]), 0)


class Lifecycle(unittest.TestCase):
    def test_cut_hole_lift_morph_arm_swing_crack_shatter_debris(self):
        st, ar = arena()
        to_fight(ar)
        surf = AR.Surface(st.w, st.h)
        comp = AR.Compositor(ar, surf)
        F = ar.forge
        job = F.start('a', 'weapon', ar.last_now)
        self.assertIsNotNone(job)
        self.assertTrue(job.pixels)
        stages, morph = [], set()

        def watch(ar):
            if not stages or stages[-1] != job.stage:
                stages.append(job.stage)
            if job.stage == 'morph':
                morph.add(min(FG.MORPH_FRAMES - 1, int((ar.last_now - job.t_stage) * 30)))
            return job.done
        step(ar, 3.0, comp, until=watch)
        self.assertEqual(stages, ['outline', 'cut', 'lift', 'morph', 'settle'])
        self.assertTrue(6 <= FG.MORPH_FRAMES <= 10)
        self.assertGreaterEqual(len(morph), FG.MORPH_FRAMES - 1)
        frames = [F._morph_frame(job, i)[0] for i in range(FG.MORPH_FRAMES)]
        self.assertEqual(len({f.tobytes()[:4000] + bytes(f.size[0]) for f in frames}), FG.MORPH_FRAMES)   # every frame differs
        self.assertEqual(len(F.holes), 1)
        self.assertIn('a', F.weapons)
        w = F.weapons['a']
        self.assertEqual(sig_pixels(w.art['levels'][0]) > 0, True)                     # textured with the screen's pixels
        # a strike swings it: the angle goes up (wind-up), through the slash, back to rest
        t = ar.last_now
        F.on_strike('a', t, t + 0.3, t + 0.6)
        angs = [w.angle(t + k / 30.0) for k in range(0, 30)]
        self.assertGreater(max(angs), FG.REST + 40)
        self.assertLess(min(angs), 0)
        self.assertTrue(any(w.fast(t + k / 30.0) for k in range(30)))
        self.assertAlmostEqual(w.angle(t + 2.0), FG.REST)
        for k in range(FG.CRACKS_TO_SHATTER - 1):
            F.on_hit_landed('a', t)
            self.assertEqual(w.cracks, k + 1)
        self.assertIn('a', F.weapons)
        F.on_hit_landed('a', t)
        self.assertNotIn('a', F.weapons)                                              # shattered ...
        self.assertGreater(len(F.debris), 10)                                         # ... into its own pixels
        self.assertGreater(sum(sig_pixels(d[0]) for d in F.debris), 50)
        step(ar, 1.6, comp)
        self.assertEqual(F.debris, [])                                                # fell and faded
        self.assertEqual(surf.out_of_bounds, 0)
        self.assertEqual(ar.counts.get('forge_shatter'), 1)

    def test_uses_run_out_and_the_weapon_shatters(self):
        st, ar = arena()
        to_fight(ar)
        F = ar.forge
        F.start('b', 'weapon', ar.last_now)
        step(ar, 3.0, until=lambda ar: 'b' in F.weapons)
        t = ar.last_now + 1.0
        for _ in range(F.uses):
            F.on_exchange_end(('a', 'b'), t)
        self.assertNotIn('b', F.weapons)

    def test_slab_is_thrown_and_hits(self):
        st, ar = arena()
        to_fight(ar)
        hp = ar.f['b'].hp
        job = ar.forge.start('a', 'slab', ar.last_now)
        self.assertEqual(job.family, 'slab')
        step(ar, 3.0, until=lambda ar: 'forge_throw' in ar.counts and not ar.forge.slabs)
        self.assertIn('forge_throw', ar.counts)
        self.assertLess(ar.f['b'].hp, hp)

    def test_loose_piece_falls_lands_and_is_picked_up(self):
        st, ar = arena()
        to_fight(ar)
        F = ar.forge
        F.rng.random = lambda: 0.0                                                   # the chunk always breaks off
        win = st.windows[0]
        F.on_window_crack(win, ar.last_now, (win['l'] + win['r']) / 2, (win['t'] + win['b']) / 2, True)
        self.assertEqual(len(F.loose), 1)
        step(ar, 2.0, until=lambda ar: F.loose and F.loose[0]['state'] == 'rest')
        self.assertEqual(F.loose[0]['state'], 'rest')
        self.assertTrue(F.loose[0]['pixels'])
        self.assertEqual(F.kind_for('a'), 'pickup')
        F.start('a', 'pickup', ar.last_now)
        step(ar, 4.0, until=lambda ar: 'a' in F.weapons)
        self.assertIn('a', F.weapons)
        self.assertIn('forge_pickup', ar.counts)

    def test_shape_mode_without_a_grab(self):
        st, ar = arena(scr=None)
        to_fight(ar)
        self.assertFalse(ar.forge.pixels)
        job = ar.forge.start('a', 'weapon', ar.last_now)
        self.assertFalse(job.pixels)
        step(ar, 3.0, until=lambda ar: 'a' in ar.forge.weapons)
        self.assertFalse(ar.forge.weapons['a'].pixels)
        self.assertEqual(sig_pixels(ar.forge.weapons['a'].art['levels'][0]), 0)

    def test_a_window_that_moved_since_the_grab_is_forged_from_its_shape(self):
        st, ar = arena()
        to_fight(ar)
        moved = [(21, 140, 230, 660, 600), (22, 700, 300, 1180, 640)]
        st.update(moved)
        win = st.window_by_id(21)
        self.assertFalse(ar.forge.screen.matches(win))
        self.assertTrue(ar.forge.screen.matches(st.window_by_id(22)))
        tex, pixels = ar.forge._texture_from((200, 300, 300, 400), win, 'chunk', 1)
        self.assertFalse(pixels)
        self.assertEqual(sig_pixels(tex), 0)


class Scheduling(unittest.TestCase):
    def counts(self, intensity, seeds):
        out = []
        for seed in seeds:
            st, ar = arena(seed=seed, intensity=intensity)
            step(ar, 240, until=lambda ar: ar.phase == 'done')
            out.append(ar.counts.get('forge', 0))
        return out

    def test_forges_per_match_follow_the_intensity(self):
        self.assertEqual(self.counts('calm', range(3)), [1, 1, 1])
        n = self.counts('normal', range(5))
        self.assertTrue(all(2 <= c <= 4 for c in n), n)
        w = self.counts('wild', range(4))
        self.assertTrue(all(c >= 5 for c in w), w)

    def test_forge_off_means_zero_forges(self):
        for seed in range(3):
            st, ar = arena(seed=seed, forge=False)
            step(ar, 240, until=lambda ar: ar.phase == 'done')
            self.assertEqual([k for k in ar.counts if k.startswith('forge')], [], seed)
            self.assertFalse(ar.forge.pixels)

    def test_pacing_with_forging_on(self):
        lens, ko = [], 0
        for seed in range(10):
            st, ar = arena(seed=seed)
            step(ar, 240, until=lambda ar: ar.phase == 'done')
            lens += [r['dur'] for r in ar.rounds]
            ko += sum(r['ko'] for r in ar.rounds)
        self.assertLessEqual(sum(lens) / len(lens), 20.0, lens)
        self.assertGreater(ko / len(lens), 0.6)

    def test_the_stance_finisher_forges_inside_the_set_piece_and_the_cut_shatters_it(self):
        from minis_core import arena_setpieces as SP
        st, ar = arena(seed=3)
        to_fight(ar)
        ar.forge.target, ar.forge.done = 3, 0
        plan = ar._setpiece_plan('stance_finisher', ar.f['a'], ar.f['b'])
        ar._start_sp_setup('stance_finisher', 'a', 'b', plan, ar.last_now)
        armed = []
        step(ar, SP.SETPIECES['stance_finisher']['dur'] + 2.0, until=lambda ar: armed.append('a' in ar.forge.weapons) or
             (ar.counts.get('setpiece') and ar.sp is None))
        self.assertIn(True, armed)                                                    # forged during the stance
        self.assertNotIn('a', ar.forge.weapons)                                        # the finishing cut shattered it
        self.assertGreaterEqual(ar.counts.get('forge_shatter', 0), 1)


class Privacy(Isolated):
    def test_disable_mid_match_drops_the_grab_and_every_derived_image(self):
        st, ar = arena()
        to_fight(ar)
        surf = AR.Surface(st.w, st.h)
        comp = AR.Compositor(ar, surf)
        F = ar.forge
        F.start('a', 'weapon', ar.last_now)
        step(ar, 3.0, comp, until=lambda ar: 'a' in F.weapons)
        F.start('b', 'weapon', ar.last_now)
        step(ar, 0.5, comp)                                                           # b's piece is in the air
        self.assertGreater(sig_pixels(surf.canvas), 100)                              # positive control: the overlay shows real pixels
        scr = F.screen
        F.disable(ar.last_now)
        self.assertFalse(scr.available)
        self.assertIsNone(scr.region((0, 0, 50, 50)))
        self.assertEqual((F.weapons, F.jobs, F.loose, F.slabs, F.debris, len(F._cache)), ({}, [], [], [], [], 0))
        self.assertFalse(ar.state()['screen_pixels'])
        step(ar, 0.3, comp)
        self.assertEqual(sig_pixels(surf.canvas), 0)                                  # repainted without them
        step(ar, 30, comp)
        self.assertEqual(sum(1 for k, t, kw in ar.events if k == 'forge' and t > ar.last_now - 30), 0)   # and no new forge

    def test_screen_image_is_never_pickled_or_printed(self):
        s = screen()
        with self.assertRaises(TypeError):
            pickle.dumps(s)
        self.assertEqual(repr(s), '<ScreenImage 1280x720 in RAM>')
        self.assertNotIn('ScreenImage', json.dumps(AR.Arena(AR.Stage(MON, WINS, FLOOR), {'a': LIB['claude'], 'b': LIB['codex']}, FX,
                                                            screen=s, forge=True).state()))

    def test_grab_monitor_never_grabs_under_tests(self):
        import minis
        with mock.patch('PIL.ImageGrab.grab', side_effect=AssertionError('real screen grab')):
            self.assertIsNone(minis.grab_monitor(object(), (0, 0, 100, 100)))

    def test_no_captured_pixel_reaches_any_sink_during_a_real_arena_run(self):
        """The real arena process body (minis.run_arena) with forging on and a signature 'screen': every write path is
        recorded, and none may carry a byte run of the signature, an Image.save, or a pixel list in JSON."""
        import minis
        writes, saves, dumps, logs = [], [], [], []
        real_open = builtins.open

        class Rec(io.RawIOBase):
            def __init__(self, f):
                self.f = f

            def write(self, b):
                writes.append(b.encode('utf-8', 'replace') if isinstance(b, str) else bytes(b))
                return self.f.write(b)

            def __getattr__(self, n):
                return getattr(self.f, n)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()

        def rec_open(file, mode='r', *a, **k):
            f = real_open(file, mode, *a, **k)
            return Rec(f) if any(c in mode for c in 'wax+') else f

        def rec_write_bytes(self, data):
            writes.append(bytes(data))
            return len(data)

        def rec_write_text(self, data, *a, **k):
            writes.append(data.encode('utf-8', 'replace'))
            return real_open(self, 'w', encoding='utf-8').write(data)

        real_dumps = json.dumps

        def rec_dumps(obj, *a, **k):
            s = real_dumps(obj, *a, **k)
            dumps.append(s)
            return s

        class H(logging.Handler):
            def emit(self, r):
                logs.append(r.getMessage())
        h = H(level=logging.DEBUG)
        root = logging.getLogger()
        root.addHandler(h)
        old_level = root.level
        root.setLevel(logging.DEBUG)
        self.addCleanup(root.removeHandler, h)
        self.addCleanup(root.setLevel, old_level)
        clock = [1000.0]

        def tick():
            clock[0] += 1 / 30.0
            return clock[0]
        surf = AR.Surface(1280, 720)
        seen = {}
        real_arena = AR.Arena

        class Watch(real_arena):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                seen['ar'] = self
        with mock.patch.object(builtins, 'open', rec_open), mock.patch.object(Path, 'write_bytes', rec_write_bytes), \
                mock.patch.object(Path, 'write_text', rec_write_text), mock.patch.object(json, 'dumps', rec_dumps), \
                mock.patch.object(os, 'write', side_effect=AssertionError('os.write')), \
                mock.patch.object(Image.Image, 'save', lambda self, *a, **k: saves.append(self.size)), \
                mock.patch.object(AR, 'Arena', Watch), mock.patch.object(minis.time, 'sleep', lambda s: None):
            rc = minis.run_arena(dict(monitor=1, options={'intensity': 'wild'}), _Shell(), dict(CFG), monitor_rect=MON,
                                 windows_fn=lambda: list(WINS), surface=surf, wall=tick, mono=tick, max_seconds=80, seed=4, screen=SIG.copy())
        self.assertEqual(rc, 0)
        ar = seen['ar']
        self.assertGreaterEqual(ar.counts.get('forge', 0), 2, ar.counts)            # it really forged ...
        self.assertTrue(any(k == 'forge_armed' for k in ar.counts))
        self.assertFalse(ar.forge.pixels)                                           # ... and dropped the grab on the way out
        self.assertGreater(len(writes), 3)                                          # the heartbeats really went through the recorder
        self.assertEqual(saves, [])
        blob = b''.join(writes) + ''.join(dumps).encode() + '\n'.join(logs).encode()
        leaks = [c for c in chunks(SIG) if c in blob]
        self.assertEqual(leaks, [])
        def walk(v, where):                                                          # numbers and short names only
            if isinstance(v, str):
                self.assertLessEqual(len(v), 80, where)
                enc = v.encode('latin-1', 'replace') + v.encode('utf-8', 'replace')
                self.assertEqual([c for c in chunks(SIG, n=40, size=8) if c in enc], [], where)
            elif isinstance(v, dict):
                for k, x in v.items():
                    walk(x, f'{where}.{k}')
            elif isinstance(v, list):
                self.assertLessEqual(len(v), 64, where)
                for x in v:
                    walk(x, where)
        for s in dumps:
            self.assertNotRegex(s, r'\[(\s*\d+\s*,){64,}')
            walk(json.loads(s), 'json')
        hb = [json.loads(s) for s in dumps if '"screen_pixels"' in s]
        self.assertTrue(hb and all(isinstance(d['screen_pixels'], bool) for d in hb))


class _Shell:
    def make_mutex(self, *a, **k):
        return (object(), False)

    def __getattr__(self, name):
        raise AssertionError(f'shell.{name} called: the arena must not reach the desktop')


class Capture(Isolated):
    def test_arena_capture_refuses_while_pixels_are_held(self):
        import argparse
        import minis
        shell = mock.Mock()
        target = str(minis.cfgmod.data_dir() / 'cap.png')
        for st in ({'active': True, 'pid': 1, 'screen_pixels': True}, {'active': True, 'pid': 1}):
            control.write_arena_state(st)
            with mock.patch.object(minis.plat, 'shell', lambda: shell), mock.patch.object(minis.plat, 'is_mac', lambda: False):
                rc = minis.cmd_arena(argparse.Namespace(action='capture', path=target, freeze=False, monitor=None))
            self.assertEqual(rc, 2, st)
            shell.capture_window.assert_not_called()
        self.assertFalse(Path(target).exists())

    def test_forge_off_capture_has_no_forged_pixels_and_forge_on_would(self):
        import argparse
        import minis

        def overlay(forge):
            control.set_forge(forge)
            clock = [1000.0]

            def tick():
                clock[0] += 1 / 30.0
                return clock[0]
            surf = AR.Surface(1280, 720)
            peak = [0]
            real_render = AR.Compositor.render

            def render(self, now):
                r = real_render(self, now)
                if self.frames % 6 == 0 and any(j.stage in ('lift', 'windup') for j in self.arena.forge.jobs):
                    peak[0] = max(peak[0], sig_pixels(self.surface.canvas))
                return r
            with mock.patch.object(AR.Compositor, 'render', render), mock.patch.object(minis.time, 'sleep', lambda s: None):
                minis.run_arena(dict(monitor=1, options={'intensity': 'wild'}), _Shell(), dict(CFG), monitor_rect=MON, windows_fn=lambda: list(WINS),
                                surface=surf, wall=tick, mono=tick, max_seconds=40, seed=4, screen=SIG.copy())
            return surf, peak[0]
        surf_on, peak_on = overlay(True)
        self.assertGreater(peak_on, 200)                                            # positive control: forged pixels do show
        surf_off, peak_off = overlay(False)
        self.assertEqual(peak_off, 0)
        self.assertEqual(sig_pixels(surf_off.canvas), 0)
        control.write_arena_state({'active': True, 'pid': 1, 'screen_pixels': False})
        target = minis.cfgmod.data_dir() / 'cap.png'
        shell = mock.Mock()
        shell.find_own_window.return_value = 7
        shell.capture_window.return_value = surf_off.canvas
        with mock.patch.object(minis.plat, 'shell', lambda: shell), mock.patch.object(minis.plat, 'is_mac', lambda: False):
            rc = minis.cmd_arena(argparse.Namespace(action='capture', path=str(target), freeze=False, monitor=None))
        self.assertEqual(rc, 0)
        self.assertEqual(sig_pixels(Image.open(target)), 0)


class VisualOnly8(Isolated):
    """V7's VisualOnly7 with desktop weapons on: forging reads only the RAM image; no window API is ever called."""

    @unittest.skipUnless(sys.platform == 'win32', 'records the Win32 backend; the macOS arena is checked on a real Mac')
    def test_forging_calls_no_window_api(self):
        import minis
        from minis_win import shell as real_shell, arena_window
        calls = []

        class Rec:
            def __init__(self, tag):
                self.tag = tag

            def __getattr__(self, name):
                def f(*a, **k):
                    calls.append((self.tag, name))
                    return (object(), False) if name == 'make_mutex' else 0
                return f
        clock = [1000.0]

        def tick():
            clock[0] += 1 / 30.0
            return clock[0]
        surf = AR.Surface(1280, 720)
        seen = {}

        class Watch(AR.Arena):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                seen['ar'] = self
        with mock.patch.object(real_shell, 'user32', Rec('user32')), mock.patch.object(arena_window, 'user32', Rec('user32')), \
                mock.patch.object(AR, 'Arena', Watch), mock.patch.object(minis.time, 'sleep', lambda s: None):
            rc = minis.run_arena(dict(monitor=1, options={'intensity': 'wild'}), Rec('shell'), dict(CFG), monitor_rect=MON,
                                 windows_fn=lambda: list(WINS), surface=surf, wall=tick, mono=tick, max_seconds=40, seed=4, screen=SIG.copy())
        self.assertEqual(rc, 0)
        self.assertGreater(seen['ar'].counts.get('forge', 0), 0)
        self.assertEqual(sorted(set(calls)), [('shell', 'make_mutex')], calls[:10])


class MacPure(unittest.TestCase):
    def test_tile_keys(self):
        from minis_platform.rects import tile_keys
        self.assertEqual(tile_keys([(10, 10, 20, 20)], 1710, 1107), {(0, 0)})
        self.assertEqual(tile_keys([(120, 120, 140, 140)], 1710, 1107), {(0, 0), (128, 0), (0, 128), (128, 128)})
        self.assertEqual(len(tile_keys([(0, 0, 1710, 1107)], 1710, 1107)), 14 * 9)
        self.assertEqual(tile_keys([(-50, -50, -1, -1)], 100, 100), set())

    def test_badge_sits_left_of_the_notch_and_of_menu_bar_plates(self):
        from minis_mac import geometry as G
        frame, visible = (0, 0, 1710, 1107), (0, 0, 1710, 1070)
        x, y = G.menubar_badge_origin(frame, visible, 760.0, False, 128, 26, 4)
        self.assertEqual(x, 760 - 8 - G.BADGE)
        self.assertGreaterEqual(y, 2)
        px, _ = G.menubar_plate_origin('a', frame, visible, 760.0, 128, 26, 4)
        x2, _ = G.menubar_badge_origin(frame, visible, 760.0, True, 128, 26, 4)
        self.assertLessEqual(x2 + G.BADGE, px)
        x3, _ = G.menubar_badge_origin((0, 0, 1920, 1080), (0, 0, 1920, 1055), None, False, 128, 26, 4)
        self.assertEqual(x3, (1920 - G.BADGE) // 2)

    def test_a_tint_surface_gets_flashes_without_full_frames(self):
        st, ar = arena(forge=False)

        class Tinted(AR.Surface):
            def __init__(self, *a):
                super().__init__(*a)
                self.tints = []

            def tint(self, rgb, a):
                self.tints.append((rgb, round(a, 2)))
        surf = Tinted(st.w, st.h)
        comp = AR.Compositor(ar, surf)
        step(ar, 30, comp, until=lambda ar: ar.phase == 'fight')
        writes = []
        real = surf.write
        surf.write = lambda img, x, y: (writes.append(img.size), real(img, x, y))
        ar.fxp.flash_at(ar.last_now, seconds=0.1)
        step(ar, 0.1, comp)
        self.assertTrue(any(rgb == (255, 255, 255) for rgb, a in surf.tints), surf.tints)
        self.assertNotIn((st.w, st.h), writes)                                        # no full-frame repaint for the flash


if __name__ == '__main__':
    unittest.main()
