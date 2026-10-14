"""The director: which two sources get a fighter.  Pure and testable; the `minis.py director` process only feeds it
Activities every 2 s and writes the result.

Rules
- At most two sources, slot `a` (left) and slot `b` (right), picked by recency of activity.
- Stable: a slot keeps its source until another source is active (working / waiting, or active within `director_idle_s`)
  AND the slot's own source has been idle longer than `director_idle_s` (60 s).  Working or waiting counts as active now.
- A source that vanishes keeps its slot for `director_grace_s` (one bad poll must not swap characters).
- An empty slot is filled with the most recently active unassigned source.

Output (assign.json, written atomically):
  {"a": {"source": id, "character": c, "program": name} | null, "b": ..., "ts": wall-clock seconds}
"""
from __future__ import annotations
import json, time
from pathlib import Path

from . import config as cfgmod
from .bus import write_json_atomic

SLOTS = ('a', 'b')
ACTIVE_STATES = ('working', 'waiting')


def assign_path() -> Path:
    return cfgmod.data_dir() / 'assign.json'


def idle_for(act, now):
    return 0.0 if act.state in ACTIVE_STATES else max(0.0, now - (act.last_active or 0.0))


class Director:
    def __init__(self, cfg, resolve=None):
        self.cfg = cfg
        if resolve is None:
            from .atlas import resolve
        self.resolve = resolve
        self.slots = {s: None for s in SLOTS}          # slot -> source id
        self.info = {}                                 # source id -> (character, program) last seen
        self.missing_since = {}

    def step(self, acts, now):
        """-> {slot: source id | None}"""
        idle_s, grace = self.cfg['director_idle_s'], self.cfg['director_grace_s']
        by_id = {}
        for a in acts:
            by_id.setdefault(a.source_id, a)
            self.info[a.source_id] = (a.character, a.program)
        for s in SLOTS:
            sid = self.slots[s]
            if sid is None:
                continue
            if sid in by_id:
                self.missing_since.pop(sid, None)
            elif now - self.missing_since.setdefault(sid, now) >= grace:
                self.slots[s] = None
                self.missing_since.pop(sid, None)
        assigned = {v for v in self.slots.values() if v}
        free = sorted((a for a in by_id.values() if a.source_id not in assigned),
                      key=lambda a: (idle_for(a, now), -(a.last_active or 0.0), a.source_id))
        for s in SLOTS:
            if self.slots[s] is None and free:
                self.slots[s] = free.pop(0).source_id
        for cand in list(free):
            if idle_for(cand, now) > idle_s:
                break                                   # sorted: nobody after this one is active either
            victims = [(idle_for(by_id[sid], now), s) for s, sid in self.slots.items() if sid in by_id and idle_for(by_id[sid], now) > idle_s]
            if not victims:
                break
            _, s = max(victims)
            self.slots[s] = cand.source_id
        return dict(self.slots)

    def assignment(self, now):
        out = {}
        for s in SLOTS:
            sid = self.slots[s]
            if sid is None:
                out[s] = None
            else:
                ch, prog = self.info.get(sid, (sid, sid))
                out[s] = {'source': sid, 'character': self.resolve(ch), 'program': prog}
        out['ts'] = now
        return out


def write_assign(data, path=None) -> bool:
    return write_json_atomic(Path(path) if path else assign_path(), data)


_cache = {}


def read_assign(path=None):
    """-> the assign dict, or None when the file is missing / corrupt.  Stat-cached: cheap to call every second."""
    p = Path(path) if path else assign_path()
    try:
        st = p.stat()
        sig = (st.st_mtime_ns, st.st_size)
        hit = _cache.get(str(p))
        if hit and hit[0] == sig:
            return hit[1]
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    _cache[str(p)] = (sig, data)
    return data


def slot_assignment(data, slot):
    """The {'source','character','program'} for a slot, or None.  Tolerates malformed entries."""
    if not isinstance(data, dict):
        return None
    v = data.get(slot)
    if isinstance(v, dict) and isinstance(v.get('source'), str) and isinstance(v.get('character'), str):
        return v
    return None


class Runner:
    """The director loop body: poll sources, step, write assign.json when it changes (and as a heartbeat every 10 s)."""

    def __init__(self, cfg, sources, director=None, path=None, clock=time.time):
        self.cfg, self.sources, self.clock = cfg, sources, clock
        self.director = director or Director(cfg)
        self.path = path
        self.last_written = None
        self.last_ts = -1e18

    def step(self, now=None):
        now = self.clock() if now is None else now
        acts = self.sources.poll(now)
        self.director.step(acts, now)
        data = self.director.assignment(now)
        body = {k: v for k, v in data.items() if k != 'ts'}
        if body != self.last_written or now - self.last_ts >= 10.0:
            if write_assign(data, self.path):
                self.last_written, self.last_ts = body, now
        return data, acts
