"""Headless simulator: two Brains + scripted fake telemetry on a fake clock.  No windows, no files.
Used by the tests and to render the preview GIFs (the same logic the real windows run)."""
from __future__ import annotations
import random
from PIL import Image, ImageDraw

from . import config as cfgmod, render
from .atlas import Library
from .brain import Brain, LEFT, RIGHT

DEFAULT_CHARS = {LEFT: 'claude', RIGHT: 'codex'}
from .telemetry import Snapshot


class FakeTelemetry:
    """segments: [(t_start, state, ctx_pct)]; emits 'finished' when working ends, 'limit' when ctx crosses the limit."""

    def __init__(self, who, segments, plan=None, limit=90, done_show=8.0, t0=1000.0):
        self.who, self.segments, self.plan, self.limit, self.done_show, self.t0 = who, segments, plan, limit, done_show, t0
        self.prev = None
        self.work_start = None
        self.done_until = 0
        self.limit_seen = False

    def poll(self, now):
        cur = self.segments[0]
        for seg in self.segments:
            if seg[0] <= now - self.t0:
                cur = seg
        state, ctx = cur[1], cur[2]
        snap = Snapshot(self.who, state, ctx, self.plan[0] if self.plan else None, self.plan[1] if self.plan else '')
        if state == 'working' and self.work_start is None:
            self.work_start = now
        if self.prev == 'working' and state == 'idle':
            if self.work_start is not None and now - self.work_start >= 15:
                snap.events.append('finished')
                self.done_until = now + self.done_show
            self.work_start = None
        self.prev = state
        if ctx is not None and ctx >= self.limit:
            if not self.limit_seen:
                snap.events.append('limit')
            self.limit_seen = True
            snap.state = 'limit'
        else:
            self.limit_seen = False
            if state == 'idle' and now < self.done_until:
                snap.state = 'done'
        return snap


_LIB = Library()


def make(seed=1, cfg=None, t0=1000.0, tele=None, chars=None):
    """-> (cfg, {slot: Atlas}, {slot: Brain}).  Slots a/b wear `chars` (default claude / codex)."""
    cfg = dict(cfgmod.DEFAULTS if cfg is None else cfg)
    chars = dict(DEFAULT_CHARS, **(chars or {}))
    atl = {w: _LIB[chars[w]] for w in (LEFT, RIGHT)}
    brains = {w: Brain(w, atl[w], _LIB, cfg, random.Random(seed + (1 if w == RIGHT else 0)), t0, run=f'sim{w}', record=no_record) for w in (LEFT, RIGHT)}
    for b in brains.values():
        b.flashes = True                                         # the simulator never reads this machine's control.json
    return cfg, atl, brains


def no_record(*a, **k):
    """The simulator never writes the real record.json under %LOCALAPPDATA% (a preview match is not a real result)."""
    no_record.calls.append(a)
    return True


no_record.calls = []


def step(brains, tele, now, bus):
    for w, b in brains.items():
        snap = tele[w].poll(now)
        partner = bus.get(RIGHT if w == LEFT else LEFT)
        b.tick(now, snap, partner)
    for w, b in brains.items():
        bus[w] = b.publish()


def run(seconds, tele, seed=1, cfg_over=None, fps=10, t0=1000.0, place=None, collect=False, scale=3, crop=None, label='DEMO DATA', chars=None):
    cfg = dict(cfgmod.DEFAULTS)
    cfg.update(cfg_over or {})
    cfg, atl, brains = make(seed, cfg, t0, chars=chars)
    if place:
        for w, x in place.items():
            brains[w].x = brains[w].home_x = x
            brains[w].home = (x - 40, x + 40)
    bus = {}
    frames, times, flags = [], [], []
    z0, z1 = cfg['zone']
    zone_w = int(z1 - z0 + 70)
    n = int(seconds * fps)
    for i in range(n + 1):
        now = t0 + i / fps
        step(brains, tele, now, bus)
        if collect:
            im = Image.new('RGBA', (zone_w, 64), (0, 0, 0, 0))
            for w in (LEFT, RIGHT):
                v = brains[w].view(now)
                snap = brains[w].snap
                im.alpha_composite(render.compose_full(atl[w], atl[w], v, snap, now, zone_w, cfg, win_x=0))
            frames.append(mock_taskbar(im, crop, scale, label))
            times.append(i / fps)
            flags.append(dict(script=any(brains[w].script is not None for w in (LEFT, RIGHT)), mode={w: brains[w].mode for w in (LEFT, RIGHT)},
                              x={w: brains[w].x for w in (LEFT, RIGHT)}, anim={w: brains[w].anim for w in (LEFT, RIGHT)}))
    run.flags = flags
    return brains, frames, times


def mock_taskbar(sprites, crop, scale, label=''):
    """Sprites over a Windows-11-dark taskbar mock (bottom 48 rows) with a dark window edge above it."""
    w, h = sprites.size
    bg = Image.new('RGBA', (w, h), (24, 24, 30, 255))
    d = ImageDraw.Draw(bg)
    d.rectangle([0, 16, w, h], fill=(32, 32, 32, 255))
    d.line([(0, 16), (w, 16)], fill=(58, 58, 62, 255))
    bg.alpha_composite(sprites)
    if label:
        render.text(d, (4, 2), label, (120, 120, 135), 9, False)
        bg2 = bg
    if crop:
        bg = bg.crop((crop[0], 0, crop[1], h))
    if scale != 1:
        bg = bg.resize((bg.width * scale, bg.height * scale), Image.NEAREST)
    return bg.convert('RGB')


def save_gif(frames, times, path, fps=10, colors=48, hold_last=0.8):
    if not frames:
        return
    pal = frames[len(frames) // 2].quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    dur = [int(1000 / fps)] * len(q)
    dur[-1] = int(hold_last * 1000)
    q[0].save(path, save_all=True, append_images=q[1:], duration=dur, loop=0, optimize=False, disposal=1)
