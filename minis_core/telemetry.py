"""Read-only telemetry: newest Claude / Codex session -> state + numbers.  Never keeps or shows content.

Only enums and numbers leave the parsers (state, token counts, percentages); prompts, file names and
titles are never copied, logged or displayed.

Two stages, so time-based rules are re-applied on every poll even when the file has not changed:
  facts  - folded line by line from the transcript (only the appended bytes are read after the first poll)
  state  - derived from the facts and *now* (45 s waiting, 10 min idle guard, Codex plan-window expiry)
"""
from __future__ import annotations
import datetime, hashlib, json, os, time
from dataclasses import dataclass, field

from . import config as cfgmod


@dataclass
class Snapshot:
    who: str
    state: str = 'sleeping'          # working | idle | waiting | sleeping | limit | done
    ctx_pct: float | None = None
    plan_pct: float | None = None
    plan_label: str = ''
    resets_in: str = ''
    age_s: float | None = None
    sid: str = ''
    events: list = field(default_factory=list)
    timed_out: bool = False          # idle only because the turn went quiet past the idle guard (not a finish)


def parse_iso(ts):
    try:
        return datetime.datetime.fromisoformat(str(ts).replace('Z', '+00:00')).timestamp()
    except Exception:
        return None


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def fmt_resets(seconds):
    if seconds is None or seconds <= 0:
        return ''
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f'{d}d {h}h'
    if h:
        return f'{h}h {m}m'
    return f'{m}m'


def _loads(ln):
    ln = ln.strip()
    if not ln:
        return None
    try:
        o = json.loads(ln)
    except Exception:
        return None
    return o if isinstance(o, dict) else None


def tail_objects(path, max_bytes=262144):
    """Last ~max_bytes of a JSONL file as parsed objects (a partial first line is dropped)."""
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        f.seek(max(0, size - max_bytes))
        data = f.read()
    lines = data.split(b'\n')
    if size > max_bytes:
        lines = lines[1:]
    return [o for o in (_loads(ln) for ln in lines) if o is not None]


# ------------------------------------------------------------------ Claude: facts + state
def claude_facts():
    return {'kind': None, 'ts': None, 'stop': None, 'ctx_tokens': None}


def fold_claude(f, o):
    t = o.get('type')
    if t in ('user', 'assistant'):
        f['kind'] = t
        f['ts'] = parse_iso(o.get('timestamp'))
        f['stop'] = (o.get('message') or {}).get('stop_reason') if t == 'assistant' else None
    if t == 'assistant':
        u = (o.get('message') or {}).get('usage')
        if isinstance(u, dict):
            try:
                n = sum(int(u.get(k) or 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
            except (TypeError, ValueError):
                n = 0
            if n > 0:                                     # a zero-usage line (synthetic / error turn) says nothing about context
                f['ctx_tokens'] = n
    return f


def claude_state(f, now, cfg, mtime=None) -> Snapshot:
    snap = Snapshot('claude')
    if f['ctx_tokens']:
        snap.ctx_pct = round(clamp(f['ctx_tokens'] / float(cfg['claude_window']) * 100), 1)
    if f['kind'] is None:
        snap.state = 'idle'
        return snap
    ts = f['ts'] or mtime or now
    age = max(0.0, now - ts)
    snap.age_s = age
    if f['kind'] == 'assistant':
        if f['stop'] == 'tool_use':
            state = 'waiting' if age > cfg['waiting_seconds'] else 'working'
        elif f['stop'] in (None, ''):
            state = 'working'
        else:
            state = 'idle'
    else:
        state = 'working'                                 # a user line (prompt or tool_result): the model is on it
    if state in ('working', 'waiting') and age > cfg['idle_guard_minutes'] * 60:
        state, snap.timed_out = 'idle', True
    snap.state = state
    return snap


def parse_claude(objs, now, cfg, mtime=None) -> Snapshot:
    f = claude_facts()
    for o in objs:
        fold_claude(f, o)
    return claude_state(f, now, cfg, mtime)


# ------------------------------------------------------------------ Codex: facts + state
def _plan_label(window_minutes):
    if window_minutes is None:
        return ''
    if window_minutes >= 6000:
        return 'wk'
    if abs(window_minutes - 300) < 30:
        return '5h'
    return f'{int(window_minutes)}m'


def codex_facts():
    return {'evt': None, 'ts': None, 'ctx_pct': None, 'info_seen': False, 'plan': None}


def fold_codex(f, o):
    ts = parse_iso(o.get('timestamp'))
    if ts:
        f['ts'] = ts
    if o.get('type') != 'event_msg':
        return f
    p = o.get('payload') or {}
    pt = p.get('type')
    if pt in ('task_started', 'task_complete', 'turn_aborted'):
        f['evt'] = pt
    if pt == 'token_count':
        info = p.get('info')
        if info:
            f['info_seen'] = True
            used = (info.get('last_token_usage') or {}).get('input_tokens')
            win = info.get('model_context_window')
            try:
                f['ctx_pct'] = round(clamp(float(used) / float(win) * 100), 1) if used is not None and win else None
            except (TypeError, ValueError, ZeroDivisionError):
                f['ctx_pct'] = None
        rl = p.get('rate_limits') or {}
        pr = rl.get('primary')
        # trust rule (part 1): the codex limit with a real primary window.  Part 2 (not already reset) is checked per poll.
        if rl.get('limit_id') == 'codex' and isinstance(pr, dict) and pr.get('resets_at') is not None:
            f['plan'] = {'used_percent': pr.get('used_percent'), 'window_minutes': pr.get('window_minutes'), 'resets_at': pr.get('resets_at')}
    return f


def codex_state(f, now, cfg, mtime=None) -> Snapshot:
    snap = Snapshot('codex')
    snap.ctx_pct = f['ctx_pct']
    plan = f['plan']
    try:
        resets = float(plan['resets_at']) if plan else 0.0
    except (TypeError, ValueError):
        resets = 0.0
    if plan and resets > now:
        snap.plan_pct = round(clamp(float(plan.get('used_percent') or 0)), 1)
        snap.plan_label = _plan_label(plan.get('window_minutes'))
        snap.resets_in = fmt_resets(resets - now)
    last_ts = f['ts'] or mtime or now
    age = max(0.0, now - last_ts)
    snap.age_s = age
    state = 'working' if f['evt'] == 'task_started' else 'idle'
    if state == 'working':
        if age > cfg['idle_guard_minutes'] * 60:
            state, snap.timed_out = 'idle', True
        elif age > cfg['waiting_seconds']:
            state = 'waiting'
    snap.state = state
    return snap


def parse_codex(objs, now, cfg, mtime=None) -> Snapshot:
    f = codex_facts()
    for o in objs:
        fold_codex(f, o)
    return codex_state(f, now, cfg, mtime)


KINDS = {'claude': (claude_facts, fold_claude, claude_state), 'codex': (codex_facts, fold_codex, codex_state)}


def _meaningful(who, f):
    return f['kind'] is not None if who == 'claude' else (f['evt'] is not None or f['info_seen'])


# ------------------------------------------------------------------ discovery
def claude_files(roots):
    for root in roots:
        try:
            with os.scandir(root) as it:
                for proj in it:
                    try:
                        if not proj.is_dir():
                            continue
                        with os.scandir(proj.path) as it2:
                            for f in it2:
                                if f.name.endswith('.jsonl'):
                                    try:                            # one unreadable entry must not hide the rest of the folder
                                        if f.is_file():
                                            yield f.path, f.stat().st_mtime
                                    except OSError:
                                        pass
                    except OSError:
                        pass
        except OSError:
            pass


def _digit_dirs(path):
    try:
        return sorted((d for d in os.listdir(path) if d.isdigit()), reverse=True)
    except OSError:                                       # missing, unreadable, or a stray *file* named like a year
        return []


def codex_files(roots, days=3):
    """rollout-*.jsonl from the newest `days` day folders of sessions/YYYY/MM/DD under each root."""
    for root in roots:
        seen = 0
        for y in _digit_dirs(root)[:2]:
            for m in _digit_dirs(os.path.join(root, y)):
                for d in _digit_dirs(os.path.join(root, y, m)):
                    if seen >= days:
                        break
                    seen += 1
                    try:
                        with os.scandir(os.path.join(root, y, m, d)) as it:
                            for f in it:
                                if f.name.startswith('rollout-') and f.name.endswith('.jsonl'):
                                    try:
                                        yield f.path, f.stat().st_mtime
                                    except OSError:
                                        pass
                    except OSError:
                        pass


# ------------------------------------------------------------------ transitions (shared with the process detectors)
class Transitions:
    """Adds the transient 'done' state, the 'limit' state and the one-shot events 'finished' / 'limit'."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.prev = None
        self.work_since = None
        self.done_until = 0.0
        self.limit_seen = False

    def reset(self):
        """A different session became the newest: its history is not this one's, so no 'finished' across the switch."""
        self.prev = None
        self.work_since = None

    def apply(self, snap, now):
        if snap.state == 'working' and self.work_since is None:
            self.work_since = now
        if self.prev in ('working', 'waiting') and snap.state == 'idle':
            if self.work_since is not None and now - self.work_since >= self.cfg['finished_min_work_s'] and not snap.timed_out:
                snap.events.append('finished')
                self.done_until = now + self.cfg['done_show_s']
            self.work_since = None
        if snap.state in ('idle', 'sleeping') and self.prev not in ('working', 'waiting'):
            self.work_since = None
        self.prev = snap.state
        top = max([v for v in (snap.ctx_pct, snap.plan_pct) if v is not None] or [0])
        if top >= self.cfg['limit_pct'] and snap.state != 'sleeping':
            if not self.limit_seen:
                snap.events.append('limit')
            self.limit_seen = True
            snap.state = 'limit'
        else:
            self.limit_seen = False
            if snap.state == 'idle' and now < self.done_until:
                snap.state = 'done'
        return snap


# ------------------------------------------------------------------ tracker
MAX_BACK = (262144, 1 << 20, 4 << 20, 16 << 20)        # how far back a first read goes to find one meaningful line
MAX_APPEND = 16 << 20


class Tracker:
    """Polls the newest session for one agent (claude | codex)."""

    def __init__(self, who, cfg, clock=time.time, feed_path=None):
        self.who, self.cfg, self.clock = who, cfg, clock
        self.new_facts, self.fold, self.derive = KINDS[who]
        self.feed_path = feed_path
        self._recent = None
        self._disc = -1e18
        self._quick_k = 0
        self.scans = 0
        self.path = None
        self.mtime = None
        self._file = None             # dict(path, offset, facts) for the current path only
        self.bytes_read = 0
        self.tr = Transitions(cfg)

    # -------------------------------------------------- discovery
    def _rescan(self, now):
        if self.who == 'claude':
            files = list(claude_files(cfgmod.expand(self.cfg['claude_dirs'])))
        else:
            files = list(codex_files(cfgmod.expand(self.cfg['codex_dirs'])))
        horizon = now - self.cfg['stale_session_hours'] * 3600
        files = sorted([f for f in files if f[1] >= horizon], key=lambda f: -f[1])[:40]
        self._recent = [p for p, _ in files]
        self._disc = now
        self.scans += 1

    def _best(self):
        best = None
        for p in self._recent or []:
            try:
                m = os.stat(p).st_mtime
            except OSError:
                continue
            if best is None or m > best[1]:
                best = (p, m)
        return best

    def _newest(self, now):
        """Full directory scan every 30 s; in between, stat just the recent candidates.  If the best candidate looks stale
        (> 2 min) a fresh file may have appeared that the last scan missed, so rescan sooner - after 5 s, then backing
        off 10, 20, 30 s while nothing fresh turns up (so an idle night does not rescan every 5 s)."""
        if self._recent is None or now - self._disc >= 30.0:
            self._rescan(now)
        best = self._best()
        if best is not None and now - best[1] <= 120:
            self._quick_k = 0
        elif now - self._disc >= min(30.0, 5.0 * (2 ** self._quick_k)):
            self._rescan(now)
            self._quick_k += 1
            best = self._best()
            if best is not None and now - best[1] <= 120:
                self._quick_k = 0
        return best or (None, 0)

    # -------------------------------------------------- reading
    def _fold_bytes(self, f, data, at_start):
        """Fold complete lines of `data`; returns the number of bytes consumed (up to the last newline).
        A trailing piece without a newline is folded if it parses, but not consumed (it is re-read next time)."""
        lines = data.split(b'\n')
        if not at_start:
            lines = lines[1:]                               # partial first line of a tail read
            skip = data.find(b'\n') + 1 if b'\n' in data else len(data)
        else:
            skip = 0
        tail = lines.pop() if lines else b''
        for ln in lines:
            o = _loads(ln)
            if o is not None:
                self.fold(f, o)
        o = _loads(tail)
        if o is not None:
            self.fold(f, o)
        consumed = len(data) - len(tail)
        return max(consumed, skip)

    def _initial(self, path, size):
        f = self.new_facts()
        with open(path, 'rb') as fh:
            for mb in MAX_BACK:
                start = max(0, size - mb)
                fh.seek(start)
                data = fh.read(size - start)
                self.bytes_read += len(data)
                f = self.new_facts()
                used = self._fold_bytes(f, data, start == 0)
                if _meaningful(self.who, f) or start == 0:
                    break
        return dict(path=path, offset=start + used, facts=f, size=size)

    def _append(self, st, size):
        with open(st['path'], 'rb') as fh:
            start = st['offset']
            at_line = True
            if size - start > MAX_APPEND:                    # a burst bigger than the cap: jump to its tail
                start, at_line = size - MAX_APPEND, False
            fh.seek(start)
            data = fh.read(size - start)
        self.bytes_read += len(data)
        used = self._fold_bytes(st['facts'], data, at_line)
        st['offset'] = start + used
        st['size'] = size

    def _facts(self, path):
        """-> facts for path, or None if the file vanished before it could be read for the first time."""
        st = self._file
        try:
            size = os.path.getsize(path)
            if st is None or st['path'] != path or size < st['offset']:      # new file, or truncated / rewritten
                self._file = st = self._initial(path, size)
            elif size != st['size']:
                self._append(st, size)
        except OSError:
            if st is None or st['path'] != path:
                return None
        return st['facts']

    def _plan_feed(self, now):
        p = self.feed_path or (cfgmod.data_dir() / 'feeds' / 'claude-plan.json')
        try:
            with open(p, encoding='utf-8') as fh:
                d = json.load(fh)
            ts = parse_iso(d.get('ts'))
            if ts and now - ts <= self.cfg['plan_feed_max_age_min'] * 60:
                v = d.get('five_hour')
                if v is not None:
                    return round(clamp(float(v)), 1), '5h'
        except Exception:
            pass
        return None, ''

    # -------------------------------------------------- poll
    def poll(self, now=None) -> Snapshot:
        now = self.clock() if now is None else now
        path, mtime = self._newest(now)
        if path != self.path:
            self.tr.reset()
            self._file = None                               # keep parsed state for the current path only
            self.path = path
        self.mtime = mtime if path else None
        stale = self.cfg['stale_session_hours'] * 3600
        snap = None
        if path and now - mtime <= stale:
            f = self._facts(path)
            if f is not None:
                snap = self.derive(f, now, self.cfg, mtime)
                snap.who = self.who
                snap.sid = hashlib.sha1(path.encode()).hexdigest()[:6]
                if now - mtime > self.cfg['sleep_minutes'] * 60:
                    snap.state = 'sleeping'
        if snap is None:
            snap = Snapshot(self.who, 'sleeping')
        if self.who == 'claude' and snap.plan_pct is None:
            snap.plan_pct, snap.plan_label = self._plan_feed(now)
        return self.tr.apply(snap, now)
