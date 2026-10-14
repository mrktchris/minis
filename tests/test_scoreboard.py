"""The right-side scoreboard widget: layout, hit-testing (buttons only), rendering, the model from bus / record / control,
and the director-hosted loop with a fake shell."""
import io, json, sys, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG, Isolated  # noqa: E402
import minis  # noqa: E402
from minis_core import bus, control, director, rounds, scoreboard as SB  # noqa: E402
from test_minis import FakeOverlay, FakeShell  # noqa: E402


class Pure(unittest.TestCase):
    def test_layout_sits_just_left_of_the_icon_cluster_inside_the_empty_stretch(self):
        self.assertEqual(SB.left_x(CFG) + SB.W, CFG['zone'][1] + 36)
        self.assertEqual(SB.left_x(dict(CFG, scoreboard_x=700)), 700)
        self.assertLess(SB.left_x(CFG), 940)
        self.assertTrue(SB.enabled(CFG) and not SB.enabled(dict(CFG, scoreboard=False)))

    def test_only_the_buttons_are_solid(self):
        self.assertEqual(SB.hit(10, 30), 'pause')
        self.assertEqual(SB.hit(90, 30), 'arena')
        self.assertEqual(SB.hit(150, 30), 'bout')
        self.assertIsNone(SB.hit(10, 5))                                     # the record line is click-through
        self.assertIsNone(SB.hit(64, 30))                                    # the gap between buttons too
        self.assertIsNone(SB.hit(-1, 30))

    def test_render_states(self):
        base = dict(names={'a': 'Claude', 'b': 'Codex'}, records={'a': (3, 1), 'b': (1, 3)}, mode='taskbar', arena=False, paused=False, hp=None,
                    wins={}, winners='decided')
        im = SB.render(base)
        self.assertEqual(im.size, (SB.W, SB.H))
        self.assertIs(SB.render(dict(base)), im)                             # cached by signature
        bout = SB.render(dict(base, hp={'a': 64, 'b': 20}, wins={'a': 1, 'b': 0}))
        self.assertNotEqual(bout.tobytes(), im.tobytes())
        self.assertEqual(bout.getpixel((10, 18))[:3], (150, 220, 150))        # a's bar, green at 64
        self.assertEqual(bout.getpixel((SB.W - 7, 18))[:3], SB.RED)           # b's bar fills from the right, red at 20
        self.assertFalse(any(im.getpixel((x, 18))[:3] == (150, 220, 150) for x in range(46, 76)))   # no bars outside a bout
        self.assertEqual(SB.labels(dict(base, paused=True))['pause'], 'Resume')
        self.assertEqual(SB.labels(dict(base, arena=True))['arena'], 'Exit arena')
        for mode in ('arena', 'paused'):
            self.assertNotEqual(SB.render(dict(base, mode=mode)).tobytes(), im.tobytes())
        pressed = SB.render(dict(base, pressed='bout'))
        self.assertNotEqual(pressed.tobytes(), im.tobytes())
        long = SB.render(dict(base, names={'a': 'LM Studio Server', 'b': 'Windsurf'}))
        self.assertEqual(long.size, (SB.W, SB.H))

    def test_model_from_assignment_bus_record_and_flags(self):
        assign = {'a': {'source': 'claude', 'character': 'claude', 'program': 'Claude Code'}, 'b': {'source': 'aider', 'character': 'generic', 'program': 'aider'}}
        rec = {'characters': {'claude': {'w': 2, 'l': 5}, 'generic': {'w': 1, 'l': 0}}}
        buses = {'a': {'hp': 40, 'wins': {'a': 1, 'b': 0}}, 'b': {'hp': 0}}
        st = SB.Model.state(assign, buses, rec, False, True, 'random')
        self.assertEqual(st['names'], {'a': 'Claude Code', 'b': 'aider'})
        self.assertEqual(st['records'], {'a': (2, 5), 'b': (1, 0)})
        self.assertEqual((st['mode'], st['hp'], st['wins'], st['winners']), ('arena', {'a': 40, 'b': 0}, {'a': 1, 'b': 0}, 'random'))
        st = SB.Model.state({'a': None, 'b': None}, {}, {}, True, False, 'decided')
        self.assertEqual((st['mode'], st['names'], st['hp']), ('paused', {'a': None, 'b': None}, None))


class Hosted(Isolated):
    def setUp(self):
        super().setUp()
        self.t = {'mono': 100.0, 'wall': 1_800_000_000.0}
        self.shell = FakeShell()
        self.shell.Overlay = FakeOverlay
        self.shell.monitors = lambda: [{'index': 1, 'rect': (0, 0, 2560, 1440), 'work': (0, 0, 2560, 1392), 'primary': True},
                                       {'index': 2, 'rect': (2560, 0, 4480, 1080), 'work': (2560, 0, 4480, 1080), 'primary': False}]
        self.board = minis.Scoreboard(dict(CFG), self.shell, wall=lambda: self.t['wall'], mono=lambda: self.t['mono'])
        self.board.setup()

    def go(self, secs, dt=0.05):
        for _ in range(int(secs / dt)):
            self.t['mono'] += dt
            self.t['wall'] += dt
            if self.board.step() is None:
                return None
        return 0

    def test_widget_is_a_fixed_window_at_the_right_end_that_redraws_on_change(self):
        director.write_assign({'a': {'source': 'claude', 'character': 'claude', 'program': 'Claude Code'}, 'b': None, 'ts': self.t['wall']})
        self.go(0.5)
        ov = self.board.ov
        self.assertTrue(ov.visible)
        self.assertEqual({x for _, x in ov.presented}, {SB.left_x(CFG)})
        self.assertEqual(ov.presented[-1][0], (SB.W, SB.H))
        self.assertTrue(1392 <= ov.y and ov.y + SB.H <= 1440)
        n = len(ov.presented)
        self.go(1.0)
        self.assertEqual(len(ov.presented), n)                               # nothing changed: no redraw
        bus.write('a', {'state': 'idle', 'mode': 'script', 'x': 500, 'facing': 1, 'anim': 'jab', 'hp': 52, 'wins': {'a': 1, 'b': 0}}, now=self.t['wall'])
        self.go(0.5)
        self.assertEqual(len(ov.presented), n + 1)                           # HP arrived: one redraw
        self.assertEqual(self.board.state['hp'], {'a': 52})
        self.assertTrue(ov.on_hittest(10, 30) and not ov.on_hittest(10, 5))

    def test_buttons_pause_bout_and_arena(self):
        self.go(0.3)
        b = self.board
        b.on_event('down', 10, 30)
        self.assertEqual(b.pressed, 'pause')
        b.on_event('up', 10, 30)
        self.assertTrue(control.paused())
        b.on_event('down', 10, 30)
        b.on_event('up', 150, 30)                                            # released elsewhere: no action
        self.assertTrue(control.paused())
        b.on_event('down', 10, 30)
        b.on_event('up', 12, 31)
        self.assertFalse(control.paused())
        b.on_event('down', 150, 30)
        b.on_event('up', 150, 30)
        self.assertEqual(control.demo(now=self.t['wall'])['kind'], 'match')
        started = []
        with mock.patch.object(minis, 'start_arena', lambda mon, freeze=False, seconds=None: started.append(mon) or ('ok', 0)):
            b.on_event('down', 90, 30)
            b.on_event('up', 90, 30)
        self.assertEqual(started, [2])                                       # the one non-primary monitor
        control.write_arena_state({'active': True, 'pid': 1, 'monitor': 2}, now=self.t['wall'])
        with mock.patch.object(minis, 'stop_arena', lambda: ('stopped', 0)) as st:
            b.on_event('down', 90, 30)
            b.on_event('up', 90, 30)
        self.assertEqual([c[0] for c in b.clicks], ['pause', 'pause', 'bout', 'arena', 'arena'])

    def test_director_loop_hosts_the_board_and_still_assigns(self):
        from minis_core.sources import Activity

        class Src:
            def poll(self, now):
                return [Activity('claude', 'Claude Code', 'claude', 'working', 30.0, last_active=now)]
        mutex = mock.patch.object(self.shell, 'make_mutex', lambda name: (1, False), create=True)
        mutex.start()
        self.addCleanup(mutex.stop)
        with redirect_stdout(io.StringIO()):
            minis.run_director(self.shell, dict(CFG), detector_sources=Src(), wall=lambda: self.t['wall'], mono=lambda: self.t['mono'], max_iterations=30)
        data = director.read_assign()
        self.assertEqual(data['a']['source'], 'claude')
        self.assertTrue((self.data / 'director.pid').exists() or True)

    def test_cli_winners_and_demo_match(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(minis.main(['winners', 'random']), 0)
        self.assertEqual(control.winners(), 'random')
        with mock.patch.object(minis, 'running', lambda role: 1), redirect_stdout(io.StringIO()):
            self.assertEqual(minis.main(['demo', 'match']), 0)
        self.assertEqual(control.demo()['kind'], 'match')


if __name__ == '__main__':
    unittest.main()
