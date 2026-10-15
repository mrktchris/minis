"""Effects library (fx.json / fx.png with graceful absence) and effect playback."""
import json, shutil, sys, tempfile, unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG  # noqa: E402
from minis_core import fx as fxmod, render  # noqa: E402
from minis_core.effects import EffectPlayer, anchor_point  # noqa: E402
from minis_core.atlas import Atlas, Library  # noqa: E402
from minis_core.telemetry import Snapshot  # noqa: E402


def sheet_fixture(tmp, res=2):
    """A tiny fx.png + fx.json in the work-order schema."""
    im = Image.new('RGBA', (96, 48), (0, 0, 0, 0))
    for i in range(3):
        for x in range(i * 32, i * 32 + 32):
            for y in range(32):
                im.putpixel((x, y), (255, 10 * i, 0, 255))
    for x in range(32):
        im.putpixel((x, 40), (0, 255, 0, 255))
    im.save(tmp / 'fx.png')
    meta = {'res': res, 'effects': {
        'hit_light': {'frames': [{'x': i * 32, 'y': 0, 'w': 32, 'h': 32, 'ms': 60} for i in range(3)], 'anchor': 'center', 'offset': [0, 0],
                      'loop': False, 'layer': 'front', 'hit_frame': 1, 'travel': None, 'shake': None},
        'beam_wave': {'frames': [{'x': 0, 'y': 32, 'w': 32, 'h': 16, 'ms': 100}, {'x': 32, 'y': 32, 'w': 64, 'h': 16, 'ms': 300}], 'anchor': 'hand',
                       'offset': [10, -2], 'loop': False, 'layer': 'front', 'hit_frame': 1, 'travel': {'speed': 200}, 'shake': {'frames': 6, 'amp': 4}},
        'broken': {'frames': [{'x': 90, 'y': 40, 'w': 32, 'h': 32, 'ms': 60}]},
    }}
    (tmp / 'fx.json').write_text(json.dumps(meta), encoding='utf-8')
    return tmp / 'fx.json'


class Loading(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='minis-fx-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_absent_sheet_gives_procedural_placeholders_for_everything(self):
        f = fxmod.Fx(paths=[self.tmp / 'nope.json'])
        self.assertEqual(f.loaded_from, [])
        for name in fxmod.GENERIC + ('beam_wave', 'spiral_orb', 'anything'):
            e = f.get(name)
            self.assertTrue(e.frames and e.procedural, name)
            self.assertFalse(f.has_art(name))
        for kind in fxmod.BANNERS:
            im = f.banner(kind)
            self.assertGreater(im.getchannel('A').getbbox()[2], 20, kind)
        self.assertEqual(len(f.get('letters').frames), 52)                     # 26 glyphs x 2 sizes
        self.assertIsInstance(f.letter(__import__('random').Random(1)), Image.Image)
        with self.assertRaises(ValueError):
            f.banner('nope')

    def test_sheet_is_read_in_the_work_order_schema(self):
        f = fxmod.Fx(paths=[sheet_fixture(self.tmp)])
        self.assertEqual(f.res, 2)
        self.assertTrue(f.has_art('hit_light') and f.has_art('beam_wave'))
        e = f.get('beam_wave')
        self.assertEqual((e.anchor, e.offset, e.layer, e.hit_frame, e.travel, e.shake), ('hand', (10, -2), 'front', 1, {'speed': 200.0}, {'frames': 6, 'amp': 4.0}))
        self.assertEqual([im.size for im, ms in e.frames], [(32, 16), (64, 16)])
        self.assertEqual(e.total_ms, 400)
        self.assertEqual(e.locate(50), (0, False))
        self.assertEqual(e.locate(150), (1, False))
        self.assertEqual(e.locate(999), (1, True))
        self.assertEqual(f.get('hit_light').frames[1][0].getpixel((3, 3)), (255, 10, 0, 255))
        self.assertIn('fx.json:broken', f.errors)                            # a frame outside the sheet: that effect only
        self.assertTrue(f.get('dust').procedural)                            # missing generic: placeholder, no error
        self.assertEqual(f.get('hit_light').image(0, -1, 0.5).size, (16, 16))  # flipped + scaled, cached
        self.assertIs(f.get('hit_light').image(0, -1, 0.5), f.get('hit_light').image(0, -1, 0.5))

    def test_banner_reads_round_text_frames_in_order_and_named_overrides(self):
        im = Image.new('RGBA', (60, 10), (0, 0, 0, 0))
        im.save(self.tmp / 'fx.png')
        fr = [{'x': i * 10, 'y': 0, 'w': 10, 'h': 10, 'ms': 100} for i in range(6)]
        (self.tmp / 'fx.json').write_text(json.dumps({'effects': {'round_text': {'frames': fr[:5]}, 'ko_text': {'frames': fr[5:]},
                                                                  'fight': {'frames': [dict(fr[0], w=7)]}}}), encoding='utf-8')
        f = fxmod.Fx(paths=[self.tmp / 'fx.json'])
        self.assertEqual(f.banner('round2').size, (10, 10))
        self.assertEqual(f.banner('fight').size, (7, 10))                    # the named effect wins
        self.assertEqual(f.banner('ko').size, (10, 10))


class Playback(unittest.TestCase):
    def test_anchor_points_scale_with_res(self):
        self.assertEqual(anchor_point('ground', 100, 57, 1, 1), (100, 57))
        self.assertEqual(anchor_point('hand', 100, 57, 1, 1), (112, 33))
        self.assertEqual(anchor_point('hand', 100, 114, -1, 2), (76, 66))
        self.assertEqual(anchor_point('center', 100, 57, 1, 1), (100, 33))

    def test_player_scales_hd_effects_down_for_the_taskbar_and_travels(self):
        f = fxmod.Fx(paths=[])
        p = EffectPlayer(f, res=1, fps=30)
        i = p.spawn('beam_wave', 10.0, 100, 57, 1, owner='a')
        self.assertEqual(i.vx, 0)                                           # procedural beam: no travel -> stays put
        p.tick(10.0)
        pl = p.placements(10.05)
        self.assertEqual(len(pl), 1)
        im, lx, ty, layer, inst = pl[0]
        self.assertEqual(im.size, (f.get('beam_wave').frames[0][0].width // 2, f.get('beam_wave').frames[0][0].height // 2))
        self.assertEqual(layer, 'front')
        p.tick(99.0)
        self.assertEqual(p.placements(99.0), [])                            # finished effects are dropped

    def test_shake_decays_to_zero_and_fixed_frames_live_until_fade(self):
        f = fxmod.Fx(paths=[])
        p = EffectPlayer(f, res=2, fps=30)
        p.spawn_at('explosion', 0.0, 50, 50)
        p.tick(0.0)
        self.assertNotEqual(p.shake(0.03), (0, 0))
        self.assertEqual(p.shake(5.0), (0, 0))
        inst = p.spawn_at('letters', 0.0, 10, 10, vx=100, vy=0, gravity=0, fade_ms=500)
        inst.data = {'frame': 7}
        p.tick(0.1)
        im, lx, ty, layer, i2 = [x for x in p.placements(0.1) if x[4] is inst][0]
        self.assertAlmostEqual(inst.x, 20, delta=0.5)
        p.tick(0.7)
        self.assertNotIn(inst, p.active)
        p.spawn_at('hit_light', 0.0, 1, 1)
        p.clear()
        self.assertEqual(p.active, [])

    def test_compose_draws_effects_in_layers_and_a_banner_clipped_to_the_cell(self):
        a = Atlas('claude')
        f = fxmod.Fx(paths=[])
        p = EffectPlayer(f, res=1, fps=30)
        p.spawn('dust', 0.0, 500, a.ground_y, 1)                            # back layer, at the feet
        p.spawn('hit_heavy', 0.0, 500, a.ground_y, 1)                       # front layer
        p.tick(0.0)
        view = dict(anim='idle', frame=0, x=500, facing=1, dim=False, proj=None, fx=p.placements(0.0), banner=(f.banner('ko'), 500), shake=(3, -2))
        im, x0 = render.compose(a, a, view, Snapshot('claude', 'idle', 20.0), 0.0, CFG, show_plate=False)
        self.assertEqual(im.height, 64)
        plain, x1 = render.compose(a, a, dict(view, fx=[], banner=None, shake=(0, 0)), Snapshot('claude', 'idle', 20.0), 0.0, CFG, show_plate=False)
        self.assertNotEqual(im.tobytes(), plain.tobytes())
        self.assertLessEqual(x0, x1 - 10)                                   # the banner / effects widen the canvas


class HD(unittest.TestCase):
    def test_hd_atlas_falls_back_to_2x_nearest_until_assets_hd_exists(self):
        a, h = Atlas('codex'), Atlas('codex', hd=True)
        self.assertEqual((a.res, h.res), (1, 2))
        self.assertEqual(h.cell, (128, 128))
        self.assertEqual(h.anchor(1), a.anchor(1) * 2)
        self.assertEqual(h.ground_y, a.ground_y * 2)
        fr, fh = a.frame_image('jab', 2, 1), h.frame_image('jab', 2, 1)
        self.assertEqual(fh.size, (128, 128))
        if h.upscaled:                                                      # the fallback is the 64 px frame doubled; real HD has its own shading
            self.assertEqual(fh.getpixel((60, 60)), fr.getpixel((30, 30)))
        self.assertEqual(h.meta['projectile']['speed'], a.meta['projectile']['speed'] * 2)
        self.assertEqual(h.total_ms('jab'), a.total_ms('jab'))
        if not h.upscaled:                                                  # the real HD build has landed
            self.assertEqual(h.meta.get('res'), 2)
        lib = Library(hd=True)
        self.assertEqual(lib['claude'].res, 2)
        self.assertEqual(lib['nobody'].res, 2)

    def test_a_res_2_atlas_on_disk_is_used_as_is(self):
        tmp = Path(tempfile.mkdtemp(prefix='minis-hd-'))
        self.addCleanup(shutil.rmtree, tmp, True)
        src = Path(__file__).resolve().parent.parent / 'assets' / 'claude'
        m = json.loads((src / 'anim.json').read_text(encoding='utf-8'))
        m.update(res=2, cell=[128, 128], ground_y=114, anchor={'R': 60, 'L': 66}, signature=dict(m['signature'], ultimate='reverse'))
        for k, v in m['sheets'].items():
            Image.open(src / v).resize((1024, 6144), Image.NEAREST).save(tmp / v)
        Image.open(src / m['projectile']['file']).resize((144, 40), Image.NEAREST).save(tmp / m['projectile']['file'])
        m['projectile'].update(w=48, h=40, speed=260)
        (tmp / 'anim.json').write_text(json.dumps(m), encoding='utf-8')
        h = Atlas('claude', tmp, hd=True)
        self.assertFalse(h.upscaled)
        self.assertEqual((h.res, h.cell, h.anchor(1), h.ground_y), (2, (128, 128), 60, 114))
        self.assertEqual(h.signature()['ultimate'], 'reverse')
        self.assertEqual(h.ultimate(), 'reverse')
        with self.assertRaises(ValueError):
            Atlas('claude', tmp, hd=False)                                  # a RES 2 atlas cannot serve the 64 px taskbar


class FightFeelV6(unittest.TestCase):
    def test_time_banner_and_the_winner_name_banner(self):
        f = fxmod.Fx(paths=[])
        t = f.banner('time')
        self.assertGreater(t.width, 10)
        n = f.banner('winner', name='Codex')
        self.assertGreater(n.width, f.banner('winner').width)                  # "CODEX WINS" is wider than "WINNER"
        self.assertIs(n, f.banner('winner', name='Codex'))                      # cached
        with self.assertRaises(ValueError):
            f.banner('nope')

    def test_flashes_last_at_least_100_ms(self):
        from minis_core import effects
        self.assertGreaterEqual(effects.FLASH_S, 0.1)
        p = EffectPlayer(fxmod.Fx(paths=[]), res=1, fps=30)
        p.flash_at(1.0)
        self.assertGreater(p.flash(1.09), 0)                                    # still white three 30 fps redraws later
        self.assertEqual(p.flash(1.11), 0)


if __name__ == '__main__':
    unittest.main()
