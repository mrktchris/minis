"""Runs ONE real arena process headless for tests/test_integration_processes.py (not a test itself).

    LOCALAPPDATA=<temp> python tests/arena_harness.py

Everything is real (minis.run_arena, Arena, Compositor, control / arena.json heartbeats, the monotonic clock) except:
- the monitor is a synthetic rect from <data>/harness.json {"arena": {"rect": [l, t, r, b], "windows": [[id, l, t, r, b], ...],
  "seconds": S, "freeze": bool}}; the window list is that fixed list (no EnumWindows)
- the surface is minis_core.arena.Surface (RAM) instead of the layered window; a synthetic backdrop stands in for a screen grab
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import minis  # noqa: E402
from minis_core import arena as AR, config as cfgmod  # noqa: E402


class HeadlessShell:
    def __init__(self, real):
        self.real = real

    def make_mutex(self, name):
        return self.real.make_mutex(name)

    def monitors(self):
        return []

    def window_rects(self, exclude=()):
        return []


def main():
    from minis_win import shell as real_shell
    h = json.loads((cfgmod.data_dir() / 'harness.json').read_text(encoding='utf-8'))
    a = h['arena']
    rect = tuple(a['rect'])
    cfg = cfgmod.load()
    cfg.update(h.get('cfg', {}))
    surface = AR.Surface(rect[2] - rect[0], rect[3] - rect[1])
    bd = AR.synthetic_backdrop(surface.w, surface.h) if a.get('freeze') else None
    windows = [tuple(w) for w in a.get('windows', [])]
    return minis.run_arena(dict(monitor=a.get('monitor', 9), freeze=bool(a.get('freeze')), seconds=a.get('seconds')), HeadlessShell(real_shell), cfg,
                           monitor_rect=rect, windows_fn=lambda: windows, backdrop=bd, surface=surface, seed=a.get('seed', 1))


if __name__ == '__main__':
    sys.exit(main())
