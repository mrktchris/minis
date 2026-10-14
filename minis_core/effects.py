"""Effect playback: live instances of fx.Effect anchored to a fighter (hand / ground / center + offset), travelling,
layered front or back, and the screen-shake offsets they request.  Pure: positions in, placements out; no window code.

Coordinates are "logical" pixels of whatever rig the caller draws (RES 1 for the taskbar, RES 2 for the arena): the
player scales each effect frame by `res / effect.res`, so a RES 2 sheet draws at half size on the 64 px taskbar.

V5: a growing beam (`Effect.grow`) is drawn as the span `Effect.extent()` returns, cropped from the frame so its anchor
edge stays on the hand while the far end extends, holds and retracts; `beam_end()` says where that far end is (the impact
burst goes there).  `flash()` is the white screen flash (an effect's `flash: true` on its hit frame, or `flash_at()` from a
timeline); `add_shake()` takes a shake a MOVE asks for (anim.json `shake`) beside the ones effects carry.
"""
from __future__ import annotations
import math

HAND_DX, HAND_DY, CENTER_DY = 12, 24, 24          # art/fx.py contract: center = ground - (0, 24*res); hand = ground + anim.hand
FLASH_S = 0.06                                     # one frame at the active rates: the white flash lasts this long
FLASH_ALPHA = 0.6


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
        self.shakes = []                      # standalone shakes from moves: (t0, frames, amp in the player's px)
        self.flashes = []                     # standalone flashes: (t0, alpha, seconds)

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
        if owner is None and tag is None:
            self.shakes, self.flashes = [], []

    def add_shake(self, t0, frames, amp):
        """A shake a move asks for on its hit frame (anim.json `shake`; amp already in this player's px)."""
        if frames and amp:
            self.shakes.append((float(t0), int(frames), float(amp)))

    def flash_at(self, t0, alpha=FLASH_ALPHA, seconds=FLASH_S):
        self.flashes.append((float(t0), float(alpha), float(seconds)))

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
        self.shakes = [s for s in self.shakes if now - s[0] < s[1] / float(self.fps) + 0.5]
        self.flashes = [f for f in self.flashes if now - f[0] < f[2] + 0.5]

    # ---- output
    def placements(self, now, layer=None):
        """-> [(image, left, top, layer, instance)] in the player's logical pixels (centre-anchored frames)."""
        out = []
        for i in self.active:
            if layer is not None and i.effect.layer != layer:
                continue
            idx = i.data['frame'] if isinstance(i.data, dict) and 'frame' in i.data else i.frame(now)[0]
            im = i.effect.image(idx, i.facing, self.res / float(i.effect.res))
            top = int(round(i.y - im.height / 2.0))
            span = self._span(i, im, now)
            if span is None:
                out.append((im, int(round(i.x - im.width / 2.0)), top, i.effect.layer, i))
                continue
            s_px, e_px, alpha = span
            if e_px - s_px < 1:
                continue
            if i.facing >= 0:
                crop = im.crop((s_px, 0, e_px, im.height))
                left = int(round(i.x - im.width / 2.0)) + s_px
            else:
                crop = im.crop((im.width - e_px, 0, im.width - s_px, im.height))
                left = int(round(i.x + im.width / 2.0)) - e_px
            if alpha < 1.0:
                crop = crop.copy()
                crop.putalpha(crop.getchannel('A').point(lambda v, a=alpha: int(v * a)))
            out.append((crop, left, top, i.effect.layer, i))
        return out

    def _span(self, i, im, now):
        """(start_px, end_px, alpha) of a growing beam in the player's px from its anchor edge, else None."""
        ext = i.effect.extent(i.elapsed_ms(now))
        if ext is None:
            return None
        k = self.res / float(i.effect.res)
        s, e, alpha = ext
        return max(0, min(im.width, int(round(s * k)))), max(0, min(im.width, int(round(e * k)))), alpha

    def beam_origin(self, inst):
        """x of a hand-anchored effect's anchor edge (where a beam leaves the hand) in the player's px."""
        w = max(im.width for im, _ in inst.effect.frames) * self.res / float(inst.effect.res)
        return inst.x - inst.facing * w / 2.0

    def beam_end(self, inst, now):
        """x of a growing beam's far end right now (its full far edge for an effect without `grow`)."""
        k = self.res / float(inst.effect.res)
        ext = inst.effect.extent(inst.elapsed_ms(now))
        w = max(im.width for im, _ in inst.effect.frames) * k
        reach = ext[1] * k if ext is not None else w
        return self.beam_origin(inst) + inst.facing * reach

    def flash(self, now):
        """Alpha (0..1) of the white screen flash this instant: effects flagged `flash` on their hit frame, or flash_at()."""
        best = 0.0
        for i in self.active:
            if i.effect.flash:
                el = now - i.t0 - i.effect.hit_ms() / 1000.0
                if 0 <= el < FLASH_S:
                    best = max(best, FLASH_ALPHA)
        for t0, alpha, secs in self.flashes:
            if 0 <= now - t0 < secs:
                best = max(best, alpha)
        return best

    def shake(self, now):
        """(dx, dy) in logical px: the strongest active shake, decaying over its frame count at `fps`."""
        best = (0, 0)
        mag = 0.0
        cands = []
        for i in self.active:
            sh = i.effect.shake
            if not sh:
                continue
            cands.append((i.t0 + i.effect.hit_ms() / 1000.0, sh['frames'], sh['amp'] * self.res / float(i.effect.res)))
        cands.extend(self.shakes)
        for t0, frames, amp0 in cands:
            el = now - t0
            n = frames / float(self.fps)
            if el < 0 or el >= n or n <= 0:
                continue
            k = 1.0 - el / n
            amp = amp0 * k
            if amp > mag:
                mag = amp
                f = int(el * self.fps)
                best = (int(round(amp * (1 if f % 2 == 0 else -1))), int(round(amp * 0.5 * math.sin(f * 2.1))))
        return best

    def hit_frame_time(self, name):
        """Seconds from spawn to the effect's hit_frame (0 when it has none): when its impact should land."""
        return self.fx.get(name).hit_ms() / 1000.0

    def reach(self, name):
        """How far (player px, from the hand) the effect `name` reaches: a growing beam's `to_w`, a wide hand-anchored
        frame's far edge, else 0 (a burst on the spot).  Callers position a beam ultimate so the defender stands inside."""
        e = self.fx.get(name)
        k = self.res / float(e.res)
        w = max(im.width for im, _ in e.frames)
        h = max(im.height for im, _ in e.frames)
        if e.grow:
            return e.grow['to_w'] * k
        if e.anchor == 'hand' and w >= 3 * h:
            return (e.offset[0] + w / 2.0) * k
        return 0.0
