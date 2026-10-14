"""A 7-day usage history for the scoreboard sparkline: %LOCALAPPDATA%\\minis\\history.json
  {"days": {"YYYY-MM-DD": {"ctx_max": float, "plan_max": float|null, "samples": int}}}
Numbers and dates only - never a source name beyond the character id, never titles or content.  The director feeds it
from the activities it already polls, at most once a minute; the file is written atomically and trimmed to 14 days."""
from __future__ import annotations
import datetime, json, time
from pathlib import Path

from . import config as cfgmod
from .bus import write_json_atomic

KEEP_DAYS = 14


def history_path() -> Path:
    return cfgmod.data_dir() / 'history.json'


def read(path=None) -> dict:
    p = Path(path) if path else history_path()
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        return d if isinstance(d, dict) and isinstance(d.get('days'), dict) else {'days': {}}
    except (OSError, ValueError):
        return {'days': {}}


def day_key(now):
    return datetime.date.fromtimestamp(now).isoformat()


class Recorder:
    def __init__(self, path=None, every_s=60.0):
        self.path, self.every_s = path, every_s
        self.last = -1e18

    def record(self, acts, now=None) -> bool:
        """Fold the activities' ctx% / plan% maxima into today's row (at most once per `every_s`)."""
        now = time.time() if now is None else now
        if now - self.last < self.every_s:
            return False
        self.last = now
        vals = [a for a in acts if getattr(a, 'ctx_pct', None) is not None or getattr(a, 'plan_pct', None) is not None]
        if not vals:
            return False
        d = read(self.path)
        key = day_key(now)
        row = d['days'].get(key) or {'ctx_max': None, 'plan_max': None, 'samples': 0}
        for a in vals:
            if a.ctx_pct is not None:
                row['ctx_max'] = float(a.ctx_pct) if row['ctx_max'] is None else max(row['ctx_max'], float(a.ctx_pct))
            if a.plan_pct is not None:
                row['plan_max'] = float(a.plan_pct) if row['plan_max'] is None else max(row['plan_max'], float(a.plan_pct))
        row['samples'] = int(row.get('samples', 0)) + 1
        d['days'][key] = row
        for k in sorted(d['days'])[:-KEEP_DAYS]:
            d['days'].pop(k, None)
        return write_json_atomic(Path(self.path) if self.path else history_path(), d)


def last_days(n=7, now=None, path=None, field='ctx_max'):
    """-> [value | None] for the last n days ending today (oldest first)."""
    now = time.time() if now is None else now
    d = read(path)['days']
    out = []
    for i in range(n - 1, -1, -1):
        key = day_key(now - i * 86400)
        row = d.get(key) or {}
        out.append(row.get(field))
    return out
