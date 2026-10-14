"""User controls shared by every fighter: %LOCALAPPDATA%\\minis\\control.json
  {"paused": bool, "plates": bool, "winners": "decided"|"random", "demo": {"id", "kind", "ts"}, "arena_stop": ts}
and the arena's own heartbeat file arena.json {"pid", "monitor", "freeze", "phase", "round", "hp", "ts"} (written by the
arena process every ~1 s; the taskbar fighters hide while it is fresh)."""
from __future__ import annotations
import json, time
from pathlib import Path

from . import config as cfgmod
from .bus import write_json_atomic


def control_path() -> Path:
    return cfgmod.data_dir() / 'control.json'


_cache = {}


def read(path=None) -> dict:
    p = Path(path) if path else control_path()
    try:
        st = p.stat()
        sig = (st.st_mtime_ns, st.st_size)
        hit = _cache.get(str(p))
        if hit and hit[0] == sig:
            return hit[1]
        data = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        return {}
    _cache[str(p)] = (sig, data)
    return data


def paused(path=None) -> bool:
    return bool(read(path).get('paused', False))


def _update(path, **kw) -> bool:
    data = dict(read(path), ts=time.time(), **kw)
    return write_json_atomic(Path(path) if path else control_path(), data)


def set_paused(flag: bool, path=None) -> bool:
    return _update(path, paused=bool(flag))


def plates_on(path=None) -> bool:
    """HUD plates shown (the default) or hidden entirely (`minis.py plates off`, or the right-click menu)."""
    return read(path).get('plates', True) is not False


def set_plates(flag: bool, path=None) -> bool:
    return _update(path, plates=bool(flag))


DEMO_KINDS = ('spar', 'clash', 'ranged', 'match')
WINNER_MODES = ('decided', 'random')
ARENA_FRESH_S = 4.0


def winners(path=None) -> str:
    """How match winners are drawn: `decided` (biased by the health score, the default) or `random`."""
    v = read(path).get('winners')
    return v if v in WINNER_MODES else 'decided'


def set_winners(mode: str, path=None) -> bool:
    if mode not in WINNER_MODES:
        raise ValueError(mode)
    return _update(path, winners=mode)


# ---------------------------------------------------------------- arena mode
def arena_path() -> Path:
    return cfgmod.data_dir() / 'arena.json'


def write_arena_state(state: dict, path=None, now=None) -> bool:
    """The arena process's heartbeat (numbers / enums only: pid, monitor index, phase, round, hp)."""
    now = time.time() if now is None else now
    return write_json_atomic(Path(path) if path else arena_path(), dict(state, ts=now))


def clear_arena_state(path=None) -> bool:
    return write_json_atomic(Path(path) if path else arena_path(), {'active': False, 'ts': time.time()})


def arena_state(path=None, now=None):
    """-> the arena heartbeat while it is fresh and active, else None."""
    d = read(path or arena_path())
    now = time.time() if now is None else now
    try:
        if d.get('active') and 0 <= now - float(d.get('ts', 0)) <= ARENA_FRESH_S:
            return d
    except (TypeError, ValueError):
        pass
    return None


def arena_active(path=None, now=None) -> bool:
    return arena_state(path, now) is not None


def request_arena_stop(path=None, now=None) -> bool:
    now = time.time() if now is None else now
    return _update(path, arena_stop=now)


def arena_stop_requested(since, path=None) -> bool:
    """True when an `arena stop` was asked for after the arena started (`since`, wall-clock)."""
    try:
        return float(read(path).get('arena_stop', 0)) > float(since)
    except (TypeError, ValueError):
        return False
DEMO_MAX_AGE_S = 15.0


def request_demo(kind='spar', path=None, now=None) -> bool:
    """Ask the fighters for one bout right now (`minis.py demo`, or the right-click menu).  Only the choreography is
    forced: the plates keep showing the real state and numbers."""
    if kind not in DEMO_KINDS:
        raise ValueError(kind)
    now = time.time() if now is None else now
    return _update(path, demo={'id': '%x' % int(now * 1000), 'kind': kind, 'ts': now})


def demo(path=None, now=None):
    """-> {'id','kind','ts'} of a demo request younger than DEMO_MAX_AGE_S, else None."""
    d = read(path).get('demo')
    now = time.time() if now is None else now
    try:
        if isinstance(d, dict) and d.get('kind') in DEMO_KINDS and 0 <= now - float(d['ts']) <= DEMO_MAX_AGE_S:
            return d
    except (KeyError, TypeError, ValueError):
        pass
    return None
