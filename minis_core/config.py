"""Config: sensible defaults, optional overrides from minis.json next to minis.py."""
from __future__ import annotations
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    # roam zone on the primary display (screen x). Measured on the author's PC (2560x1440, 100% DPI,
    # centred icons): the empty stretch left of the icon cluster is x 0-940. Override in minis.json. Never walk over the icon cluster.
    "zone": [40, 900],
    "claude_window": 1_000_000,            # context window of the current Claude model (reported by the app)
    "claude_dirs": ["~/.claude/projects"],
    "codex_dirs": ["~/.codex/sessions", "~/.codex-emdash/sessions"],
    "stale_session_hours": 24,
    "sleep_minutes": 30,
    "waiting_seconds": 45,
    "idle_guard_minutes": 10,
    "finished_min_work_s": 15,
    "done_show_s": 8,
    "plan_feed_max_age_min": 15,
    "limit_pct": 90,
    "fps_active": 10,
    "fps_idle": 4,
    "topmost_tick_ms": 250,
    "bout_min_s": 45,                      # neither working: a spar / ranged duel this often
    "bout_max_s": 90,
    "console_min_s": 40,                   # partner knocked out (limit): visit and console it this often
    "console_max_s": 80,
    "shadowbox_min_s": 3,                  # a working fighter throws a shadow punch this often
    "shadowbox_max_s": 6,
    "walk_px_s": 40,
    "gap_px": 24,                          # hip-to-hip distance for close combat
    "plate": True,
    "clash_min_s": 20,                     # both agents working: a short clash this often
    "clash_max_s": 40,
    "invite_window_s": 3.0,                # an invite can only be accepted this long after it was sent
    "event_max_age_s": 3.0,                # older partner events are ignored (restart replay)
    "director_poll_s": 2.0,
    "director_idle_s": 60,                 # a slot keeps its source until that source is idle this long and another is active
    "director_grace_s": 6,                 # a source missing for less than this keeps its slot (one bad poll)
    "proc_working_cpu_pct": 15,            # process sources: tree CPU above this (% of one core) = working
    "proc_window_s": 6,                    # ... averaged over this many seconds
    "log_max_bytes": 65536,
    # V4: matches, scoreboard, arena
    "match_min_s": 180,                    # both awake: a best-of-3 match this often (on top of clashes / spars)
    "match_max_s": 360,
    "scoreboard": True,                    # the right-side widget (director process)
    "scoreboard_x": None,                  # screen x of the widget; None = just left of the icon cluster (zone end + 36 - width)
    "arena_monitor": None,                 # monitor index for the Arena button / menu item; None = the one non-primary monitor
    "arena_fps": 30,
    "arena_cpu_budget_pct": 10.0,          # of one core; above it the arena drops to 20 fps
    "arena_min_window_px": [160, 100],     # smaller window rects are not platforms
}


PLATE_W, PLATE_H, PLATE_SPACING = 128, 26, 4
PLATE_CLEAR_PX = 40                        # plate strip end -> lowest hip x; sprites reach at most 33 px from the hip


def plate_left(cfg, slot) -> int:
    """HUD plates do not travel with the fighters: both sit side by side, fixed, at the left end of the roam zone
    (slot a first, then slot b)."""
    return int(cfg['zone'][0]) + (0 if slot == 'a' else PLATE_W + PLATE_SPACING)


def fight_zone(cfg) -> tuple:
    """Where fighters may stand (hip x): the roam zone minus the plate strip, so a sprite never covers a plate."""
    if cfg.get('fight_zone'):
        z0, z1 = cfg['fight_zone']
        return float(z0), float(z1)
    z0, z1 = cfg['zone']
    if cfg.get('scoreboard', True):                                # the widget sits at the right end: stay clear of it too
        from . import scoreboard
        z1 = min(z1, scoreboard.left_x(cfg) - PLATE_CLEAR_PX)
    return float(z0 + 2 * PLATE_W + PLATE_SPACING + PLATE_CLEAR_PX), float(z1)


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    d = Path(base) / "minis"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(path: str | os.PathLike | None = None) -> dict:
    cfg = dict(DEFAULTS)
    p = Path(path) if path else ROOT / "minis.json"
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def expand(paths):
    return [Path(os.path.expanduser(p)) for p in paths]


def ui_scale(band_px: int) -> int:
    """Integer-only sprite scale (nearest neighbour, never blur): a 42 px fighter must fit the taskbar band."""
    return max(1, (int(band_px) - 4) // 42)
