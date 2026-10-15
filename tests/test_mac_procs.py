"""macOS process layer (minis_mac.procs) and the CLI's mac paths in minis.py, tested on any OS with canned `ps` output,
fake kill() and a patched platform.  Nothing here starts, signals or inspects a real process."""
import os, signal, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CFG, ROOT, Isolated  # noqa: E402
import minis  # noqa: E402
import minis_platform as plat  # noqa: E402
from minis_mac import procs as P  # noqa: E402

TABLE = """\
    1     0   1:02.50 Wed Oct 15 09:00:00 2026     /sbin/launchd
  501     1   0:01.23 Wed Oct 15 10:00:00 2026     /Applications/Cursor.app/Contents/MacOS/Cursor
  502   501 1:02:03.40 Wed Oct  5 10:00:01 2026     /Applications/Cursor.app/Contents/Frameworks/Cursor Helper (Renderer).app/Contents/MacOS/Cursor Helper (Renderer)
  777     1   0:00.05 Thu Oct 16 08:15:42 2026     /opt/homebrew/bin/node
garbage line
"""


class PsParsing(unittest.TestCase):
    def test_cputime_formats(self):
        self.assertAlmostEqual(P.parse_cputime('0:01.23'), 1.23)
        self.assertAlmostEqual(P.parse_cputime('12:34.5'), 754.5)
        self.assertAlmostEqual(P.parse_cputime('1:02:03'), 3723.0)
        self.assertAlmostEqual(P.parse_cputime('2-01:00:00'), 2 * 86400 + 3600)
        self.assertIsNone(P.parse_cputime(''))
        self.assertIsNone(P.parse_cputime('x:y'))

    def test_table_rows_with_spaces_in_paths(self):
        rows = {r['pid']: r for r in P.parse_ps_table(TABLE)}
        self.assertEqual(sorted(rows), [1, 501, 502, 777])
        self.assertEqual(rows[501]['name'], 'cursor')
        self.assertEqual(rows[502]['name'], 'cursor helper (renderer)')
        self.assertTrue(rows[502]['path'].endswith('MacOS/Cursor Helper (Renderer)'))
        self.assertEqual(rows[502]['ppid'], 501)
        self.assertAlmostEqual(rows[502]['cpu'], 3723.4)
        self.assertEqual(rows[502]['start'], 'Wed Oct 5 10:00:01 2026')
        self.assertEqual(rows[777]['name'], 'node')

    def test_info_reads_one_snapshot(self):
        calls = []
        snap = P.Snapshot(ps=lambda args: calls.append(args) or TABLE)
        with mock.patch.object(P, '_snap', snap):
            self.assertIn((501, 1, 'cursor'), P.list_processes())
            self.assertEqual(P.times(501), ('Wed Oct 15 10:00:00 2026', 1.23))
            self.assertTrue(P.image_path(501).endswith('/Cursor'))
        self.assertEqual(calls, [P.TABLE_ARGS])                        # path and times came from the same ps call

    def test_split_args_anchored_on_the_script(self):
        script = '/Users/me/my projects/taskbar-fighters/minis.py'
        py = '/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python'
        self.assertEqual(P.split_ps_args(f'{py} {script} run a', script), [py, script, 'run', 'a'])
        self.assertEqual(P.split_ps_args(f'{py} {script}', script), [py, script])
        self.assertEqual(P.split_ps_args('node /x/cli.js --flag', None), ['node', '/x/cli.js', '--flag'])
        self.assertEqual(P.split_ps_args('', script), [])

    def test_argv_via_ps(self):
        self.assertEqual(P.argv(5, None, ps=lambda a: 'python3 /r/minis.py director\n'), ['python3', '/r/minis.py', 'director'])
        self.assertIsNone(P.argv(5, None, ps=lambda a: ''))


class Signals(unittest.TestCase):
    def test_alive(self):
        def kill(pid, sig):
            if pid == 1:
                raise ProcessLookupError
            if pid == 2:
                raise PermissionError
        self.assertFalse(P.alive(1, kill))
        self.assertTrue(P.alive(2, kill))
        self.assertTrue(P.alive(3, kill))
        self.assertFalse(P.alive(0, kill))

    def _run(self, alive_seq, ours=True):
        sent, state = [], dict(n=0)

        def kill(pid, sig):
            sent.append(sig)

        def is_alive(pid):
            state['n'] += 1
            return alive_seq(state['n'], sent)
        t = dict(now=0.0)

        def sleep(s):
            t['now'] += s
        gone = P.terminate(42, still_ours=lambda: ours, grace_s=1.0, kill=kill, is_alive=is_alive, sleep=sleep, clock=lambda: t['now'])
        return gone, sent

    def test_sigterm_is_enough(self):
        gone, sent = self._run(lambda n, s: n < 3)
        self.assertTrue(gone)
        self.assertEqual(sent, [signal.SIGTERM])

    def test_stubborn_own_process_gets_sigkill(self):
        kill_sig = getattr(signal, 'SIGKILL', signal.SIGTERM)
        gone, sent = self._run(lambda n, s: kill_sig not in s or len(s) < 2)
        self.assertTrue(gone)
        self.assertEqual(sent, [signal.SIGTERM, kill_sig])

    def test_never_sigkill_a_pid_that_is_no_longer_ours(self):
        gone, sent = self._run(lambda n, s: True, ours=False)
        self.assertFalse(gone)
        self.assertEqual(sent, [signal.SIGTERM])


class SingleInstance(unittest.TestCase):
    def test_lock_file_per_role(self):
        d = Path(tempfile.mkdtemp(prefix='minis-lock-'))
        held = set()

        def flock(fd):
            if 'held' in held:
                raise BlockingIOError
            held.add('held')
        h, already = P.make_mutex('Local\\minis-a-1234abcd', d, flock=flock)
        self.assertFalse(already)
        self.assertTrue((d / 'Local_minis-a-1234abcd.lock').exists())
        h2, already2 = P.make_mutex('Local\\minis-a-1234abcd', d, flock=flock)
        self.assertTrue(already2)
        self.assertIsNone(h2)
        h.close()
        P._locks.remove(h)
        __import__('shutil').rmtree(d, True)


def as_mac():
    names = {'win32': 'win', 'darwin': 'mac'}
    return mock.patch('minis_platform.current', lambda platform=None: 'mac' if platform is None else names.get(platform, 'other'))


class CliOnMac(Isolated):
    PY = '/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python'

    def test_framework_python_and_versioned_names_count_as_python(self):
        script = str(ROOT / 'minis.py')
        self.assertTrue(minis.argv_is_ours([self.PY, script, 'run', 'a'], 'a'))
        self.assertTrue(minis.argv_is_ours(['/opt/homebrew/bin/python3.12', script, 'director'], 'director'))
        self.assertFalse(minis.argv_is_ours(['/usr/bin/perl', script, 'director'], 'director'))
        self.assertFalse(minis.argv_is_ours(['/opt/homebrew/bin/python3.x', script, 'director'], 'director'))

    def test_proc_argv_on_mac_splits_on_the_script(self):
        line = f'{self.PY} {ROOT / "minis.py"} run b'
        with as_mac(), mock.patch('minis_mac.procs.run_ps', lambda args, timeout=5.0: line + '\n'):
            argv = minis.proc_argv(123)
        self.assertEqual(argv, [self.PY, str(ROOT / 'minis.py'), 'run', 'b'])
        self.assertTrue(minis.argv_is_ours(argv, 'b'))

    def test_stop_on_mac_terminates_only_after_proving_ownership(self):
        (self.data / 'a.pid').write_text('4242')
        mine = [self.PY, str(ROOT / 'minis.py'), 'run', 'a']
        calls = []

        def terminate(pid, still_ours, **kw):
            calls.append((pid, still_ours()))
            return True
        with as_mac(), mock.patch.object(minis, 'pid_alive', lambda pid: True), \
                mock.patch.object(minis, 'proc_argv', lambda pid: mine), mock.patch('minis_mac.procs.terminate', terminate), \
                mock.patch('subprocess.run', lambda *a, **k: self.fail('taskkill on a Mac')), mock.patch('builtins.print'):
            rc = minis.cmd_stop(roles=('a',))
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [(4242, True)])
        self.assertFalse((self.data / 'a.pid').exists())

    def test_stop_on_mac_leaves_a_foreign_pid_alone(self):
        (self.data / 'a.pid').write_text('4242')
        with as_mac(), mock.patch.object(minis, 'pid_alive', lambda pid: True), \
                mock.patch.object(minis, 'proc_argv', lambda pid: ['/usr/bin/python3', '/elsewhere/minis.py', 'run', 'a']), \
                mock.patch('minis_mac.procs.terminate', lambda *a, **k: self.fail('killed a stranger')), mock.patch('builtins.print'):
            minis.cmd_stop(roles=('a',))
        self.assertTrue((self.data / 'a.pid').exists())

    def test_spawn_on_mac_uses_a_new_session_not_creation_flags(self):
        seen = {}
        with as_mac(), mock.patch('subprocess.Popen', lambda argv, **kw: seen.update(kw) or 'proc'):
            minis.spawn_detached(['python3', 'x'])
        self.assertTrue(seen['start_new_session'])
        self.assertNotIn('creationflags', seen)

    @unittest.skipUnless(sys.platform == 'win32', 'Win32 only')
    def test_spawn_on_windows_is_unchanged(self):
        seen = {}
        with mock.patch('subprocess.Popen', lambda argv, **kw: seen.update(kw) or 'proc'):
            minis.spawn_detached(['python', 'x'])
        self.assertEqual(seen['creationflags'], minis.DETACHED)
        self.assertNotIn('start_new_session', seen)

    def test_shortcut_on_mac_only_explains(self):
        with as_mac(), mock.patch('builtins.print') as pr:
            rc = minis.cmd_shortcut(mock.Mock(action='create', desktop=False))
        self.assertEqual(rc, 0)
        self.assertIn('autostart on', pr.call_args[0][0])

    def test_autostart_on_mac_writes_and_removes_the_launch_agent(self):
        home = Path(tempfile.mkdtemp(prefix='minis-home-'))
        self.addCleanup(__import__('shutil').rmtree, home, True)
        from minis_mac import launchd
        with as_mac(), mock.patch('builtins.print'):
            self.assertEqual(minis.cmd_autostart(mock.Mock(state='on'), home=home), 0)
            self.assertTrue(launchd.plist_path(home).exists())
            self.assertEqual(minis.cmd_autostart(mock.Mock(state='off'), home=home), 0)
        self.assertFalse(launchd.plist_path(home).exists())

    def test_autostart_refused_on_windows(self):
        with mock.patch('minis_platform.current', lambda platform=None: 'win'), mock.patch('builtins.print'):
            self.assertEqual(minis.cmd_autostart(mock.Mock(state='on')), 2)

    def test_print_startup_on_mac_prints_a_plist_and_installs_nothing(self):
        out = []
        with as_mac(), mock.patch('builtins.print', lambda *a, **k: out.append(' '.join(map(str, a)))), \
                mock.patch('minis_mac.launchd.install', lambda *a, **k: self.fail('installed')):
            minis.cmd_print_startup()
        text = '\n'.join(out)
        self.assertIn('<key>ProgramArguments</key>', text)
        self.assertIn('autostart off', text)

    def test_freeze_and_capture_refused_on_mac(self):
        fake = mock.Mock()
        with as_mac(), mock.patch('minis_platform.module', lambda part, platform=None: fake), mock.patch('builtins.print') as pr:
            rc = minis.cmd_arena(mock.Mock(action='start', freeze=True, monitor=1, seconds=None, seed=None, path=None))
            self.assertEqual(rc, 2)
            self.assertIn('Screen Recording', pr.call_args[0][0])
            rc = minis.cmd_arena(mock.Mock(action='capture', path='qa/x.png', freeze=False))
            self.assertEqual(rc, 2)
        fake.capture_window.assert_not_called()


class Drive(unittest.TestCase):
    def test_plain_loop_without_run_loop(self):
        seq = iter([0.0, 0.0, None])
        slept = []
        self.assertEqual(minis.drive(object(), lambda: next(seq), sleep=slept.append), 0)
        self.assertEqual(slept, [0.0, 0.0])

    def test_backend_run_loop_drives_the_step(self):
        class Sh:
            def run_loop(self, step):
                n = 0
                while step() is not None:
                    n += 1
                return n
        seq = iter([0.1, 0.1, 0.1, None])
        self.assertEqual(minis.drive(Sh(), lambda: next(seq), sleep=lambda s: self.fail('slept')), 3)


class FakeOverlay:
    def __init__(self, title, x, y, w, h, scale=1, **kw):
        self.x, self.y, self.w, self.h, self.scale = x, y, w * scale, h * scale, scale
        self.panel = mock.Mock()
        self.panel.isVisible.return_value = True
        self.panel.level.return_value = 25
        self.closed = False

    def present(self, img, x=None):
        if x is not None:
            self.x = x
        self.w, self.h = img.width * self.scale, img.height * self.scale
        return True

    def actual_rect(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def close(self):
        self.closed = True


class FakeMacShell:
    def __init__(self):
        self.made = []

    def taskbar_rect(self):
        return (0, 864, 1512, 912, 3)

    def taskbar_autohide(self):
        return False

    def screen_size(self):
        return (1512, 982)

    def monitors(self):
        return [dict(index=1, rect=(0, 0, 1512, 982), work=(0, 33, 1512, 912), primary=True, scale=2.0)]

    def dock_info(self):
        return dict(dock='bottom', rect=(0, 864, 1512, 912), edge=3, dock_top=912)

    def Overlay(self, *a, **k):
        o = FakeOverlay(*a, **k)
        self.made.append(o)
        return o

    def spin(self, s):
        self.spun = s


class SelftestAndDoctor(Isolated):
    def test_mac_selftest_reports_frames_and_closes_its_windows(self):
        sh, out = FakeMacShell(), []
        rc = minis.selftest_mac(None, shell=sh, seconds=0.0, out=out.append)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(sh.made), 2)
        self.assertTrue(all(o.closed for o in sh.made))
        self.assertTrue(all(o.actual_rect()[3] == 912 for o in sh.made))      # standing on the Dock's top edge
        self.assertIn('PASS', out[-1])

    def test_mac_selftest_fails_when_appkit_moves_a_window(self):
        sh, out = FakeMacShell(), []
        orig = FakeOverlay.actual_rect
        with mock.patch.object(FakeOverlay, 'actual_rect', lambda self: tuple(v + 30 for v in orig(self))):
            rc = minis.selftest_mac(None, shell=sh, seconds=0.0, out=out.append)
        self.assertEqual(rc, 1)
        self.assertIn('MISMATCH', '\n'.join(out))

    def test_doctor_report_is_complete_and_private(self):
        out = []
        rows = [dict(source='claude', program='Claude Code', character='claude', state='working', how='x'),
                dict(source='cursor', program='Cursor', character='cursor', state='-', how='y')]
        rc = minis.cmd_doctor(shell=FakeMacShell(), probe=lambda: (True, 'probe ok'), describe=lambda: rows, out=out.append)
        text = '\n'.join(out)
        self.assertEqual(rc, 0, text)
        for want in ('python:', 'Pillow:', 'backend:', 'data dir:', 'screen: 1512x982', 'test overlay window', 'Claude Code (working)',
                     'PASS:', 'issues'):
            self.assertIn(want, text)
        self.assertNotIn(str(Path.home()), text)                              # home shown as ~
        self.assertNotIn('Cursor (', text)                                    # not detected -> not listed as seen

    def test_doctor_fails_loudly_when_the_backend_cannot_load(self):
        out = []
        with mock.patch('minis_platform.shell', lambda: (_ for _ in ()).throw(ImportError('needs PyObjC'))):
            rc = minis.cmd_doctor(describe=lambda: [], out=out.append)
        self.assertEqual(rc, 1)
        self.assertIn('[FAIL] desktop backend loads', '\n'.join(out))
        self.assertTrue(out[-2].startswith('FAIL'))

    def test_headless_still_fails_a_backend_that_cannot_import(self):
        out = []
        with mock.patch('minis_platform.shell', lambda: (_ for _ in ()).throw(ImportError('objc.BadPrototypeError'))):
            rc = minis.cmd_doctor(mock.Mock(headless=True), describe=lambda: [], out=out.append)
        self.assertEqual(rc, 1)
        self.assertIn('[FAIL] desktop backend loads', chr(10).join(out))

    def test_headless_skips_only_the_window(self):
        out = []
        rc = minis.cmd_doctor(mock.Mock(headless=True), shell=FakeMacShell(), probe=lambda: self.fail('opened a window'),
                              describe=lambda: [], out=out.append)
        self.assertEqual(rc, 0, out)
        self.assertIn('[skip] test overlay window (headless)', chr(10).join(out))

    def test_redact(self):
        self.assertEqual(minis.redact('/Users/me/x/y', home='/Users/me'), '~/x/y')
        self.assertEqual(minis.redact('/', home='/'), '/')


if __name__ == '__main__':
    unittest.main()
