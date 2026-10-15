"""Process facts on macOS through /bin/ps only (no psutil, no sysctl ctypes): list processes, executable path, CPU time,
command line - the same shape as minis_win.procs, so sources.ProcessScanner and `minis.py stop` work unchanged.

Rules kept from Windows:
- Command lines are only pattern-matched or compared, never stored, logged or printed.
- `stop` kills only a pid whose exact argv is ours (pid file + argv check), SIGTERM first, SIGKILL only if it is STILL ours.
Single instance per role: an exclusive flock on a lock file in the data dir (released by the OS when the process dies).

Everything that touches the OS is injectable, so tests/test_mac_procs.py runs on Windows with canned ps output.
"""
from __future__ import annotations
import os, re, signal, subprocess, time
from pathlib import Path

PS = '/bin/ps'
PS_ENV = {'LC_ALL': 'C', 'LANG': 'C', 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'}     # fixed lstart format, no user PATH
TABLE_ARGS = ['-ww', '-axo', 'pid=,ppid=,time=,lstart=,comm=']     # -ww: never cut long paths


def run_ps(args, timeout=5.0):
    """stdout of /bin/ps with a fixed C locale, or '' when it fails."""
    try:
        r = subprocess.run([PS] + list(args), capture_output=True, text=True, env=PS_ENV, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ''
    return r.stdout if r.returncode == 0 else ''


def parse_cputime(s):
    """BSD ps `time`: '0:01.23', '12:34.56', '1:02:03', '2-01:02:03' -> seconds (float), or None."""
    s = (s or '').strip()
    if not s:
        return None
    days = 0
    if '-' in s:
        d, s = s.split('-', 1)
        try:
            days = int(d)
        except ValueError:
            return None
    try:
        parts = [float(p) for p in s.split(':')]
    except ValueError:
        return None
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return days * 86400 + secs


def parse_ps_table(text):
    """Lines of `ps -axo pid=,ppid=,time=,lstart=,comm=` -> [dict(pid, ppid, cpu, start, path, name)].
    lstart is five tokens ('Wed Oct 15 10:00:00 2026', C locale) and is kept only as an opaque start token (it tells a
    reused pid from the original); comm is the executable's full path and may contain spaces; name is its lower-case
    basename (what the sources table matches)."""
    out = []
    for line in (text or '').splitlines():
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        path = parts[8].strip()
        out.append(dict(pid=pid, ppid=ppid, cpu=parse_cputime(parts[2]), start=' '.join(parts[3:8]), path=path,
                        name=os.path.basename(path.rstrip('/')).lower()))
    return out


def split_ps_args(line, script=None):
    """`ps -o args=` prints argv joined by spaces, so a path with spaces is ambiguous.  When the caller knows the script
    path it expects (ROOT/minis.py), split around it exactly: [interpreter path, script, *rest].  Otherwise whitespace."""
    line = (line or '').strip()
    if not line:
        return []
    if script:
        s = str(script)
        if line.endswith(' ' + s):
            return [line[:-len(s) - 1], s]
        i = line.find(' ' + s + ' ')
        if i > 0:
            return [line[:i], s] + line[i + len(s) + 2:].split()
    return line.split()


# ------------------------------------------------------------------ snapshot (one ps call per scan)
class Snapshot:
    """The last process table.  list() refreshes it; path() / times() read it (falling back to a per-pid ps call)."""

    def __init__(self, ps=run_ps):
        self.ps = ps
        self.rows = {}

    def refresh(self):
        self.rows = {r['pid']: r for r in parse_ps_table(self.ps(TABLE_ARGS))}
        return self.rows

    def row(self, pid):
        r = self.rows.get(int(pid))
        if r is None:
            got = parse_ps_table(self.ps(['-ww', '-o', 'pid=,ppid=,time=,lstart=,comm=', '-p', str(int(pid))]))
            r = got[0] if got else None
        return r


_snap = Snapshot()


def list_processes():
    """-> [(pid, ppid, exe name lower-case)]"""
    return [(r['pid'], r['ppid'], r['name']) for r in _snap.refresh().values()]


def image_path(pid):
    r = _snap.row(pid)
    return r['path'] if r else None


def times(pid):
    """-> (start token, CPU seconds user+system) or None."""
    r = _snap.row(pid)
    if not r or r['cpu'] is None:
        return None
    return r['start'], r['cpu']


def argv(pid, script=None, ps=None):
    """argv of a live process via `ps -o args=`, or None when it cannot be read.  Compared, never kept."""
    out = (ps or run_ps)(['-ww', '-o', 'args=', '-p', str(int(pid))])
    line = out.strip()
    if not line:
        return None
    return split_ps_args(line.splitlines()[0], script)


def alive(pid, kill=os.kill):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                                   # exists, owned by someone else
    except (OSError, ValueError, TypeError):
        return False


def terminate(pid, still_ours, grace_s=3.0, kill=os.kill, is_alive=None, sleep=time.sleep, clock=time.monotonic):
    """SIGTERM, wait up to `grace_s`, then SIGKILL only if `still_ours()` is still true.  -> True when the pid is gone."""
    is_alive = is_alive or (lambda p: alive(p, kill))
    try:
        kill(int(pid), signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    end = clock() + grace_s
    while clock() < end:
        if not is_alive(pid):
            return True
        sleep(0.1)
    if not is_alive(pid):
        return True
    if not still_ours():                              # pid reused while we waited: never kill a stranger
        return False
    try:
        kill(int(pid), getattr(signal, 'SIGKILL', signal.SIGTERM))
    except ProcessLookupError:
        return True
    except OSError:
        return False
    sleep(0.2)
    return not is_alive(pid)


# ------------------------------------------------------------------ single instance
def lock_path(name, lock_dir):
    """Lock-file path for a mutex name like 'Local\\minis-a-1a2b3c4d' (anything but [A-Za-z0-9._-] becomes '_')."""
    return Path(lock_dir) / (re.sub(r'[^A-Za-z0-9._-]', '_', str(name)) + '.lock')


_locks = []                                           # open lock files: kept for the process lifetime


def make_mutex(name, lock_dir=None, flock=None):
    """-> (handle, already_running), like minis_win.shell.make_mutex.  An exclusive non-blocking flock on a file in
    the data dir; the OS drops it when the process exits, however it exits."""
    if lock_dir is None:
        from minis_core import config as cfgmod
        lock_dir = cfgmod.data_dir() / 'locks'
    Path(lock_dir).mkdir(parents=True, exist_ok=True)
    p = lock_path(name, lock_dir)
    if flock is None:
        import fcntl
        flock = lambda fd: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)      # noqa: E731
    fh = open(p, 'a+')
    try:
        flock(fh.fileno())
    except (BlockingIOError, PermissionError, OSError):
        fh.close()
        return None, True
    _locks.append(fh)
    return fh, False


class Info:
    """The real process facts, in the shape sources.ProcessScanner expects."""
    list = staticmethod(list_processes)
    path = staticmethod(image_path)
    times = staticmethod(times)
    argv = staticmethod(argv)
