"""Runs ONE real fighter slot process for tests/test_integration_processes.py (not a test itself).

    LOCALAPPDATA=<temp> python tests/two_process_harness.py a|b

Everything is real (minis.run_slot, Fighter, Brain, the bus files, the monotonic clock, two separate processes) except:
- the source detector reads <data>/fake/<source>.json  {"state": ..., "ctx": ...}  instead of a transcript or process table
- the shell is headless: windows are not created; each present() appends "<mono> <x> <crc32>" to <data>/present-<slot>.log
  (set "real_windows": true in <data>/harness.json to draw on the real desktop instead)
- config overrides come from <data>/harness.json {"cfg": {...}}
"""
import json, os, sys, time, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import minis  # noqa: E402
from minis_core import config as cfgmod  # noqa: E402
from minis_core.sources import Activity  # noqa: E402


class FakeDetector:
    def __init__(self, source):
        self.source = source
        self.path = cfgmod.data_dir() / 'fake' / f'{source}.json'

    def poll(self, now):
        try:
            d = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return []
        return [Activity(self.source, self.source, self.source, d.get('state', 'idle'), d.get('ctx'), events=list(d.get('events', [])))]


class HeadlessOverlay:
    def __init__(self, title, x, y, w, h, scale=1, on_event=None, on_timer=None):
        self.title, self.x, self.y, self.scale, self.on_event, self.on_timer = title, x, y, scale, on_event, on_timer
        self.visible = True
        self.log = cfgmod.data_dir() / f'present-{title.replace("minis-", "")}.log'

    def pump(self):
        return True

    def present(self, im, x=None):
        if x is not None:
            self.x = int(x)
        with open(self.log, 'a', encoding='ascii') as f:
            f.write(f'{time.monotonic():.3f} {self.x} {zlib.crc32(im.tobytes()):08x}\n')
        return True

    def show(self, v):
        self.visible = v

    def reassert_topmost(self):
        pass

    def move(self, x, y):
        self.x, self.y = x, y

    def set_scale(self, s):
        self.scale = s

    def menu(self, items):
        return 0

    def close(self):
        pass


class HeadlessShell:
    Overlay = HeadlessOverlay

    def __init__(self, real):
        self.real = real

    def taskbar_rect(self):
        return (0, 1392, 2560, 1440, 3)

    def taskbar_autohide(self):
        return False

    def screen_size(self):
        return 2560, 1440

    def fullscreen_busy(self):
        return False

    def make_mutex(self, name):
        return self.real.make_mutex(name)


def main(slot):
    from minis_win import shell as real_shell
    try:
        h = json.loads((cfgmod.data_dir() / 'harness.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        h = {}
    cfg = cfgmod.load()
    cfg.update(h.get('cfg', {}))
    sh = real_shell if h.get('real_windows') else HeadlessShell(real_shell)
    return minis.run_slot(slot, sh, cfg, detector_for=lambda source, cfg: FakeDetector(source))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
