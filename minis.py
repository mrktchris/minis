#!/usr/bin/env python3
"""Pixel fighters on the Windows taskbar for whatever AI program is in use (at most two at a time).

  python minis.py start          launch the director + both fighter slots (three processes, no console windows)
  python minis.py stop           stop them: only PIDs it recorded itself, after proving each one's exact command line
  python minis.py status         processes, slot assignments, pause state, bus freshness
  python minis.py pause          freeze every fighter on a static frame (plates keep updating)
  python minis.py resume         animate again
  python minis.py plates on|off  show / hide both HUD plates (fixed at the left end of the zone)
  python minis.py demo [kind]    start one bout now (spar | clash | ranged | match); plates keep the real numbers
  python minis.py winners random|decided   how match winners are drawn (decided = biased by the health score)
  python minis.py monitors       list monitors (index, rect, primary) for `arena --monitor N`
  python minis.py arena --monitor N [--freeze] [--seconds S] [--seed K]   arena mode on monitor N, as its own process
  python minis.py arena stop     ask the arena to leave (then force-stop it if it will not)
  python minis.py arena capture <png>   PrintWindow of the arena's OWN window only (never the desktop)
  python minis.py director       run the director + scoreboard widget in the foreground
  python minis.py run <slot>     run one fighter slot in the foreground (a = left, b = right)
  python minis.py run arena ...  the arena process body (what `arena` launches)
  python minis.py selftest-gui   real-desktop check: draws over the taskbar, survives a taskbar raise   [--keep]
  python minis.py print-startup  print (never run) the commands to start at logon
"""
from __future__ import annotations
import argparse, atexit, logging, logging.handlers, os, random, subprocess, sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from minis_core import config as cfgmod  # noqa: E402

SLOTS = ('a', 'b')
LEGACY = ('claude', 'codex')                      # v2 fighters (`run claude|codex`): stop/status still recognise them
ROLES = ('director',) + SLOTS
ARENA = 'arena'                                    # its own process: `run arena --monitor N ...` (argv prefix match)
PYTHONS = {'python.exe', 'pythonw.exe', 'python3.exe', 'python', 'pythonw', 'python3'}
DEFAULT_ASSIGN = {'a': {'source': 'claude', 'character': 'claude', 'program': 'Claude Code'},
                  'b': {'source': 'codex', 'character': 'codex', 'program': 'Codex'}}
SYSROOT = os.environ.get('SystemRoot', r'C:\Windows')
TASKKILL = os.path.join(SYSROOT, 'System32', 'taskkill.exe')


def other(slot):
    return 'b' if slot == 'a' else 'a'


# ------------------------------------------------------------------ logging (small, rotating, never content)
def get_logger(name):
    log = logging.getLogger(f'minis.{name}')
    if not log.handlers:
        try:
            h = logging.handlers.RotatingFileHandler(cfgmod.data_dir() / f'{name}.log', maxBytes=cfgmod.DEFAULTS['log_max_bytes'],
                                                     backupCount=1, encoding='utf-8')
            h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            log.addHandler(h)
        except OSError:
            log.addHandler(logging.NullHandler())
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def safe_traceback(e):
    """Frames as file:line:function only (no source text), and an OSError's message (which names the file - possibly a
    transcript) reduced to its errno, so a log line can never carry a project or session name."""
    frames = ''.join(f'  {os.path.basename(fr.filename)}:{fr.lineno} in {fr.name}\n' for fr in traceback.extract_tb(e.__traceback__))
    if isinstance(e, OSError):
        msg = f'{type(e).__name__} errno={e.errno} winerror={getattr(e, "winerror", None)}'
    else:
        msg = f'{type(e).__name__}: {str(e)[:200]}'
    return frames + msg


# ------------------------------------------------------------------ process identity
def pid_file(role):
    return cfgmod.data_dir() / f'{role}.pid'


def expected_tail(role):
    return ['director'] if role == 'director' else ['run', role]


def argv_is_ours(argv, role, root=ROOT):
    """Exact argv: <python>, <ROOT>\\minis.py, then `run <slot>` or `director`.  Substrings never count.
    The arena is `run arena` followed by its own options (--monitor N ...), so that role matches on the prefix."""
    if not argv:
        return False
    tail = expected_tail(role)
    if role == ARENA:
        if len(argv) < 2 + len(tail) or list(argv[2:4]) != tail:
            return False
    elif len(argv) != 2 + len(tail):
        return False
    if os.path.basename(argv[0]).lower() not in PYTHONS:
        return False
    try:
        script_ok = os.path.normcase(os.path.abspath(argv[1])) == os.path.normcase(str(Path(root) / 'minis.py'))
    except (TypeError, ValueError):
        return False
    return script_ok and (list(argv[2:4]) == tail if role == ARENA else list(argv[2:]) == tail)


def read_pid(role):
    try:
        return int(pid_file(role).read_text().strip())
    except (OSError, ValueError):
        return None


def pid_alive(pid):
    from minis_win import procs
    return procs.alive(pid)


def proc_argv(pid):
    """argv of a live process, or None when it cannot be read."""
    from minis_win import procs
    try:
        return procs.argv(pid)
    except OSError:
        return None


def proc_state(role):
    """-> (status, pid) with status in running | stopped | unverified | foreign."""
    pid = read_pid(role)
    if not pid:
        return 'stopped', None
    if not pid_alive(pid):
        return 'stopped', pid
    argv = proc_argv(pid)
    if not argv:
        return 'unverified', pid
    return ('running' if argv_is_ours(argv, role) else 'foreign'), pid


def running(role):
    st, pid = proc_state(role)
    return pid if st == 'running' else None


def python_exe(windowless=True):
    exe = Path(sys.executable)
    pyw = exe.with_name('pythonw.exe')
    return pyw if windowless and pyw.exists() else exe


def cmd_start(args=None):
    legacy = [r for r in LEGACY if running(r)]
    if legacy:
        print(f'v2 fighters still running ({", ".join(legacy)}): run `python minis.py stop` first')
        return 1
    exe = python_exe()
    flags = 0x00000008 | 0x00000200 | 0x08000000          # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    for role in ROLES:
        st, pid = proc_state(role)
        if st == 'running':
            print(f'{role}: already running (pid {pid})')
            continue
        subprocess.Popen([str(exe), str(ROOT / 'minis.py')] + expected_tail(role), creationflags=flags, close_fds=True, cwd=str(ROOT))
        print(f'{role}: started')
    return 0


def cmd_stop(args=None, roles=None):
    """Stops only a process whose pid it recorded AND whose exact command line is ours.  Anything else is left alone and
    reported; a command line that cannot be read is reported as 'could not verify', separately."""
    from minis_core import bus, control
    rc = 0
    for role in (roles if roles is not None else ROLES + LEGACY + (ARENA,)):
        st, pid = proc_state(role)
        if st == 'stopped':
            if pid is not None:
                pid_file(role).unlink(missing_ok=True)       # stale file from a dead process
            if role in ROLES:
                print(f'{role}: not running')
            if role == ARENA and pid is not None:
                control.clear_arena_state()
            continue
        if st == 'unverified':
            print(f'{role}: could not verify pid {pid} (command line unreadable) - left alone')
            rc = 1
            continue
        if st == 'foreign':
            print(f'{role}: pid {pid} is not a minis process (pid reused?) - left alone')
            continue
        if not argv_is_ours(proc_argv(pid), role):            # re-check right before killing
            print(f'{role}: pid {pid} changed under us - left alone')
            continue
        r = subprocess.run([TASKKILL, '/PID', str(pid), '/F'], capture_output=True)
        if r.returncode == 0:
            pid_file(role).unlink(missing_ok=True)
            if role in SLOTS + LEGACY:
                bus.write_gone(role)
            if role == ARENA:
                control.clear_arena_state()
            print(f'{role}: stopped (pid {pid})')
        else:
            print(f'{role}: taskkill failed for pid {pid} (exit {r.returncode})')
            rc = 1
    return rc


def cmd_status(args=None):
    from minis_core import bus, control, director
    data = director.read_assign()
    now = time.time()
    for role in ROLES + LEGACY:
        st, pid = proc_state(role)
        if role in LEGACY and st == 'stopped':
            continue
        line = f'{role:8s} {st}{" pid %s" % pid if pid else ""}'
        if role in SLOTS + LEGACY:
            b = bus.read(role, raw=True)
            age = None if not b else round(now - float(b.get('ts', 0)), 1)
            line += f'  bus age {age}s state={b and b.get("state")} mode={b and b.get("mode")} anim={b and b.get("anim")}'
        if role in SLOTS:
            a = DEFAULT_ASSIGN[role] if data is None else director.slot_assignment(data, role)
            line += f'  -> {a["program"]} as {a["character"]}' if a else '  -> (no assignment: hidden)'
        print(line)
    if data is None:
        print('assign.json: missing (fighters fall back to a=claude, b=codex)')
    else:
        print(f'assign.json: written {round(now - float(data.get("ts", 0)), 1)}s ago')
    print('animations:', 'PAUSED' if control.paused() else 'running', '| HUD plates:', 'on' if control.plates_on() else 'off',
          '| winners:', control.winners())
    st, pid = proc_state(ARENA)
    ar = control.arena_state()
    print(f'arena: {st}{" pid %s" % pid if pid else ""}' + (f'  monitor {ar.get("monitor")} phase={ar.get("phase")} round={ar.get("round")} hp={ar.get("hp")}' if ar else ''))
    from minis_core import rounds
    rec = rounds.read_record()
    if rec.get('characters'):
        print('record:', ', '.join(f'{c} {v.get("w", 0)}-{v.get("l", 0)}' for c, v in sorted(rec['characters'].items())))
    return 0


def cmd_pause(args=None):
    from minis_core import control
    ok = control.set_paused(True)
    print('paused' if ok else 'could not write control.json')
    return 0 if ok else 1


def cmd_resume(args=None):
    from minis_core import control
    ok = control.set_paused(False)
    print('resumed' if ok else 'could not write control.json')
    return 0 if ok else 1


def cmd_plates(args):
    from minis_core import control
    ok = control.set_plates(args.state == 'on')
    print(f'HUD plates {args.state}' if ok else 'could not write control.json')
    return 0 if ok else 1


def cmd_demo(args):
    """One bout right now, for a look.  Only the choreography is forced; the plates keep showing the real state."""
    from minis_core import control
    ok = control.request_demo(args.kind)
    if not ok:
        print('could not write control.json')
        return 1
    if not running('a') or not running('b'):
        print(f'{args.kind} requested, but both fighter slots must be running (`python minis.py start`)')
        return 1
    print(f'{args.kind} requested: the two fighters meet in the middle within a few seconds (if neither is paused)')
    return 0


def cmd_winners(args):
    from minis_core import control
    ok = control.set_winners(args.mode)
    print(f'winners: {args.mode}' if ok else 'could not write control.json')
    return 0 if ok else 1


def cmd_monitors(args=None):
    from minis_win import shell
    for m in shell.monitors():
        l, t, r, b = m['rect']
        print(f"{m['index']}: {r - l}x{b - t} at ({l},{t}){'  primary' if m['primary'] else ''}")
    return 0


def pick_arena_monitor(cfg, mons):
    """The monitor the Arena button / menu item uses: cfg `arena_monitor`, else the one non-primary monitor, else None."""
    if cfg.get('arena_monitor'):
        return int(cfg['arena_monitor'])
    others = [m['index'] for m in mons if not m['primary']]
    return others[0] if len(others) == 1 else None


def start_arena(monitor, freeze=False, seconds=None, seed=None):
    """Launch the arena as its own detached process (a crash never takes the taskbar fighters down).
    `seed` fixes the choreography (previews, captures); without it the wall clock seeds the match."""
    st, pid = proc_state(ARENA)
    if st == 'running':
        return f'arena: already running (pid {pid})', 1
    argv = [str(python_exe()), str(ROOT / 'minis.py'), 'run', 'arena', '--monitor', str(int(monitor))]
    if freeze:
        argv.append('--freeze')
    if seconds:
        argv += ['--seconds', str(float(seconds))]
    if seed is not None:
        argv += ['--seed', str(int(seed))]
    flags = 0x00000008 | 0x00000200 | 0x08000000
    subprocess.Popen(argv, creationflags=flags, close_fds=True, cwd=str(ROOT))
    return f'arena: started on monitor {monitor}' + (' (freeze)' if freeze else ''), 0


def stop_arena(wait_s=4.0):
    """Ask the arena to play its exit and leave; after `wait_s` force-stop it (only if its command line is ours)."""
    from minis_core import control
    st, pid = proc_state(ARENA)
    if st != 'running':
        control.clear_arena_state()
        return 'arena: not running', 0
    control.request_arena_stop()
    end = time.time() + wait_s
    while time.time() < end:
        if proc_state(ARENA)[0] != 'running':
            control.clear_arena_state()
            return 'arena: stopped', 0
        time.sleep(0.2)
    rc = cmd_stop(roles=(ARENA,))
    return 'arena: force-stopped' if rc == 0 else 'arena: could not stop', rc


def cmd_arena(args):
    from minis_win import shell
    if args.action == 'stop':
        msg, rc = stop_arena()
        print(msg)
        return rc
    if args.action == 'capture':
        if not args.path:
            print('arena capture <png>: a path is needed')
            return 2
        hwnd = shell.find_own_window('MinisArena')
        if not hwnd:
            print('arena capture: no arena window')
            return 1
        im = shell.capture_window(hwnd)
        if im is None:
            print('arena capture: PrintWindow failed')
            return 1
        Path(args.path).parent.mkdir(parents=True, exist_ok=True)
        im.save(args.path)
        print(f'arena capture: {im.size[0]}x{im.size[1]} -> {args.path}')
        return 0
    if args.monitor is None:
        print('arena: --monitor N is required (no default; see `python minis.py monitors`)')
        return 2
    mons = {m['index'] for m in shell.monitors()}
    if args.monitor not in mons:
        print(f'arena: monitor {args.monitor} does not exist; have {sorted(mons)}')
        return 2
    msg, rc = start_arena(args.monitor, args.freeze, args.seconds, getattr(args, 'seed', None))
    print(msg)
    return rc


def cmd_print_startup(args=None):
    exe = Path(sys.executable).with_name('pythonw.exe')
    print('# Not run for you. Either of these starts the director and both fighter slots at logon:\n')
    print(f'schtasks /Create /SC ONLOGON /TN "MinisFighters" /TR "\\"{exe}\\" \\"{ROOT / "minis.py"}\\" start" /RL LIMITED /F')
    print('\n# or drop a shortcut to this into  shell:startup :')
    print(f'"{exe}" "{ROOT / "minis.py"}" start')
    print('\n# remove later:  schtasks /Delete /TN "MinisFighters" /F')
    return 0


def _own_process(role):
    """Single instance per role (named mutex) + pid file removed on exit."""
    from minis_win import shell
    return _own_process_with(shell, role)


def mutex_name(role):
    """One instance per role *per data dir*: the two-process test (its own temp data dir) can run beside live fighters."""
    import zlib
    return f'Local\\minis-{role}-{zlib.crc32(str(cfgmod.data_dir()).lower().encode()):08x}'


def _own_process_with(shell, role):
    mutex, already = shell.make_mutex(mutex_name(role))
    if already:
        return None
    pf = pid_file(role)
    pf.write_text(str(os.getpid()))
    atexit.register(lambda: pf.unlink(missing_ok=True))
    return mutex


# ------------------------------------------------------------------ director process
def cmd_director(args):
    from minis_win import shell
    return run_director(shell, cfgmod.load())


def run_director(shell, cfg, detector_sources=None, wall=time.time, mono=time.monotonic, max_iterations=None):
    """The director process body: source polling every `director_poll_s` + the scoreboard widget (pumped every 50 ms)."""
    from minis_core import director, sources
    log = get_logger('director')
    mutex = _own_process_with(shell, 'director')
    if mutex is None:
        print('director is already running')
        return 0
    from minis_core import history
    runner = director.Runner(cfg, detector_sources or sources.Sources(cfg))
    hist = history.Recorder()
    board = None
    try:
        if cfg.get('scoreboard', True):
            board = Scoreboard(cfg, shell, wall=wall, mono=mono, log=log)
            board.setup()
    except Exception as e:
        log.error('scoreboard setup failed\n' + safe_traceback(e))
        board = None
    log.info('director started')
    errors = 0
    next_poll = -1e9
    n = 0
    try:
        while True:
            now = mono()
            try:
                if now >= next_poll:
                    next_poll = now + cfg['director_poll_s'] + (2.0 if errors > 20 else 0.0)
                    data, acts = runner.step(wall())
                    hist.record(acts, wall())
                    errors = 0
                if board is not None and board.step() is None:
                    break
            except Exception as e:                        # never die silently: log and keep going
                errors += 1
                log.error(safe_traceback(e))
            n += 1
            if max_iterations is not None and n >= max_iterations:
                break
            time.sleep(0.05 if board is not None else max(0.2, next_poll - mono()))
    finally:
        if board is not None:
            board.close()
    return 0


class Scoreboard:
    """The right-side widget (minis_core.scoreboard draws it): records, mode, HP bars during a bout, three buttons.
    Lives in the director process; solid to the mouse only on its buttons (WM_NCHITTEST), so clicks elsewhere fall
    through to the taskbar."""

    def __init__(self, cfg, shell, wall=time.time, mono=time.monotonic, log=None):
        from minis_core import scoreboard as SB
        self.cfg, self.shell, self.wall, self.mono = cfg, shell, wall, mono
        self.SB = SB
        self.log = log or logging.getLogger('minis.null')
        self.ov = None
        self.g = None
        self.pressed = None
        self.press_t = 0.0
        self.last = dict(draw=-1e9, sig=None, tb=-1e9, top=-1e9, read=-1e9)
        self.state = None
        self.clicks = []                                  # (button, mono) for tests
        self.hidden = True
        self.quit = False

    def geometry(self):
        l, t, r, b, edge = self.shell.taskbar_rect()
        ok = edge == 3 and not self.shell.taskbar_autohide()
        if edge != 3:
            _, sh = self.shell.screen_size()
            b, t = sh, sh - 48
        band = max(24, b - t)
        sc = cfgmod.ui_scale(band)
        y = b - band + max(0, (band - self.SB.H * sc) // 2)
        return dict(scale=sc, y=y, usable=ok)

    def setup(self):
        self.g = self.geometry()
        self.ov = self.shell.Overlay('minis-scoreboard', self.SB.left_x(self.cfg) * self.g['scale'], self.g['y'], self.SB.W, self.SB.H,
                                     scale=self.g['scale'], on_event=self.on_event, on_hittest=lambda x, y: self.SB.hit(x, y) is not None)
        self.ov.show(False)

    def on_event(self, kind, mx, my):
        name = self.SB.hit(mx, my)
        if kind == 'down' and name:
            self.pressed, self.press_t = name, self.mono()
            self.last['sig'] = None
        elif kind == 'up':
            if self.pressed and self.SB.hit(mx, my) == self.pressed:
                self.act(self.pressed)
            self.pressed = None
            self.last['sig'] = None

    def act(self, name):
        from minis_core import control
        self.clicks.append((name, self.mono()))
        if name == 'pause':
            control.set_paused(not control.paused())
        elif name == 'bout':
            control.request_demo('match', now=self.wall())
        elif name == 'arena':
            if control.arena_active():
                self.log.info('arena: %s', stop_arena()[0])
            else:
                try:
                    mon = pick_arena_monitor(self.cfg, self.shell.monitors())
                except Exception:
                    mon = None
                if mon is None:
                    self.log.info('arena: no monitor chosen (set arena_monitor in minis.json or use `minis.py arena --monitor N`)')
                else:
                    self.log.info('arena: %s', start_arena(mon)[0])
        self.last['read'] = -1e9

    def read_state(self):
        from minis_core import bus, control, director, rounds
        wall = self.wall()
        assign = director.read_assign()
        if assign is None:
            assign = DEFAULT_ASSIGN
        from minis_core import history
        buses = {s: bus.read(s, now=wall) for s in SLOTS}
        return self.SB.Model.state(assign, buses, rounds.read_record(), control.paused(), control.arena_active(now=wall), control.winners(),
                                   pressed=self.pressed, spark=history.last_days(7, wall))

    def step(self):
        """One iteration; None when the window is gone."""
        if not self.ov.pump() or self.quit:
            return None
        now = self.mono()
        if self.pressed and now - self.press_t > 1.5:
            self.pressed = None
        if now - self.last['tb'] >= 2.0:
            self.last['tb'] = now
            g2 = self.geometry()
            if g2['scale'] != self.g['scale'] or g2['y'] != self.g['y']:
                self.ov.set_scale(g2['scale'])
                self.ov.move(self.SB.left_x(self.cfg) * g2['scale'], g2['y'])
                self.last['sig'] = None
            self.g = g2
            hidden = not g2['usable'] or self.shell.fullscreen_busy() or not self.cfg.get('scoreboard', True)
            if not hidden and not self.ov.visible:
                self.last['sig'] = None
            self.ov.show(not hidden)
            self.hidden = hidden
        if self.ov.visible and now - self.last['top'] >= self.cfg['topmost_tick_ms'] / 1000.0:
            self.ov.reassert_topmost()
            self.last['top'] = now
        if self.ov.visible and now - self.last['read'] >= 0.25:
            self.last['read'] = now
            self.state = self.read_state()
            sig = self.SB.signature(self.state)
            if sig != self.last['sig']:
                self.ov.present(self.SB.render(self.state), x=self.SB.left_x(self.cfg) * self.g['scale'])
                self.last['sig'] = sig
        return 0.05

    def close(self):
        try:
            if self.ov:
                self.ov.close()
        except Exception:
            pass


# ------------------------------------------------------------------ fighter slot
class Fighter:
    """One slot's loop.  `step()` is one iteration (testable without a desktop: inject a fake shell / overlay)."""

    def __init__(self, slot, cfg, shell, lib=None, rng=None, wall=time.time, mono=time.monotonic, assign_path=None,
                 control_path=None, bus_root=None, detector_for=None, log=None):
        from minis_core.atlas import Library
        from minis_core import sources
        self.slot, self.cfg, self.shell = slot, cfg, shell
        self.lib = lib or Library()
        self.rng = rng or random.Random()
        self.wall, self.mono = wall, mono
        self.assign_path, self.control_path, self.bus_root = assign_path, control_path, bus_root
        self.detector_for = detector_for or sources.detector_for
        self.log = log or logging.getLogger('minis.null')
        self.cell = 64
        z0, z1 = cfg['zone']
        self.win_x = int(z0 - 36)
        self.zone_w = int(z1 + 36 - self.win_x)
        self.st = dict(drag=False, dx=0.0, hide_until=0.0, quit=False, menu=False, drag_t=0.0, drag_x=0.0, drag_v=0.0, drag_vmax=0.0)
        self.arena = False            # the arena process is up: the taskbar fighters hide while it plays
        self.assigned = None          # {'source','character','program'} or None
        self.detector = None
        self.snap = None
        self.partner = None
        self.paused = False
        self.plates = cfg.get('plate', True)                # HUD plates on/off: control.json `plates` (all fighters)
        self.hidden = True
        self.brain = None
        self.ov = None                # the fighter window (sprite + projectile), moves with the fighter
        self.pov = None               # the HUD plate window, fixed at the left end of the zone
        self.g = None
        self.last = dict(tele=-1e9, bus=-1e9, top=-1e9, tb=-1e9, draw=-1e9, sig=None, pbus=-1e9, assign=-1e9, ctl=-1e9, pubkey=None, evkey=None,
                         psig=None, demo=None, notes=0)
        self.gone_written = False

    # -------------------------------------------------- setup
    def geometry(self):
        l, t, r, b, edge = self.shell.taskbar_rect()
        ok = edge == 3 and not self.shell.taskbar_autohide()
        if edge != 3:
            _, sh = self.shell.screen_size()
            b, t = sh, sh - 48
        band = max(24, b - t)
        sc = cfgmod.ui_scale(band)
        py = b - band + max(0, (band - cfgmod.PLATE_H * sc) // 2)          # plate: vertically centred in the taskbar band
        return dict(scale=sc, y=b - self.cell * sc, bottom=b, usable=ok, plate_y=py)

    def plate_x(self):
        return cfgmod.plate_left(self.cfg, self.slot) * self.g['scale']

    def setup(self):
        from minis_core import control
        from minis_core.brain import Brain
        from minis_core.telemetry import Snapshot
        self.g = self.geometry()
        now = self.mono()
        self._apply_assignment(self._read_assignment(), now, force=True)
        atlas = self.lib[self.assigned['character'] if self.assigned else 'claude']
        self.brain = Brain(self.slot, atlas, self.lib, self.cfg, self.rng, now)
        self.snap = Snapshot(atlas.character, 'sleeping')
        self.ov = self.shell.Overlay(f'minis-{self.slot}', int(self.cfg['zone'][0]), self.g['y'], 64, self.cell, scale=self.g['scale'],
                                     on_event=self.on_event, on_timer=self.menu_tick)
        self.ov.show(False)
        self.pov = self.shell.Overlay(f'minis-{self.slot}-plate', self.plate_x(), self.g['plate_y'], cfgmod.PLATE_W, cfgmod.PLATE_H,
                                      scale=self.g['scale'], on_event=self.on_plate_event, on_timer=self.menu_tick)
        self.pov.show(False)
        d = control.demo(self.control_path, now=self.wall())
        self.last['demo'] = d and d.get('id')                # a demo asked for before this process started is not replayed

    def display_name(self):
        """What the plate calls this fighter: the program's name (Claude, Codex, Gemini ...).  A character drawn with the
        generic skin (aider, opencode, a missing atlas) is named after the program it stands for."""
        a = self.assigned or {}
        atlas = self.brain.atlas
        if atlas.character == 'generic' or (a.get('character') and a['character'] != atlas.character):
            return a.get('program') or atlas.display
        return atlas.display

    # -------------------------------------------------- assignment + controls
    def _read_assignment(self):
        from minis_core import director
        data = director.read_assign(self.assign_path)
        if data is None:                                  # no director has ever run: the two transcript fighters
            return DEFAULT_ASSIGN[self.slot]
        return director.slot_assignment(data, self.slot)

    def _apply_assignment(self, a, now, force=False):
        if not force and a == self.assigned:
            return
        prev = self.assigned
        self.assigned = a
        self.last['tb'] = -1e9                             # show / hide on the next iteration, not up to 2 s later
        if a is None:
            self.detector = None
            return
        if force or prev is None or prev.get('source') != a['source']:
            self.detector = self.detector_for(a['source'], self.cfg)
            self.last['tele'] = -1e9
        if self.brain is not None and (prev is None or prev.get('character') != a['character'] or self.brain.character != self.lib[a['character']].character):
            self.brain.set_atlas(self.lib[a['character']], now)
            self.last['sig'] = None

    # -------------------------------------------------- mouse + menu
    def on_event(self, kind, mx, my):
        now = self.mono()
        b, ov = self.brain, self.ov
        if kind == 'up':
            if self.st['drag']:
                self.st['drag'] = False
                v, vmax = self.st['drag_v'], self.st['drag_vmax']
                shift = False
                try:
                    shift = bool(self.shell.shift_down())
                except Exception:
                    pass
                if shift and abs(v) > 150:
                    b.throw(max(-900.0, min(900.0, v)), now)      # Shift-drag: a short throw
                elif vmax > 600:
                    b.stun(now)                                   # a fast drag leaves it dizzy
            return
        sx = ov.x / ov.scale + mx                          # window-relative -> screen x (logical px)
        if kind == 'down' and abs(sx - b.x) <= 24 and my >= 8:
            self.st['drag'], self.st['dx'] = True, sx - b.x
            self.st.update(drag_t=now, drag_x=sx, drag_v=0.0, drag_vmax=0.0)
        elif kind == 'move' and self.st['drag']:
            dt = now - self.st['drag_t']
            if dt > 0.0:
                v = (sx - self.st['drag_x']) / dt
                self.st['drag_v'] = 0.6 * self.st['drag_v'] + 0.4 * v if dt < 0.2 else v
                self.st['drag_vmax'] = max(self.st['drag_vmax'], abs(v))
            self.st['drag_t'], self.st['drag_x'] = now, sx
            b.drag_to(sx - self.st['dx'], now)
        elif kind == 'dbl' and not self.paused:
            b.play('victory', now, loop=False)
        elif kind == 'rclick':
            self.st['menu'] = True                         # opened from the loop, not from inside the window procedure

    def on_plate_event(self, kind, mx, my):
        if kind == 'rclick':                               # the plate only opens the menu; it cannot be dragged
            self.st['menu'] = True

    def menu_tick(self):
        """Runs on a timer while the (modal) menu is open: keeps the bus heartbeat and keep-on-top alive."""
        self._publish(self.wall(), force=True)
        self.ov.reassert_topmost()
        if self.pov is not None and self.pov.visible:
            self.pov.reassert_topmost()

    def open_menu(self):
        from minis_core import control
        name = (self.assigned or {}).get('program') or self.slot
        paused = control.paused(self.control_path)
        plates = control.plates_on(self.control_path)
        winners = control.winners(self.control_path)
        arena = control.arena_active(self.control_path and None)
        choice = self.ov.menu([(1, f'Quit this mini ({name})'), (2, 'Hide for 1 hour'), (3, 'Hide HUD plates' if plates else 'Show HUD plates'),
                               (4, 'Resume animations' if paused else 'Pause all animations'), (5, 'Start a bout now'),
                               (6, 'Start a match now (best of 3)'),
                               (7, f'Winners: {winners} -> {"random" if winners == "decided" else "decided"}'),
                               (8, 'Exit arena mode' if arena else 'Arena mode...')])
        if choice == 1:
            self.st['quit'] = True
        elif choice == 2:
            self.st['hide_until'] = self.mono() + 3600
        elif choice == 3:
            control.set_plates(not plates, self.control_path)
            self.last['ctl'] = -1e9
        elif choice == 4:
            control.set_paused(not paused, self.control_path)
            self.last['ctl'] = -1e9
        elif choice == 5:
            control.request_demo('spar', self.control_path, now=self.wall())
            self.last['ctl'] = -1e9
        elif choice == 6:
            control.request_demo('match', self.control_path, now=self.wall())
            self.last['ctl'] = -1e9
        elif choice == 7:
            control.set_winners('random' if winners == 'decided' else 'decided', self.control_path)
            self.last['ctl'] = -1e9
        elif choice == 8:
            self.toggle_arena()

    def toggle_arena(self):
        """Menu / scoreboard: start the arena on the configured (or the only other) monitor, or ask it to leave."""
        from minis_core import control
        if control.arena_active():
            self.log.info('arena: %s', stop_arena()[0])
            return
        try:
            mon = pick_arena_monitor(self.cfg, self.shell.monitors())
        except Exception:
            mon = None
        if mon is None:
            self.log.info('arena: no monitor chosen (set arena_monitor in minis.json or use `minis.py arena --monitor N`)')
            return
        self.log.info('arena: %s', start_arena(mon)[0])

    # -------------------------------------------------- bus
    def _publish(self, wall, force=False):
        from minis_core import bus
        if self.assigned is None:
            if not self.gone_written:
                self.gone_written = bus.write_gone(self.slot, root=self.bus_root, now=wall)
            return
        self.gone_written = False
        pub = self.brain.publish()
        ev = pub['event'] or {}
        evkey = (ev.get('run'), ev.get('seq'))
        key = (pub['state'], pub['mode'], int(pub['x']), pub['facing'], pub['anim'], pub['ctx'], evkey, pub['paused'], pub['character'])
        mono = self.mono()
        if force or evkey != self.last['evkey'] or (mono - self.last['bus'] >= 0.25 and key != self.last['pubkey']) or mono - self.last['bus'] >= 1.0:
            bus.write(self.slot, pub, root=self.bus_root, now=wall)        # event changes go out immediately
            self.last['bus'], self.last['pubkey'], self.last['evkey'] = mono, key, evkey

    # -------------------------------------------------- one iteration
    def step(self):
        """-> seconds to sleep before the next iteration, or None to quit."""
        from minis_core import bus, control, render
        from minis_core.telemetry import Snapshot
        ov, b = self.ov, self.brain
        if not ov.pump() or self.st['quit']:
            return None
        if self.st['menu']:
            self.st['menu'] = False
            self.open_menu()
            if self.st['quit']:
                return None
        now, wall = self.mono(), self.wall()
        if now - self.last['assign'] >= 1.0:
            self.last['assign'] = now
            self._apply_assignment(self._read_assignment(), now)
        if now - self.last['ctl'] >= 0.5:
            self.last['ctl'] = now
            p = control.paused(self.control_path)
            if p != self.paused:
                self.paused = p
                b.set_paused(p, now)
                self.last['sig'] = None
            pl = control.plates_on(self.control_path)
            if pl != self.plates:
                self.plates = pl
                self.last['psig'] = None
                self._show_plate()
            b.winners = control.winners(self.control_path)
            ar = control.arena_active(now=wall)
            if ar != self.arena:
                self.arena = ar
                self.last['tb'] = -1e9                             # hide / reappear on this very iteration
                if ar and (b.bout or b.script or b.pending):
                    b.abort(now)
            d = control.demo(self.control_path, now=wall)
            if d and d.get('id') != self.last['demo']:
                self.last['demo'] = d.get('id')
                if self.slot == 'a':                       # one side starts it (like every timed bout); the other accepts
                    b.request_demo(d['kind'], now)
        tele_every = 1.0 if (self.assigned or {}).get('source') in ('claude', 'codex') else 2.0
        if self.detector is not None and now - self.last['tele'] >= tele_every:
            self.last['tele'] = now
            acts = self.detector.poll(wall)
            self.snap = acts[0].snapshot() if acts else Snapshot(b.character, 'sleeping')
        if now - self.last['pbus'] >= 0.2:
            self.last['pbus'] = now
            self.partner = bus.read(other(self.slot), root=self.bus_root, now=wall)
            if b.mode == 'home' and b.anim == 'idle' and not self.paused:        # pupils follow the cursor (one GetCursorPos per 0.2 s)
                from minis_core import eyes
                try:
                    cur = self.shell.cursor_pos()
                except Exception:
                    cur = None
                b.eye = eyes.look_at(b.x * self.g['scale'], self.g['y'] + 20 * self.g['scale'], cur) if cur else (0, 0)
            elif b.eye != (0, 0):
                b.eye = (0, 0)
        if self.assigned is not None:
            b.tick(now, self.snap, self.partner)
            self.snap.events = []                          # events are consumed by the first tick that sees them
            self._log_bout_notes()
        self._publish(wall)
        if now - self.last['tb'] >= 2.0:
            self.last['tb'] = now
            g2 = self.geometry()
            if g2['scale'] != self.g['scale'] or g2['y'] != self.g['y'] or g2['plate_y'] != self.g['plate_y']:
                ov.set_scale(g2['scale'])
                ov.move(ov.x, g2['y'])
                self.g = g2
                self.pov.set_scale(g2['scale'])
                self.pov.move(self.plate_x(), g2['plate_y'])
                self.last['sig'] = self.last['psig'] = None
            self.g = g2
            hidden = (self.assigned is None or now < self.st['hide_until'] or not g2['usable'] or self.shell.fullscreen_busy() or self.arena)
            if not hidden and not ov.visible:
                self.last['sig'] = None
            ov.show(not hidden)
            self.hidden = hidden
            self._show_plate()
        if ov.visible and now - self.last['top'] >= self.cfg['topmost_tick_ms'] / 1000.0:
            ov.reassert_topmost()
            if self.pov.visible:
                self.pov.reassert_topmost()
            self.last['top'] = now
        if ov.visible:
            v = b.view(now)
            sig = (v['anim'], v['frame'], int(v['x']), v['facing'], v['dim'], (v['proj'] or {}).get('x', 0) // 2, b.character,
                   int(now * self.cfg['fps_active']) if v.get('busy') else 0, v.get('eye'))       # effects / banners: redraw at the active rate
            quiet = self.paused or (v['anim'] in ('idle', 'sleep', 'wait', 'dizzy', 'rage', 'type', 'work') and b.mode == 'home' and not v.get('busy'))
            min_dt = 1.0 / (self.cfg['fps_idle'] if quiet else self.cfg['fps_active'])
            stale = (not self.paused) and now - self.last['draw'] > 1.0
            if (sig != self.last['sig'] and now - self.last['draw'] >= min_dt) or stale:
                im, x0 = render.compose(b.atlas, b.atlas, v, self.snap, now, self.cfg, show_plate=False)
                ov.present(im, x=x0 * self.g['scale'])
                self.last['sig'], self.last['draw'] = sig, now
        if self.pov.visible:
            self._draw_plate(now)
        return 0.25 if (self.paused or not ov.visible) else 0.05

    def _show_plate(self):
        vis = self.plates and not self.hidden
        if vis and not self.pov.visible:
            self.last['psig'] = None
        self.pov.show(vis)

    def _draw_plate(self, now):
        """The plate window only redraws when what it shows changes (state, the rounded numbers, the blink phase)."""
        from minis_core import render
        snap, name = self.snap, self.display_name()
        psig = (name, self.brain.character, snap.state, render.shown_pct(snap.ctx_pct), render.shown_pct(snap.plan_pct), snap.plan_label,
                render.blink_phase(snap, now))
        if psig != self.last['psig']:
            self.pov.present(render.plate(self.brain.atlas, snap, now, name=name), x=self.plate_x())
            self.last['psig'] = psig

    def _log_bout_notes(self):
        """Bout start / contact / hit times go to the slot log (ids, times and move names only - never content)."""
        b = self.brain
        new = min(b.bout_log_n - self.last['notes'], len(b.bout_log))
        for what, bout, t, move in list(b.bout_log)[len(b.bout_log) - new:] if new > 0 else ():
            self.log.info('%s %s %.3f %s', what, bout, t, move)
        self.last['notes'] = b.bout_log_n

    def close(self):
        from minis_core import bus
        for w in (self.ov, self.pov):
            try:
                if w:
                    w.close()
            except Exception:
                pass
        bus.write_gone(self.slot, root=self.bus_root, now=self.wall())


def cmd_run(args):
    from minis_win import shell
    if args.slot == ARENA:
        if args.monitor is None:
            print('run arena: --monitor N is required')
            return 2
        return run_arena(dict(monitor=args.monitor, freeze=args.freeze, seconds=args.seconds), shell, cfgmod.load(), seed=getattr(args, 'seed', None))
    return run_slot(args.slot, shell, cfgmod.load())


# ------------------------------------------------------------------ arena process
def run_arena(opts, shell, cfg, monitor_rect=None, windows_fn=None, backdrop=None, surface=None, wall=time.time, mono=time.monotonic,
              max_seconds=None, seed=None):
    """The arena process body.  Injectable for tests: `monitor_rect` (l, t, r, b) replaces the real monitor, `windows_fn()`
    the window-rect enumeration, `backdrop` a synthetic RAM image, `surface` a headless surface instead of the window.
    The freeze backdrop (`--freeze`) is grabbed into RAM here and handed to the arena; it is never written anywhere."""
    from minis_core import arena as AR, bus, control, director, fx as fxmod, rounds
    from minis_core.atlas import Library
    log = get_logger('arena')
    if _own_process_with(shell, ARENA) is None:
        print('arena is already running')
        return 0
    mon = int(opts.get('monitor') or 0)
    if monitor_rect is None:
        mons = {m['index']: m for m in shell.monitors()}
        if mon not in mons:
            print(f'run arena: monitor {mon} does not exist')
            return 2
        rect, work = mons[mon]['rect'], mons[mon]['work']
    else:
        rect, work = tuple(monitor_rect), tuple(monitor_rect)
    floor_y = work[3] if work[3] < rect[3] else rect[3]      # the taskbar top when the taskbar is on this monitor
    if opts.get('freeze') and backdrop is None:
        try:
            from PIL import ImageGrab
            backdrop = ImageGrab.grab(bbox=rect, all_screens=True).convert('RGBA')     # RAM only, for this process's life
        except Exception as e:
            log.error('freeze grab failed\n' + safe_traceback(e))
            backdrop = None
    if backdrop is not None and backdrop.size != (rect[2] - rect[0], rect[3] - rect[1]):
        from PIL import Image
        backdrop = backdrop.resize((rect[2] - rect[0], rect[3] - rect[1]), Image.NEAREST)
    assign = director.read_assign() or DEFAULT_ASSIGN
    slots = {s: director.slot_assignment(assign, s) or DEFAULT_ASSIGN[s] for s in SLOTS}
    lib = Library(hd=True)
    atl = {s: lib[slots[s]['character']] for s in SLOTS}
    names = {s: slots[s].get('program') or atl[s].display for s in SLOTS}
    chars = {s: atl[s].character for s in SLOTS}
    buses = {s: bus.read(s, now=wall()) for s in SLOTS}
    scores = {s: rounds.score_of_bus(buses[s]) for s in SLOTS}
    arena = AR.Arena(AR.Stage(rect, [], floor_y, tuple(cfg.get('arena_min_window_px', (160, 100)))), atl, fxmod.default(),
                     seed=seed if seed is not None else int(wall() * 1000) % 100000, mode=control.winners(), scores=scores, backdrop=backdrop,
                     names=names, chars=chars, now=mono(), cfg=cfg)
    own = []
    if surface is None:
        from minis_win.arena_window import ArenaWindow, VK_ESCAPE
        win = ArenaWindow(rect, on_hittest=arena.hit_exit, on_click=lambda x, y: arena.request_exit(mono()) if arena.hit_exit(x, y) else None,
                          on_key=lambda vk: arena.request_exit(mono()) if vk == VK_ESCAPE else None)
        own = [win.hwnd]
    else:
        win = surface
    comp = AR.Compositor(arena, win)
    windows_fn = windows_fn or (lambda: shell.window_rects(exclude=own))
    started = wall()
    seconds = opts.get('seconds') or max_seconds
    fps = int(cfg.get('arena_fps', 30))
    budget = float(cfg.get('arena_cpu_budget_pct', 10.0))
    log.info('arena started monitor=%s freeze=%s seconds=%s', mon, backdrop is not None, seconds)
    last_win, last_hb, last_cpu, cpu_pct = -1e9, -1e9, None, 0.0
    try:
        from minis_win import procs
    except Exception:
        procs = None
    try:
        while arena.phase != 'done':
            t0 = mono()
            try:
                if not win.pump():
                    break
                now = mono()
                if now - last_win >= 1.0:
                    last_win = now
                    try:
                        arena.stage.update(windows_fn())
                    except Exception as e:
                        log.error(safe_traceback(e))
                paused = control.paused()
                if paused != arena.paused:
                    arena.paused = paused
                if control.arena_stop_requested(started) or (seconds and wall() - started >= float(seconds)):
                    arena.request_exit(now)
                arena.tick(now)
                comp.render(now)
                if now - last_hb >= 1.0:
                    last_hb = now
                    st = arena.state()
                    control.write_arena_state(dict(active=True, pid=os.getpid(), monitor=mon, fps=fps, cpu_pct=round(cpu_pct, 1), **st), now=wall())
                    if procs is not None:
                        tm = procs.times(os.getpid())
                        if tm and last_cpu is not None:
                            cpu_pct = (tm[1] - last_cpu[0]) / max(1e-3, wall() - last_cpu[1]) * 100.0
                            if cpu_pct > budget and fps > 20:
                                fps = 20
                                log.info('arena: cpu %.1f%% over budget, 20 fps', cpu_pct)
                        if tm:
                            last_cpu = (tm[1], wall())
            except Exception as e:
                log.error(safe_traceback(e))
                time.sleep(0.1)
            time.sleep(max(0.0, 1.0 / fps - (mono() - t0)))
    finally:
        try:
            control.clear_arena_state()
        finally:
            win.close()
        del backdrop
        arena.backdrop = None
        log.info('arena stopped: %s', arena.state())
    return 0


def run_slot(slot, shell, cfg, detector_for=None):
    """The slot process body.  `shell` and `detector_for` are injectable so tests/two_process_harness.py can run real
    slot processes headless against fake sources."""
    log = get_logger(slot)
    if _own_process_with(shell, slot) is None:
        print(f'slot {slot} is already running')
        return 0
    f = Fighter(slot, cfg, shell, log=log, detector_for=detector_for)
    try:
        f.setup()
    except Exception as e:
        log.error('setup failed\n' + safe_traceback(e))
        raise
    log.info('slot %s started', slot)
    errors = 0
    try:
        while True:
            try:
                dt = f.step()
                errors = 0
            except Exception as e:                    # one bad frame must not end the process, and must not pass silently
                errors += 1
                log.error(safe_traceback(e))
                dt = 2.0 if errors > 20 else 0.25
            if dt is None:
                break
            time.sleep(dt)
    finally:
        f.close()
        log.info('slot %s stopped', slot)
    return 0


# ------------------------------------------------------------------ real-desktop self-test
def diff_mask(a, c, threshold=24):
    """Binary mask of changed pixels: what the fighters drew, never the taskbar's own pixels or button titles."""
    from PIL import ImageChops
    return ImageChops.difference(a.convert('RGB'), c.convert('RGB')).convert('L').point(lambda v: 255 if v > threshold else 0)


def count(mask, region=None):
    if region:
        mask = mask.crop(region)
    h = mask.convert('L').histogram()
    return sum(h) - h[0]


def cmd_selftest(args):
    """Real-desktop check.  Refuses unless the taskbar is at the bottom and <= 96 px high; captures only the taskbar rows
    of the roam zone, keeps nothing but thresholded difference masks, and restores whatever was running before."""
    from PIL import ImageGrab, Image, ImageDraw
    from minis_win import shell
    from minis_core import director
    cfg = cfgmod.load()
    l, t, r, b, edge = shell.taskbar_rect()
    if edge != 3 or b - t > 96 or shell.taskbar_autohide():
        print(f'selftest-gui: refused (taskbar edge={edge}, band={b - t}px, autohide={shell.taskbar_autohide()}); needs a bottom taskbar <= 96 px')
        return 2
    was = {role: bool(running(role)) for role in ROLES}
    z0, z1 = cfg['zone']
    bbox = (int(z0 - 36), t, int(z1 + 36), b)
    ok, res = False, {}
    try:
        cmd_stop()
        time.sleep(0.8)
        bare = ImageGrab.grab(bbox=bbox, all_screens=False)
        cmd_start()
        time.sleep(8.0)
        vis = ImageGrab.grab(bbox=bbox, all_screens=False)
        shell.raise_taskbar()
        time.sleep(0.05)
        raised = ImageGrab.grab(bbox=bbox, all_screens=False)
        time.sleep(0.8)
        after = ImageGrab.grab(bbox=bbox, all_screens=False)
        masks = [diff_mask(bare, im) for im in (vis, raised, after)]
        del vis, raised, after, bare                      # raw captures are never written anywhere
        w, h = masks[0].size
        assigned = {s: director.slot_assignment(director.read_assign(), s) for s in SLOTS}
        res = dict(visible=count(masks[0]), visible_left=count(masks[0], (0, 0, w // 2, h)), visible_right=count(masks[0], (w // 2, 0, w, h)),
                   raised_before_tick=count(masks[1]), after_raise_tick=count(masks[2]),
                   assigned={s: (a or {}).get('character') for s, a in assigned.items()})
        ok = res['visible'] > 300 and res['after_raise_tick'] > 300
        if assigned['a']:
            ok = ok and res['visible_left'] > 80
        if assigned['b']:
            ok = ok and res['visible_right'] > 80
        comp = Image.new('L', (w, h * 3 + 12), 64)
        for i, m in enumerate(masks):
            comp.paste(m, (0, i * (h + 6)))
        out = ROOT / 'qa' / 'gui-mask.png'
        out.parent.mkdir(exist_ok=True)
        comp.save(out)
        print(res)
        print('selftest-gui:', 'PASS' if ok else 'FAIL', '-> difference masks (fighters running / right after a raise / after the tick):', out)
    finally:
        if not args.keep:
            if not any(was.values()):
                cmd_stop()
            elif not all(was[r] for r in ROLES):
                cmd_stop()
                print('note: only some processes were running before; all were stopped - run `minis.py start` to restore')
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name, fn in (('start', cmd_start), ('stop', cmd_stop), ('status', cmd_status), ('pause', cmd_pause), ('resume', cmd_resume),
                     ('print-startup', cmd_print_startup), ('director', cmd_director)):
        sub.add_parser(name).set_defaults(fn=fn)
    r = sub.add_parser('run')
    r.add_argument('slot', choices=SLOTS + (ARENA,))
    r.add_argument('--monitor', type=int, default=None)
    r.add_argument('--freeze', action='store_true')
    r.add_argument('--seconds', type=float, default=None)
    r.add_argument('--seed', type=int, default=None)
    r.set_defaults(fn=cmd_run)
    w = sub.add_parser('winners', help='how match winners are drawn')
    w.add_argument('mode', choices=('decided', 'random'))
    w.set_defaults(fn=cmd_winners)
    sub.add_parser('monitors', help='list monitors for arena --monitor N').set_defaults(fn=cmd_monitors)
    ar = sub.add_parser('arena', help='arena mode: fighters break out onto a whole monitor')
    ar.add_argument('action', nargs='?', default='start', choices=('start', 'stop', 'capture'))
    ar.add_argument('path', nargs='?', default=None)
    ar.add_argument('--monitor', type=int, default=None, help='required for start: see `monitors`')
    ar.add_argument('--freeze', action='store_true', help='snapshot the monitor into RAM as the stage backdrop')
    ar.add_argument('--seconds', type=float, default=None, help='leave on its own after this long')
    ar.add_argument('--seed', type=int, default=None, help='fix the choreography seed (captures, previews)')
    ar.set_defaults(fn=cmd_arena)
    p = sub.add_parser('plates', help='show or hide both HUD plates')
    p.add_argument('state', choices=('on', 'off'))
    p.set_defaults(fn=cmd_plates)
    d = sub.add_parser('demo', help='start one bout now')
    d.add_argument('kind', nargs='?', default='spar', choices=('spar', 'clash', 'ranged', 'match'))
    d.set_defaults(fn=cmd_demo)
    s = sub.add_parser('selftest-gui')
    s.add_argument('--keep', action='store_true', help='leave the fighters running afterwards')
    s.set_defaults(fn=cmd_selftest)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
