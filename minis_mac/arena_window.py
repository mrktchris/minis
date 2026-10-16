"""The arena overlay on macOS: one panel the size of the monitor, click-through except the EXIT button.

The same surface minis_core.arena.Compositor drives on Windows: write(img, x, y) replaces a rectangle, flush() shows the
changed parts, offset(dx, dy) shakes this window (never any other).  The picture is kept in a PIL canvas and shown as a grid
of TILE-point tile layers; a flush re-uploads only the tiles a dirty rectangle touches.

CPU (docs/MAC-HANDOFF.md FOUND-2; target <= 10 % of a core at normal intensity):
- 128-point tiles (V7 used 256): a spark or a sprite step re-uploads a quarter of the pixels it did.
- A tile that is fully transparent is not converted or uploaded at all: its layer's contents are set to nil (most of the
  overlay is empty, and a fighter moving away leaves empty tiles behind).  A tile already empty stays untouched.
- Colour / white flashes are a GPU layer (`tint`): one backgroundColor + opacity change, no full-canvas re-upload.  The
  compositor uses it whenever the surface has `tint` (Windows and the headless surface keep the full-frame path).
- The canvas stays at 1 pixel per point and Core Animation scales it on Retina with nearest filtering: no 2x
  conversion, premultiply or upload on the CPU.
- `stats` counts tiles uploaded / skipped and the upload time, so a real Mac can measure (MINIS_ARENA_PROFILE=1 logs
  them every 5 s; see run_arena).
"""
from __future__ import annotations
import time
from PIL import Image
from Foundation import NSMakeRect

from . import shell
from minis_platform.rects import tile_keys  # noqa: F401  (pure: the tests run it on every OS)

ARENA_CLASS = 'MinisArena'
VK_ESCAPE = 0x1B                                       # macOS Escape (keyCode 53) is mapped to the Windows VK by geometry.MAC_KEYS
TILE = 128


class ArenaWindow:
    def __init__(self, rect, on_hittest=None, on_click=None, on_key=None, title='minis-arena'):
        l, t, r, b = rect
        self.x, self.y, self.w, self.h = int(l), int(t), int(r - l), int(b - t)
        self.scale = 1
        self.on_click = on_click
        self.ov = shell.Overlay(title, self.x, self.y, self.w, self.h, scale=1, on_event=self._mouse,
                                on_hittest=on_hittest or (lambda x, y: False), on_key=on_key, activatable=True)
        self.canvas = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0))
        self.tiles = {}
        self.empty = set()                                 # tiles whose layer currently shows nothing
        self._dirty = []
        self._offset = (0, 0)
        self._tint = None
        self._tint_layer = None
        self.visible = True
        self.stats = dict(frames=0, uploaded=0, skipped=0, upload_s=0.0)

    @property
    def hwnd(self):
        return self.ov.hwnd

    def _mouse(self, kind, x, y):
        if kind == 'down' and self.on_click:
            try:
                self.on_click(x, y)
            except Exception:
                pass

    def write(self, img, x, y):
        x, y = int(x), int(y)
        x0, y0, x1, y1 = max(0, x), max(0, y), min(self.w, x + img.width), min(self.h, y + img.height)
        if x1 <= x0 or y1 <= y0:
            return
        self.canvas.paste(img.crop((x0 - x, y0 - y, x1 - x, y1 - y)) if (x0, y0, x1, y1) != (x, y, x + img.width, y + img.height) else img, (x0, y0))
        self._dirty.append((x0, y0, x1, y1))

    def _tile_layer(self, tx, ty):
        lay = self.tiles.get((tx, ty))
        if lay is None:
            lay = shell.new_layer()
            tw, th = min(TILE, self.w - tx), min(TILE, self.h - ty)
            lay.setFrame_(NSMakeRect(tx, self.h - (ty + th), tw, th))       # layers count y from the bottom
            self.ov.layer.addSublayer_(lay)
            self.tiles[(tx, ty)] = lay
            self.empty.add((tx, ty))
        return lay

    def flush(self, full=False):
        t0 = time.perf_counter()
        rects = [(0, 0, self.w, self.h)] if full else self._dirty
        self._dirty = []
        keys = tile_keys(rects, self.w, self.h, TILE)
        if not keys:
            return True
        imgs = {}
        for k in keys:
            crop = self.canvas.crop((k[0], k[1], min(self.w, k[0] + TILE), min(self.h, k[1] + TILE)))
            if crop.getchannel('A').getbbox() is None:     # nothing to show: no conversion, no upload
                if k in self.empty and k in self.tiles:
                    self.stats['skipped'] += 1
                    continue
                imgs[k] = None
            else:
                imgs[k] = shell.cgimage(crop)

        def apply():
            for k, cg in imgs.items():
                self._tile_layer(*k).setContents_(cg)
                if cg is None:
                    self.empty.add(k)
                else:
                    self.empty.discard(k)
        shell._no_anim(apply)
        self.stats['frames'] += 1
        self.stats['uploaded'] += sum(1 for v in imgs.values() if v is not None)
        self.stats['skipped'] += sum(1 for v in imgs.values() if v is None)
        self.stats['upload_s'] += time.perf_counter() - t0
        return True

    def tint(self, rgb, alpha):
        """A full-window colour wash on the GPU (the compositor's colour / white flash): rgb None clears it."""
        want = None if rgb is None or alpha <= 0 else (tuple(int(c) for c in rgb), round(float(alpha), 2))
        if want == self._tint:
            return
        self._tint = want

        def apply():
            if self._tint_layer is None:
                lay = shell.new_layer()
                lay.setFrame_(NSMakeRect(0, 0, self.w, self.h))
                lay.setZPosition_(10.0)                    # above every tile, whenever the tiles were made
                self.ov.layer.addSublayer_(lay)
                self._tint_layer = lay
            lay = self._tint_layer
            if want is None:
                lay.setHidden_(True)
                return
            (r, g, b), a = want
            import Quartz
            lay.setBackgroundColor_(Quartz.CGColorCreateGenericRGB(r / 255.0, g / 255.0, b / 255.0, 1.0))
            lay.setOpacity_(min(1.0, a))
            lay.setHidden_(False)
        shell._no_anim(apply)

    def offset(self, dx, dy):
        if (int(dx), int(dy)) != self._offset:
            self._offset = (int(dx), int(dy))
            self.ov.move(self.x + self._offset[0], self.y + self._offset[1])

    def reassert_topmost(self):
        self.ov.reassert_topmost()

    def pump(self):
        return self.ov.pump()

    def show(self, visible):
        self.ov.show(visible)
        self.visible = visible

    def close(self):
        self.canvas = None                                 # the overlay's pixels (desktop weapons included) leave RAM
        self.ov.close()
