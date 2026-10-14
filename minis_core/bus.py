"""Loose coupling between the fighters: each process writes its own small JSON file and reads the other's.
No sockets, no shared memory, no startup order.  A missing / stale / corrupt / 'gone' partner file simply means 'solo'.
Files are keyed by slot (`a`, `b`); `ts` is wall-clock time, used only to judge staleness.
"""
from __future__ import annotations
import json, os, time
from pathlib import Path

from . import config as cfgmod


def bus_dir(root=None) -> Path:
    d = Path(root) if root else cfgmod.data_dir() / 'bus'
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json_atomic(target: Path, payload, retries=5) -> bool:
    """Temp file + os.replace.  Never raises on an OSError (disk full, locked, permissions): returns False instead."""
    target = Path(target)
    tmp = target.with_name(f'.{target.stem}.{os.getpid()}.tmp')
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    for _ in range(retries):                 # a reader may hold the target open for a moment on Windows
        try:
            os.replace(tmp, target)
            return True
        except PermissionError:
            time.sleep(0.01)
        except OSError:
            break
    try:
        tmp.unlink()
    except OSError:
        pass
    return False


def write(who: str, payload: dict, root=None, now=None):
    try:
        d = bus_dir(root)
    except OSError:
        return False
    payload = dict(payload, who=who, ts=(time.time() if now is None else now))
    return write_json_atomic(d / f'{who}.json', payload)


def write_gone(who: str, root=None, now=None):
    """A real timestamp (not 0) so `status` can tell 'stopped cleanly a moment ago' from 'never ran'."""
    return write(who, dict(state='gone', mode='gone', x=0, facing=1, anim='idle', ctx=None, event=None), root=root, now=now)


_read_cache = {}


def read(who: str, root=None, now=None, stale_s=5.0, raw=False):
    """The partner's last payload, or None when it is missing, stale, corrupt or 'gone'.  raw=True keeps 'gone' and stale
    payloads (for `status`)."""
    try:
        p = bus_dir(root) / f'{who}.json'
        st = p.stat()
        sig = (st.st_mtime_ns, st.st_size)
        hit = _read_cache.get(str(p))
        if hit and hit[0] == sig:
            data = hit[1]
        else:
            data = json.loads(p.read_text(encoding='utf-8'))
            _read_cache[str(p)] = (sig, data)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if raw:
        return data
    now = time.time() if now is None else now
    try:
        if now - float(data.get('ts', 0)) > stale_s:
            return None
    except (TypeError, ValueError):
        return None
    if data.get('state') == 'gone' or data.get('mode') == 'gone':
        return None
    return data
