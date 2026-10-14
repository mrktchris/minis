"""The director: which two sources get a fighter.  Pure and testable; the `minis.py director` process only feeds it
Activities every 2 s and writes the result.

Rules
- At most two sources, slot `a` (left) and slot `b` (right), picked by recency of activity.
- Stable: a slot keeps its source until another source is active (working / waiting, or active within `director_idle_s`)
  AND the slot's own source has been idle longer than `director_idle_s` (60 s).  Working or waiting counts as active now.
- A source that vanishes keeps its slot for `director_grace_s` (one bad poll must not swap characters).
- An empty slot is filled with the most recently active unassigned source.
- Dormant partner (V5.1): a source that stops being reported (its program closed, its session file aged out) stays a
  candidate for `dormant_hours` after its last activity, as if it were idle since then.  So the most recently used
  other program keeps its slot, asleep and dimmed, until a different program becomes active.  What the director has
  seen (source -> last activity, character, program) survives a restart through seen.json.
- Sparring bot (V5.1, `sparring_bot`): one fighter alone and no dormant candidate: the pseudo-source `sparring`
  (generic skin, plate 'Sparring bot', no numbers) takes the empty slot, and gives it back to any real source.

Output (assign.json, written atomically):
  {"a": {"source": id, "character": c, "program": name[, "dormant": true][, "bot": true]} | null, "b": ..., "ts": seconds}
"""
from __future__ import annotations
import json, time
from pathlib import Path

from . import config as cfgmod
from .bus import write_json_atomic

SLOTS = ('a', 'b')
ACTIVE_STATES = ('working', 'waiting')
SPARRING = 'sparring'                                  # the pseudo-source; never reported by any detector
SPARRING_ASSIGN = {'source': SPARRING, 'character': 'generic', 'program': 'Sparring bot', 'bot': True}


def assign_path() -> Path:
    return cfgmod.data_dir() / 'assign.json'


def seen_path() -> Path:
    return cfgmod.data_dir() / 'seen.json'


def idle_for(act, now):
    return 0.0 if act.state in ACTIVE_STATES else max(0.0, now - (act.last_active or 0.0))


class _Dormant:
    """A remembered source that no detector reports right now, ranked as idle since its last activity."""
    state = 'idle'

    def __init__(self, source_id, rec):
        self.source_id = source_id
        self.last_active = float(rec.get('last_active') or 0.0)
        self.character = rec.get('character') or source_id
        self.program = rec.get('program') or source_id


class Director:
    def __init__(self, cfg, resolve=None, seen=None):
        self.cfg = cfg
        if resolve is None:
            from .atlas import resolve
        self.resolve = resolve
        self.slots = {s: None for s in SLOTS}          # slot -> source id
        self.info = {}                                 # source id -> (character, program) last seen
        self.missing_since = {}
        self.seen = {}                                 # source id -> {'last_active', 'character', 'program'}
        for sid, rec in (seen or {}).items():
            if isinstance(sid, str) and isinstance(rec, dict) and sid != SPARRING:
                try:
                    self.seen[sid] = dict(last_active=float(rec.get('last_active') or 0.0),
                                          character=str(rec.get('character') or sid), program=str(rec.get('program') or sid))
                except (TypeError, ValueError):
                    pass
        self.dormant = {s: False for s in SLOTS}

    def _remember(self, acts, now):
        for a in acts:
            if a.source_id == SPARRING:
                continue
            last = max(float(a.last_active or 0.0), now if a.state in ACTIVE_STATES else 0.0)
            rec = self.seen.get(a.source_id)
            if rec is None:
                self.seen[a.source_id] = dict(last_active=last, character=a.character, program=a.program)
            else:
                rec['last_active'] = max(rec['last_active'], last)
                rec['character'], rec['program'] = a.character, a.program

    def _dormant_pool(self, live, now):
        horizon = float(self.cfg.get('dormant_hours', 24)) * 3600.0
        out = {}
        for sid, rec in self.seen.items():
            if sid in live or rec['last_active'] <= 0.0 or now - rec['last_active'] > horizon:
                continue
            out[sid] = _Dormant(sid, rec)
        return out

    def step(self, acts, now):
        """-> {slot: source id | None}"""
        idle_s, grace = self.cfg['director_idle_s'], self.cfg['director_grace_s']
        live = {}
        for a in acts:
            if a.source_id != SPARRING:
                live.setdefault(a.source_id, a)
        self._remember(live.values(), now)
        pool = dict(live)
        pool.update(self._dormant_pool(live, now))
        for a in pool.values():
            self.info[a.source_id] = (a.character, a.program)
        for s in SLOTS:
            sid = self.slots[s]
            if sid == SPARRING:                         # the bot is the last resort: every step re-decides it
                self.slots[s] = None
                continue
            if sid is None:
                continue
            if sid in pool:
                self.missing_since.pop(sid, None)
            elif now - self.missing_since.setdefault(sid, now) >= grace:
                self.slots[s] = None
                self.missing_since.pop(sid, None)
        assigned = {v for v in self.slots.values() if v}
        free = sorted((a for a in pool.values() if a.source_id not in assigned),
                      key=lambda a: (idle_for(a, now), -(a.last_active or 0.0), a.source_id))
        for s in SLOTS:
            if self.slots[s] is None and free:
                self.slots[s] = free.pop(0).source_id
        for cand in list(free):
            if idle_for(cand, now) > idle_s:
                break                                   # sorted: nobody after this one is active either
            victims = [(idle_for(pool[sid], now), s) for s, sid in self.slots.items() if sid in pool and idle_for(pool[sid], now) > idle_s]
            if not victims:
                break
            _, s = max(victims)
            self.slots[s] = cand.source_id
        if self.cfg.get('sparring_bot', True):
            filled = [s for s in SLOTS if self.slots[s] is not None]
            if len(filled) == 1:
                self.slots[SLOTS[1 - SLOTS.index(filled[0])]] = SPARRING
        for s in SLOTS:
            sid = self.slots[s]
            self.dormant[s] = bool(sid) and sid != SPARRING and sid not in live
        return dict(self.slots)

    def assignment(self, now):
        out = {}
        for s in SLOTS:
            sid = self.slots[s]
            if sid is None:
                out[s] = None
            elif sid == SPARRING:
                out[s] = dict(SPARRING_ASSIGN, character=self.resolve(SPARRING_ASSIGN['character']))
            else:
                ch, prog = self.info.get(sid, (sid, sid))
                out[s] = {'source': sid, 'character': self.resolve(ch), 'program': prog}
                if self.dormant.get(s):
                    out[s]['dormant'] = True
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
    """The {'source','character','program'[, 'dormant'][, 'bot']} for a slot, or None.  Tolerates malformed entries."""
    if not isinstance(data, dict):
        return None
    v = data.get(slot)
    if isinstance(v, dict) and isinstance(v.get('source'), str) and isinstance(v.get('character'), str):
        return v
    return None


def read_seen(path=None) -> dict:
    """seen.json -> {source: {'last_active', 'character', 'program'}}; {} when missing or corrupt."""
    p = Path(path) if path else seen_path()
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}
    src = d.get('sources') if isinstance(d, dict) else None
    return src if isinstance(src, dict) else {}


def write_seen(seen, path=None, now=None) -> bool:
    return write_json_atomic(Path(path) if path else seen_path(), {'sources': seen, 'ts': time.time() if now is None else now})


class Runner:
    """The director loop body: poll sources, step, write assign.json when it changes (and as a heartbeat every 10 s);
    persist what was seen (seen.json) when it changed, at most every `seen_every_s`."""

    def __init__(self, cfg, sources, director=None, path=None, clock=time.time, seen_path=None, seen_every_s=30.0):
        self.cfg, self.sources, self.clock = cfg, sources, clock
        self.seen_path, self.seen_every_s = seen_path, seen_every_s
        self.director = director or Director(cfg, seen=read_seen(seen_path))
        self.path = path
        self.last_written = None
        self.last_ts = -1e18
        self.seen_written = None
        self.seen_ts = -1e18

    def step(self, now=None):
        now = self.clock() if now is None else now
        acts = self.sources.poll(now)
        self.director.step(acts, now)
        data = self.director.assignment(now)
        body = {k: v for k, v in data.items() if k != 'ts'}
        if body != self.last_written or now - self.last_ts >= 10.0:
            if write_assign(data, self.path):
                self.last_written, self.last_ts = body, now
        seen = {k: dict(v) for k, v in self.director.seen.items()}
        if seen != self.seen_written and now - self.seen_ts >= self.seen_every_s:
            if write_seen(seen, self.seen_path, now):
                self.seen_written, self.seen_ts = seen, now
        return data, acts
