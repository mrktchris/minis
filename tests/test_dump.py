"""minis_core/dump.py (windows dump their own images) and tools/own_capture.py (composites them) - headless, temp data dirs."""
import json, sys, unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, Isolated, Clock  # noqa: F401  (sets sys.path)
from PIL import Image

from minis_core import dump
from minis_core.bus import write_json_atomic

sys.path.insert(0, str(ROOT / 'tools'))
import own_capture  # noqa: E402


class FakeOverlay:
    """The shell Overlay's contract: present(img, x=None) sizes the window to img * scale at (x, y)."""

    def __init__(self, x, y, scale=1):
        self.x, self.y, self.scale, self.visible = x, y, scale, True
        self.calls = 0

    def present(self, img, x=None):
        if x is not None:
            self.x = int(x)
        self.calls += 1
        return 'ok-%d' % self.calls

    def show(self, v):
        self.visible = v


def sprite(w, h, col):
    return Image.new('RGBA', (w, h), col)


class DumpBase(Isolated):
    def setUp(self):
        super().setUp()
        dump.reset()
        self.addCleanup(dump.reset)
        self.wall = Clock(1_000_000.0)
        self.mono = Clock(500.0)
        for name, val in (('_wall', self.wall), ('_mono', self.mono), ('AUTO_POLL', False)):
            p = mock.patch.object(dump, name, val)
            p.start()
            self.addCleanup(p.stop)

    def request(self, rid='t1', until=None, every_ms=100, **extra):
        data = dict(id=rid, until=self.wall() + 30 if until is None else until, every_ms=every_ms, **extra)
        self.assertTrue(write_json_atomic(dump.request_path(), data))
        self.mono.advance(1.0)                       # past the 0.5 s re-read throttle

    def tick(self, s):
        self.wall.advance(s)
        self.mono.advance(s)

    def files(self):
        return sorted(p.relative_to(self.data).as_posix() for p in self.data.rglob('*') if p.is_file())

    def dumps(self, rid='t1'):
        d = self.data / 'dump' / rid
        return sorted(d.glob('*.json')) if d.is_dir() else []


class TestWatch(DumpBase):
    def test_no_request_writes_nothing_and_passes_return_through(self):
        ov = FakeOverlay(10, 20)
        self.assertIs(dump.watch(ov, 'a'), ov)
        for _ in range(5):
            self.assertTrue(ov.present(sprite(8, 8, (255, 0, 0, 255)), x=12).startswith('ok-'))
            self.tick(0.2)
        dump.poll_once()
        self.assertEqual(self.files(), [])
        self.assertEqual(ov.x, 12)
        self.assertEqual(ov.present(sprite(8, 8, (1, 2, 3, 255))), 'ok-6')

    def test_expired_request_writes_nothing(self):
        ov = dump.watch(FakeOverlay(0, 0), 'a')
        self.request(until=self.wall() - 1)
        ov.present(sprite(8, 8, (255, 0, 0, 255)))
        dump.poll_once()
        self.assertEqual(self.files(), ['dump/request.json'])

    def test_malformed_id_writes_nothing(self):
        ov = dump.watch(FakeOverlay(0, 0), 'b')
        for bad in ('../escape', 'x' * 33, '', 'a b', 'a/b', '..', 7):
            self.request(rid=bad)
            ov.present(sprite(8, 8, (255, 0, 0, 255)))
            dump.poll_once()
            self.tick(0.3)
        self.assertEqual(self.files(), ['dump/request.json'])
        self.assertFalse((self.data / 'escape').exists())

    def test_garbage_request_file_writes_nothing(self):
        ov = dump.watch(FakeOverlay(0, 0), 'a')
        (self.data / 'dump').mkdir()
        dump.request_path().write_text('{not json', encoding='utf-8')
        self.mono.advance(1)
        ov.present(sprite(4, 4, (0, 0, 0, 255)))
        self.assertEqual(self.files(), ['dump/request.json'])

    def test_unknown_role_is_not_wrapped(self):
        ov = FakeOverlay(0, 0)
        orig = ov.present
        dump.watch(ov, 'arena')
        self.assertEqual(ov.present, orig)

    def test_active_request_png_and_json_per_role(self):
        a = dump.watch(FakeOverlay(300, 1300, scale=2), 'a')
        pa = dump.watch(FakeOverlay(8, 1396, scale=2), 'a-plate')
        sb = dump.watch(FakeOverlay(2300, 1396, scale=1), 'scoreboard')
        self.request(every_ms=100)
        ia, ip, isb = sprite(64, 70, (255, 0, 0, 255)), sprite(40, 20, (0, 255, 0, 255)), sprite(120, 24, (0, 0, 255, 255))
        self.assertEqual(a.present(ia, x=320), 'ok-1')
        pa.present(ip)
        sb.present(isb, x=2310)
        recs = {json.loads(p.read_text())['role']: json.loads(p.read_text()) for p in self.dumps()}
        self.assertEqual(set(recs), {'a', 'a-plate', 'scoreboard'})
        ra = recs['a']
        self.assertEqual((ra['x'], ra['y'], ra['w'], ra['h'], ra['scale'], ra['density']), (320, 1300, 128, 140, 2, 1))
        self.assertEqual((recs['scoreboard']['x'], recs['scoreboard']['w'], recs['scoreboard']['h']), (2310, 120, 24))
        self.assertEqual((recs['a-plate']['w'], recs['a-plate']['h']), (80, 40))
        png = self.data / 'dump' / 't1' / ra['png']
        self.assertTrue(png.is_file())
        with Image.open(png) as im:
            self.assertEqual(im.size, (64, 70))                  # the image as passed to present, not the scaled window
            self.assertEqual(im.convert('RGBA').getpixel((3, 3)), (255, 0, 0, 255))
        for p in self.data.rglob('*'):                           # everything under data/dump/<id>/ (+ the request)
            rel = p.relative_to(self.data).parts
            self.assertEqual(rel[0], 'dump')
            if p.is_file() and p.name != 'request.json':
                self.assertEqual(rel[1], 't1')

    def test_rate_limit_one_per_every_ms_per_role(self):
        a = dump.watch(FakeOverlay(0, 0), 'a')
        b = dump.watch(FakeOverlay(0, 0), 'b')
        self.request(every_ms=100)
        for _ in range(30):                                     # 30 presents per role over 0.3 s (every 10 ms)
            a.present(sprite(8, 8, (255, 0, 0, 255)))
            b.present(sprite(8, 8, (0, 255, 0, 255)))
            self.tick(0.01)
        roles = [json.loads(p.read_text())['role'] for p in self.dumps()]
        self.assertEqual(roles.count('a'), 3)
        self.assertEqual(roles.count('b'), 3)
        walls = sorted(json.loads(p.read_text())['wall'] for p in self.dumps() if p.name.startswith('a-'))
        self.assertTrue(all(w2 - w1 >= 0.1 - 1e-6 for w1, w2 in zip(walls, walls[1:])))

    def test_density_from_macos_hud_image(self):
        ov = dump.watch(FakeOverlay(0, 0, scale=1), 'b-plate')
        self.request()
        im = sprite(80, 40, (9, 9, 9, 255))
        im.info['density'] = 2
        with mock.patch.object(dump.sys, 'platform', 'darwin'):
            ov.present(im)
        r = json.loads(self.dumps()[0].read_text())
        self.assertEqual((r['w'], r['h'], r['density']), (40, 20, 2))

    def test_static_window_is_dumped_when_a_request_starts_and_hide_is_recorded(self):
        sb = dump.watch(FakeOverlay(50, 60), 'scoreboard')
        sb.present(sprite(10, 6, (1, 1, 1, 255)))                 # drawn before the request; never redrawn
        self.assertEqual(self.files(), [])
        self.request()
        dump.poll_once()
        recs = [json.loads(p.read_text()) for p in self.dumps()]
        self.assertEqual(len(recs), 1)
        self.assertTrue(recs[0]['visible'])
        self.tick(0.5)
        sb.show(False)                                          # hidden without a present
        dump.poll_once()
        recs = [json.loads(p.read_text()) for p in self.dumps()]
        self.assertEqual([r['visible'] for r in recs], [True, False])
        self.assertEqual(recs[0]['png'], recs[1]['png'])       # the hide record reuses the image
        self.assertEqual(len(list((self.data / 'dump' / 't1').glob('*.png'))), 1)

    def test_request_read_is_throttled(self):
        ov = dump.watch(FakeOverlay(0, 0), 'a')
        ov.present(sprite(4, 4, (0, 0, 0, 255)))                # caches "no request"
        write_json_atomic(dump.request_path(), {'id': 't1', 'until': self.wall() + 30, 'every_ms': 50})
        self.mono.advance(0.1)
        ov.present(sprite(4, 4, (0, 0, 0, 255)))
        self.assertEqual(self.dumps(), [])                       # inside the 0.5 s window: not yet seen
        self.mono.advance(0.5)
        ov.present(sprite(4, 4, (0, 0, 0, 255)))
        self.assertEqual(len(self.dumps()), 1)

    def test_a_failing_write_never_raises(self):
        ov = dump.watch(FakeOverlay(0, 0), 'a')
        self.request()
        with mock.patch.object(Image.Image, 'save', side_effect=OSError('disk full')):
            self.assertEqual(ov.present(sprite(4, 4, (0, 0, 0, 255))), 'ok-1')
        dump.poll_once()


def write_dump(d, role, wall, x, y, img, scale=1, visible=True):
    d.mkdir(parents=True, exist_ok=True)
    stem = f'{role}-{int(wall * 1000)}'
    img.save(d / f'{stem}.png')
    rec = dict(role=role, id=d.name, wall=wall, x=x, y=y, w=img.width * scale, h=img.height * scale, scale=scale, density=1,
               visible=visible, png=f'{stem}.png')
    (d / f'{stem}.json').write_text(json.dumps(rec), encoding='utf-8')


class TestCompositor(Isolated):
    def test_windows_at_their_rects_over_a_bar(self):
        d = self.data / 'dump' / 'c1'
        write_dump(d, 'a-plate', 100.0, 10, 1400, sprite(20, 10, (0, 255, 0, 255)), scale=2)
        write_dump(d, 'a', 100.0, 200, 1300, sprite(32, 70, (255, 0, 0, 255)), scale=2)
        write_dump(d, 'b', 100.0, 400, 1300, sprite(32, 70, (0, 0, 255, 255)), scale=2)
        write_dump(d, 'scoreboard', 100.0, 600, 1400, sprite(50, 20, (255, 255, 0, 255)))
        write_dump(d, 'a', 100.5, 250, 1300, sprite(32, 70, (255, 0, 255, 255)), scale=2)
        comp = own_capture.Compositor(d)
        box, bar = own_capture.plan(comp.records, [100.0, 100.5], taskbar=(0, 1392, 2560, 1440))
        x0, y0 = box[0], box[1]
        self.assertEqual(box, (10 - 8, 1300 - 8, 650 + 8, 1440))
        self.assertEqual(bar, (2, 1392, 658, 1440))
        im, rects = comp.frame(100.2, box, bar)
        self.assertEqual(im.size, (box[2] - box[0], box[3] - box[1]))
        px = lambda x, y: im.getpixel((x - x0, y - y0))[:3]     # noqa: E731
        self.assertEqual(px(220, 1350), (255, 0, 0))             # a at its first rect (2x scaled to 64 x 140)
        self.assertEqual(px(200 + 63, 1300 + 139), (255, 0, 0))
        self.assertEqual(px(450, 1350), (0, 0, 255))
        self.assertEqual(px(20, 1405), (0, 255, 0))
        self.assertEqual(px(640, 1410), (255, 255, 0))
        bar_px, bg_px = px(5, 1395), px(5, 1300 - 4)
        self.assertEqual(bg_px, own_capture.BG[:3])
        self.assertLess(sum(bar_px), sum(bg_px))                 # the bar is darker than the desktop
        self.assertEqual(rects['a'], (200 - x0, 1300 - y0, 264 - x0, 1440 - y0))
        im2, rects2 = comp.frame(100.6, box, bar)
        self.assertEqual(im2.getpixel((260 - x0, 1350 - y0))[:3], (255, 0, 255))   # the later dump of a, moved
        self.assertEqual(rects2['a'][0], 250 - x0)

    def test_hidden_window_is_left_out_and_bar_falls_back(self):
        d = self.data / 'dump' / 'c2'
        write_dump(d, 'a', 10.0, 100, 100, sprite(10, 10, (255, 0, 0, 255)))
        write_dump(d, 'b', 10.0, 200, 100, sprite(10, 10, (0, 0, 255, 255)), visible=False)
        comp = own_capture.Compositor(d)
        box, bar = own_capture.plan(comp.records, [10.0])
        self.assertEqual(bar, (92, 110 - 48, 118, 110))         # bottom 48 px of the union of the window rects
        _, rects = comp.frame(10.0, box, bar)
        self.assertEqual(set(rects), {'a'})


class TestToolPath(DumpBase):
    def test_full_tool_path_without_any_screen_capture(self):
        """main() end to end: the request it writes makes real watched overlays dump; ImageGrab.grab raising proves no
        screen is read on the way to the GIF, the still and the frames."""
        import PIL.ImageGrab
        ovs = {'a': dump.watch(FakeOverlay(300, 1300, scale=2), 'a'),
               'b': dump.watch(FakeOverlay(500, 1300, scale=2), 'b'),
               'a-plate': dump.watch(FakeOverlay(8, 1400, scale=2), 'a-plate'),
               'scoreboard': dump.watch(FakeOverlay(800, 1400), 'scoreboard')}
        ovs['scoreboard'].present(sprite(60, 24, (255, 255, 0, 255)))       # static: drawn once, before the request
        ovs['a-plate'].present(sprite(40, 12, (0, 255, 0, 255)))
        out = self.data / 'out'
        seen = {'n': 0}

        def fake_sleep(s):
            self.tick(s)
            dump.poll_once()                                     # what the poll thread does
            seen['n'] += 1
            ovs['a'].present(sprite(32, 70, (255, 0, 0, 255)), x=300 + seen['n'] * 4)
            ovs['b'].present(sprite(32, 70, (0, 0, 255, 255)), x=500 - seen['n'] * 4)

        with mock.patch.object(PIL.ImageGrab, 'grab', side_effect=AssertionError('screen capture attempted')), \
                mock.patch.object(own_capture, 'os_taskbar_rect', return_value=(0, 1392, 2560, 1440)):
            rc = own_capture.main(['--out', str(out), '--seconds', '3', '--fps', '5', '--demo', 'spar'],
                                  sleep=fake_sleep, wall=self.wall)
        self.assertEqual(rc, 0)
        self.assertFalse(dump.request_path().exists())          # the request is gone
        self.assertEqual([p.name for p in (self.data / 'dump').iterdir()], [])   # raw dumps deleted (no --keep)
        with Image.open(out / 'live-bout.gif') as g:
            total = 0
            for i in range(g.n_frames):                          # Pillow merges identical neighbours: count time, not frames
                g.seek(i)
                total += g.info['duration']
            self.assertEqual(total, 3000)
        with Image.open(out / 'live-taskbar.png') as s:
            self.assertEqual(s.size, tuple(json.loads((out / 'own-capture.json').read_text())['size']))
            self.assertGreater(s.height, 140)                    # whole 128 px-class fighters, not 48 taskbar rows
        man = json.loads((out / 'own-capture.json').read_text())
        self.assertEqual(len(list((out / 'frames').glob('*.png'))), 15)
        self.assertEqual(set(man['rects'][7]), {'a', 'b', 'a-plate', 'scoreboard'})
        from minis_core import control
        self.assertEqual(control.read().get('demo', {}).get('kind'), 'spar')

    def test_interrupt_removes_the_request(self):
        def boom(s):
            raise KeyboardInterrupt

        rc = own_capture.main(['--out', str(self.data / 'o'), '--seconds', '2'], sleep=boom, wall=self.wall)
        self.assertEqual(rc, 130)
        self.assertFalse(dump.request_path().exists())


class TestAnnotateLive(DumpBase):
    def test_doc_images_accepts_own_capture_frames(self):
        d = self.data / 'dump' / 'z'
        write_dump(d, 'a', 1.0, 100, 1300, sprite(32, 70, (255, 0, 0, 255)), scale=2)
        write_dump(d, 'scoreboard', 1.0, 300, 1400, sprite(40, 20, (255, 255, 0, 255)))
        cap = self.data / 'cap'
        written, man = own_capture.build(d, 1.0, 1.0, 4, cap, gif=None, still=None, taskbar=(0, 1392, 2560, 1440))
        self.assertTrue((cap / 'own-capture.json').is_file())
        sys.path.insert(0, str(ROOT / 'art'))
        import doc_images                                         # (its import points data_dir at its own temp dir;
        import shutil                                             #  Isolated's patch.stop restores the real one)
        self.addCleanup(shutil.rmtree, doc_images._TMP, True)
        out = self.data / 'img'
        with mock.patch.object(doc_images, 'OUT', out):
            out.mkdir()
            doc_images.annotate_live(cap)
        self.assertTrue((out / 'live-taskbar.png').is_file())
        self.assertTrue((out / 'live-bout.gif').is_file())


if __name__ == '__main__':
    unittest.main()


class RealRoles(DumpBase):
    """The real Fighter / Scoreboard objects (fake shell) with the dump hooks minis.py installs.  Live bug (2026-10-15):
    with a full-screen app up Windows reports QUNS_BUSY, the live copy hides every window and never presents, and the
    request produced nothing at all - not even a sign the windows exist - so own_capture said "no dumps arrived" while a
    match was being fought.  Now a never-drawn window answers with a hidden record and the tool says why."""

    def fighter(self, busy=False):
        import minis
        from minis_core import director
        from test_minis import FakeDetector, FakeShell
        from helpers import CFG
        director.write_assign({'a': {'source': 'claude', 'character': 'claude', 'program': 'Claude Code'},
                               'b': {'source': 'codex', 'character': 'codex', 'program': 'Codex'}, 'ts': self.wall()})
        sh = FakeShell()
        sh.fullscreen_busy = lambda: busy
        f = minis.Fighter('a', dict(CFG, fighter_size=128), sh, mono=self.mono, wall=self.wall,
                          detector_for=lambda src, cfg: FakeDetector(src))
        f.setup()
        return f

    def run_steps(self, f, n=12):
        for _ in range(n):
            self.tick(0.1)
            f.step()
            dump.poll_once()

    def test_a_visible_fighter_dumps_its_sprite_and_plate_from_its_own_presents(self):
        f = self.fighter()
        self.request(every_ms=50)
        self.run_steps(f)
        recs = [json.loads(p.read_text()) for p in self.dumps()]
        roles = {r['role'] for r in recs if r['visible'] and r['png']}
        self.assertEqual(roles, {'a', 'a-plate'})
        a = [r for r in recs if r['role'] == 'a' and r['visible']][-1]
        self.assertEqual(a['h'], 128 + 60)                              # the 128 px cell + the jump headroom
        self.assertGreater(sum(1 for r in recs if r['role'] == 'a'), 3)  # from present(), not only the first poll

    def test_a_hidden_fighter_answers_hidden_and_the_tool_says_why(self):
        f = self.fighter(busy=True)
        self.request(every_ms=50)
        self.run_steps(f)
        self.assertFalse(f.ov.visible)
        recs = [json.loads(p.read_text()) for p in self.dumps()]
        self.assertTrue(recs, 'a hidden window must still answer the request')
        self.assertEqual({r['role'] for r in recs}, {'a', 'a-plate'})
        self.assertFalse(any(r['visible'] or r['png'] for r in recs))
        msg = own_capture.hidden_reason(self.data / 'dump' / 't1')
        self.assertIn('stayed hidden', msg)
        self.assertIn('full-screen', msg)

    def test_the_real_scoreboard_dumps_too(self):
        import minis
        from test_minis import FakeShell
        from helpers import CFG
        sb = minis.Scoreboard(dict(CFG), FakeShell(), wall=self.wall, mono=self.mono)
        sb.setup()
        self.request(every_ms=50)
        for _ in range(12):
            self.tick(0.25)
            sb.step()
            dump.poll_once()
        recs = [json.loads(p.read_text()) for p in self.dumps()]
        self.assertTrue(any(r['role'] == 'scoreboard' for r in recs))
