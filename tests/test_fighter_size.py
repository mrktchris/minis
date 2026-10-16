"""fighter_size (64 | 96 | 128): geometry, art and controls of the taskbar fighters at each size.  Headless (fake shell)."""
import io, sys, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG, Isolated  # noqa: E402
import minis  # noqa: E402
from minis_core import config as cfgmod, control, director, lineup as L  # noqa: E402
from minis_core.atlas import Atlas  # noqa: E402
from test_minis import FakeDetector, FakeOverlay, FakeShell  # noqa: E402


class SizeValues(Isolated):
    def test_valid_sizes_and_fallback(self):
        self.assertEqual(cfgmod.DEFAULTS['fighter_size'], 128)
        for v in (64, 96, 128, '96'):
            self.assertEqual(cfgmod.fighter_size_of(v), int(v))
        for v in (0, 100, None, 'big'):
            self.assertEqual(cfgmod.fighter_size_of(v), 128)
        self.assertEqual([cfgmod.feet_drop(s) for s in (64, 96, 128)], [0, 4, 7])

    def test_control_json_overrides_the_config(self):
        self.assertEqual(control.fighter_size(default=64), 64)
        self.assertTrue(control.set_fighter_size(96))
        self.assertEqual(control.fighter_size(default=64), 96)
        self.assertFalse(control.set_fighter_size(100))
        self.assertEqual(control.fighter_size(), 96)


class FighterAtSize(Isolated):
    def make(self, size, slot='a'):
        self.t = {'mono': 100.0, 'wall': 1_800_000_000.0}
        director.write_assign({'a': {'source': 'claude', 'character': 'claude', 'program': 'Claude Code'},
                               'b': {'source': 'codex', 'character': 'codex', 'program': 'Codex'}, 'ts': self.t['wall']})
        f = minis.Fighter(slot, dict(CFG, fighter_size=size), FakeShell(), mono=lambda: self.t['mono'], wall=lambda: self.t['wall'],
                          detector_for=lambda src, cfg: FakeDetector(src))
        f.setup()
        for _ in range(10):
            self.t['mono'] += 0.05
            self.t['wall'] += 0.05
            f.step()
        return f

    def test_window_grows_upward_and_keeps_the_feet_line(self):
        plates = set()
        for size in (64, 96, 128):
            f = self.make(size)
            drop = cfgmod.feet_drop(size)
            self.assertEqual(f.cell, size)
            hr = cfgmod.headroom_px(size)                                    # V7.1: jump headroom above the cell
            self.assertEqual(f.ov.y, 1440 - size + drop - hr, size)         # taskbar bottom 1440, scale 1
            self.assertTrue(f.ov.presented, size)
            (w, h), x = f.ov.presented[-1]
            self.assertEqual(h, size + hr)
            feet = f.ov.y + hr + Atlas('claude').ground_y * size // 64       # ground_y scales with the art
            self.assertLessEqual(abs(feet - (1440 - 64 + Atlas('claude').ground_y)), 1, size)
            plates.add((f.pov.x, f.pov.y))
        self.assertEqual(len(plates), 1)                                     # plates do not move with the size

    def test_brain_works_in_res1_px_inside_the_scaled_zone(self):
        for size in (64, 96, 128):
            z0, z1 = cfgmod.fight_zone(dict(CFG), size)
            f = self.make(size)
            k = size / 64.0
            if size == 64:
                self.assertIsNone(f.logic_zone())
            else:
                self.assertEqual(f.logic_zone(), (z0 / k, z1 / k))
            self.assertTrue(z0 - 1 <= f.brain.x * k <= z1 + 1, (size, f.brain.x))
            self.assertEqual(f.brain.atlas.res, 1)                           # logic always on the RES 1 atlas

    def test_drag_hit_box_scales_with_the_fighter(self):
        f = self.make(128)
        b = f.brain
        hip_screen = b.x * 2
        f.on_event('down', int(hip_screen - f.ov.x / f.ov.scale) + 20, 40)   # 20 screen px = 10 brain px from the hip
        self.assertTrue(f.st['drag'])

    def test_hd_view_maps_positions_and_clamps_frames(self):
        base, hd = Atlas('claude'), Atlas('claude', hd=True)
        n = len(hd.anim['idle']['frames'])
        v = dict(anim='idle', frame=n + 5, x=100.5, facing=1, dim=False, proj={'x': 50, 'dir': 1, 'frame': 0}, fx=[],
                 banner=None, shake=(1, -1))
        out = minis.hd_view(v, hd, base)
        self.assertEqual(out['x'], 201.0)
        self.assertEqual(out['frame'], n - 1)
        self.assertEqual(out['proj']['x'], 100)
        self.assertEqual(out['shake'], (2, -2))
        from PIL import Image
        im = Image.new('RGBA', (5, 3))
        out = minis.hd_view(dict(v, fx=[(im, 10, 4, 'front', 'x')], banner=(im, 30)), hd, base)
        self.assertEqual(out['fx'][0][0].size, (10, 6))
        self.assertEqual(out['fx'][0][1:], (20, 8, 'front', 'x'))
        self.assertEqual(out['banner'][1], 60)

    def test_96_is_the_hd_render_reduced(self):
        from PIL import Image
        im = Image.new('RGBA', (128, 128), (255, 0, 0, 255))
        s = minis.shrink(im, 0.75)
        self.assertEqual(s.size, (96, 96))
        self.assertEqual(s.getpixel((48, 48)), (255, 0, 0, 255))


class SizeControls(Isolated):
    def test_menu_has_a_size_submenu(self):
        items, actions = L.fighter_menu('a', {}, control.lineup(), dict(size=96), [])
        sub = dict((it[0], it[1]) for it in items if it and isinstance(it[1], list))['Fighter size']
        self.assertEqual([s[1] for s in sub], ['64 px', '96 px (HD)', '128 px (HD)'])
        self.assertEqual([s[2]['checked'] for s in sub], [False, True, False])
        self.assertEqual(actions[L.SIZE_BASE + 128], ('size', 128))

    def test_menu_choice_saves_and_restarts(self):
        t = {'mono': 100.0, 'wall': 1_800_000_000.0}
        f = minis.Fighter('a', dict(CFG, fighter_size=64), FakeShell(), mono=lambda: t['mono'], wall=lambda: t['wall'],
                          detector_for=lambda src, cfg: FakeDetector(src))
        f.setup()
        f.ov.menu_choice = L.SIZE_BASE + 96
        calls = []
        with mock.patch.object(minis, 'restart_all', lambda: calls.append(1) or True):
            f.open_menu()
        self.assertEqual(control.fighter_size(), 96)
        self.assertEqual(calls, [1])

    def test_cli_size(self):
        with mock.patch.object(minis, 'running', lambda role: None), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(minis.main(['size', '96']), 0)
        self.assertEqual(control.fighter_size(), 96)
        self.assertIn('96 px', out.getvalue())
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), mock.patch('sys.stderr', io.StringIO()):
            minis.main(['size', '100'])


if __name__ == '__main__':
    unittest.main()
