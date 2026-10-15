"""The arena overlay on macOS: one panel the size of the monitor, click-through except the EXIT button.

The same surface minis_core.arena.Compositor drives on Windows: write(img, x, y) replaces a rectangle, flush() shows the
changed parts, offset(dx, dy) shakes this window (never any other).  The picture is kept in a PIL canvas and shown as a grid
of 256-point tile layers; a flush re-uploads only the tiles a dirty rectangle touches.  EXPERIMENTAL: untested on a Mac.
"""
from __future__ import annotations
from PIL import Image
from Foundation import NSMakeRect

from . import shell

ARENA_CLASS = 'MinisArena'
VK_ESCAPE = 0x1B                                       # macOS Escape (keyCode 53) is mapped to the Windows VK by geometry.MAC_KEYS
TILE = 256


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
        self._dirty = []
        self._offset = (0, 0)
        self.visible = True

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
        self.canvas.paste(img.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))
        self._dirty.append((x0, y0, x1, y1))

    def _tile_layer(self, tx, ty):
        lay = self.tiles.get((tx, ty))
        if lay is None:
            lay = shell.new_layer()
            tw, th = min(TILE, self.w - tx), min(TILE, self.h - ty)
            lay.setFrame_(NSMakeRect(tx, self.h - (ty + th), tw, th))       # layers count y from the bottom
            self.ov.layer.addSublayer_(lay)
            self.tiles[(tx, ty)] = lay
        return lay

    def flush(self, full=False):
        rects = [(0, 0, self.w, self.h)] if full else self._dirty
        self._dirty = []
        keys = set()
        for x0, y0, x1, y1 in rects:
            for ty in range((y0 // TILE) * TILE, y1, TILE):
                for tx in range((x0 // TILE) * TILE, x1, TILE):
                    keys.add((tx, ty))
        if not keys:
            return True
        imgs = {k: shell.cgimage(self.canvas.crop((k[0], k[1], min(self.w, k[0] + TILE), min(self.h, k[1] + TILE)))) for k in keys}

        def apply():
            for k, cg in imgs.items():
                self._tile_layer(*k).setContents_(cg)
        shell._no_anim(apply)
        return True

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
        self.ov.close()
