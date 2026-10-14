"""Effect playback: live instances of fx.Effect anchored to a fighter (hand / ground / center + offset), travelling,
layered front or back, and the screen-shake offsets they request.  Pure: positions in, placements out; no window code.

Coordinates are "logical" pixels of whatever rig the caller draws (RES 1 for the taskbar, RES 2 for the arena): the
player scales each effect frame by `res / effect.res`, so a RES 2 sheet draws at half size on the 64 px taskbar.
"""
from __future__ import annotations
import math

HAND_DX, HAND_DY, CENTER_DY = 12, 24, 24          # art/fx.py contract: center = ground - (0, 24*res); hand = ground + anim.hand


def anchor_point(anchor, hip_x, ground_y, facing, res=1):
    """Where an effect anchors on a fighter standing with its hip at hip_x and its soles at ground_y."""
    if anchor == 'hand':
        return hip_x + facing * HAND_DX * res, ground_y - HAND_DY * res
    if anchor == 'ground':
        return hip_x, ground_y
    return hip_x, ground_y - CENTER_DY * res


class Instance:
    __slots__ = ('effect', 't0', 'x', 'y', 'facing', 'owner', 'tag', 'vx', 'vy', 'gravity', 'fade_ms', 'alive', 'data')

    def __init__(self, effect, t0, x, y, facing, owner=None, tag=None, vx=0.0, vy=0.0, gravity=0.0, fade_ms=None):
        self.effect, self.t0, self.x, self.y, self.facing, self.owner, self.tag = effect, t0, float(x), float(y), facing, owner, tag
        self.vx, self.vy, self.gravity, self.fade_ms = float(vx), float(vy), float(gravity), fade_ms
        self.alive = True
        self.data = None

    def elapsed_ms(self, now):
        return max(0.0, (now - self.t0) * 1000.0)

    def frame(self, now):
        return self.effect.locate(self.elapsed_ms(now))


class EffectPlayer:
    """Holds the active effects of one drawing surface (a fighter window, or the arena)."""

    def __init__(self, fx, res=1, fps=30, max_active=64):
        self.fx, self.res, self.fps, self.max_active = fx, int(res), fps, max_active
        self.active = []
        self._last = None
        self.spawned = 0

    # ---- spawning
    def spawn(self, name, now, hip_x, ground_y, facing=1, owner=None, tag=None, anchor=None, offset=None, hand=None, **kw):
        """Place effect `name` on a fighter (anchor from the effect unless overridden; `hand` = (dx, dy) of the striking
        hand from the hip / ground point in the player's pixels, from the atlas, used for hand-anchored effects)."""
        e = self.fx.get(name)
        k = self.res / float(e.res)
        a = anchor or e.anchor
        if a == 'hand' and hand is not None:
            ax, ay = hip_x + facing * float(hand[0]), ground_y + float(hand[1])
        else:
            ax, ay = anchor_point(a, hip_x, ground_y, facing, self.res)
        ox, oy = e.offset if offset is None else offset
        x = ax + facing * ox * k
        y = ay + oy * k
        return self.spawn_at(name, now, x, y, facing, owner, tag, **kw)

    def spawn_at(self, name, now, x, y, facing=1, owner=None, tag=None, **kw):
        """Place effect `name` with its centre at (x, y)."""
        e = self.fx.get(name)
        inst = Instance(e, now, x, y, facing, owner, tag, **kw)
        if e.travel:
            inst.vx = inst.vx or facing * e.travel['speed'] * (self.res / float(e.res))
        if len(self.active) >= self.max_active:
            self.active.pop(0)
        self.active.append(inst)
        self.spawned += 1
        return inst

    def clear(self, owner=None, tag=None):
        self.active = [i for i in self.active if not ((owner is None or i.owner == owner) and (tag is None or i.tag == tag))]

    def stop(self, inst):
        inst.alive = False

    # ---- time
    def tick(self, now):
        dt = 0.0 if self._last is None else max(0.0, min(0.25, now - self._last))
        self._last = now
        keep = []
        for i in self.active:
            if not i.alive:
                continue
            fixed = isinstance(i.data, dict) and 'frame' in i.data      # a shard / glyph: one frame, lives until fade_ms
            idx, done = i.frame(now)
            if done and not i.effect.loop and not fixed:
                continue
            if i.fade_ms is not None and i.elapsed_ms(now) > i.fade_ms:
                continue
            if fixed and i.fade_ms is None and i.elapsed_ms(now) > 4000:
                continue
            if dt:
                i.vy += i.gravity * dt
                i.x += i.vx * dt
                i.y += i.vy * dt
            keep.append(i)
        self.active = keep

    # ---- output
    def placements(self, now, layer=None):
        """-> [(image, left, top, layer, instance)] in the player's logical pixels (centre-anchored frames)."""
        out = []
        for i in self.active:
            if layer is not None and i.effect.layer != layer:
                continue
            idx = i.data['frame'] if isinstance(i.data, dict) and 'frame' in i.data else i.frame(now)[0]
            im = i.effect.image(idx, i.facing, self.res / float(i.effect.res))
            out.append((im, int(round(i.x - im.width / 2.0)), int(round(i.y - im.height / 2.0)), i.effect.layer, i))
        return out

    def shake(self, now):
        """(dx, dy) in logical px: the strongest active shake, decaying over its frame count at `fps`."""
        best = (0, 0)
        mag = 0.0
        for i in self.active:
            sh = i.effect.shake
            if not sh:
                continue
            el = now - i.t0
            if i.effect.hit_frame is not None:
                el -= sum(ms for _, ms in i.effect.frames[:i.effect.hit_frame]) / 1000.0
            n = sh['frames'] / float(self.fps)
            if el < 0 or el >= n:
                continue
            k = 1.0 - el / n
            amp = sh['amp'] * k * self.res / float(i.effect.res)
            if amp > mag:
                mag = amp
                f = int(el * self.fps)
                best = (int(round(amp * (1 if f % 2 == 0 else -1))), int(round(amp * 0.5 * math.sin(f * 2.1))))
        return best

    def hit_frame_time(self, name):
        """Seconds from spawn to the effect's hit_frame (0 when it has none): when its impact should land."""
        e = self.fx.get(name)
        if e.hit_frame is None:
            return 0.0
        return sum(ms for _, ms in e.frames[:e.hit_frame]) / 1000.0
