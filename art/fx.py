"""Effects sheets: every effect is rendered from code at the current rig RES into <out>/fx.png + fx.json.

fx.json (docs/V4-WORKORDER.md "Shared interfaces", exact per-effect keys):
  {"res": k, "sheet": "fx.png",
   "effects": {"<name>": {"frames": [{"x","y","w","h","ms"}], "anchor": "hand|ground|center", "offset": [dx, dy],
                          "loop": bool, "layer": "front|back", "hit_frame": n|null,
                          "travel": {"speed": px_per_s}|null, "shake": {"frames": n, "amp": px}|null}}}

Placement contract (ART -> ENGINE): a frame is drawn CENTRED on the anchor point plus `offset` (px at this res;
negate dx and flip the frame for a left-facing owner).  Anchor points, in the owner's cell:
  ground = (anchor_x, ground_y)                      the planted-foot column and row from anim.json
  center = (anchor_x, ground_y - 24 * res)           mid-torso
  hand   = ground + anim.json[<move>]["hand"]        the front hand at that move's proj_frame (px, relative to ground)
`travel.speed` is px/s at this res, in the owner's facing.  Shake `amp` is px at this res.

Every sheet carries the colour-neutral GENERIC set (identical art in every character folder, so the engine's
name-merge across characters is harmless), the character's upgraded special/super effects, and its ultimate.
`shatter` and `letters` are particle sets: each frame is one shard / one glyph (26 small, then 26 big), not a sequence.
`round_text` frames are ROUND 1, ROUND 2, ROUND 3, FIGHT!, WINNER in that order; the same rects are also exposed as
`round_1`, `round_2`, `round_3`, `fight`, `winner`, and `ko_text` frame 2 as `ko` (the engine's named lookups).
"""
from __future__ import annotations
import json, math, os, random
from PIL import Image, ImageDraw

import rig
from rig import hexrgb

# ---------------------------------------------------------------- universal effect colours (every character)
W_ = hexrgb('FFFFFF')
Y_ = hexrgb('FFE27A')
O_ = hexrgb('FF9C2C')
R_ = hexrgb('E03A3A')
EMB = hexrgb('7A1E1E')
INK = hexrgb('1A1A22')
G1, G2, G3 = hexrgb('D8D4CC'), hexrgb('9A948C'), hexrgb('5A5660')
GL1, GL2, GL3, GL4 = hexrgb('E8F6FF'), hexrgb('8FCBF0'), hexrgb('3C78B8'), hexrgb('1E3C64')
SMK = hexrgb('3A3A42')
CENTER_DY = 24                       # design px above ground: the `center` anchor

FONT = {
    'A': ['.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'B': ['####.', '#...#', '#...#', '####.', '#...#', '#...#', '####.'],
    'C': ['.####', '#....', '#....', '#....', '#....', '#....', '.####'],
    'D': ['####.', '#...#', '#...#', '#...#', '#...#', '#...#', '####.'],
    'E': ['#####', '#....', '#....', '####.', '#....', '#....', '#####'],
    'F': ['#####', '#....', '#....', '####.', '#....', '#....', '#....'],
    'G': ['.####', '#....', '#....', '#..##', '#...#', '#...#', '.####'],
    'H': ['#...#', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'I': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '#####'],
    'J': ['..###', '...#.', '...#.', '...#.', '...#.', '#..#.', '.##..'],
    'K': ['#...#', '#..#.', '#.#..', '##...', '#.#..', '#..#.', '#...#'],
    'L': ['#....', '#....', '#....', '#....', '#....', '#....', '#####'],
    'M': ['#...#', '##.##', '#.#.#', '#.#.#', '#...#', '#...#', '#...#'],
    'N': ['#...#', '##..#', '#.#.#', '#..##', '#...#', '#...#', '#...#'],
    'O': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'P': ['####.', '#...#', '#...#', '####.', '#....', '#....', '#....'],
    'Q': ['.###.', '#...#', '#...#', '#...#', '#.#.#', '#..#.', '.##.#'],
    'R': ['####.', '#...#', '#...#', '####.', '#.#..', '#..#.', '#...#'],
    'S': ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
    'T': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
    'U': ['#...#', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'V': ['#...#', '#...#', '#...#', '#...#', '#...#', '.#.#.', '..#..'],
    'W': ['#...#', '#...#', '#...#', '#.#.#', '#.#.#', '##.##', '#...#'],
    'X': ['#...#', '#...#', '.#.#.', '..#..', '.#.#.', '#...#', '#...#'],
    'Y': ['#...#', '#...#', '.#.#.', '..#..', '..#..', '..#..', '..#..'],
    'Z': ['#####', '....#', '...#.', '..#..', '.#...', '#....', '#####'],
    '1': ['..#..', '.##..', '..#..', '..#..', '..#..', '..#..', '.###.'],
    '2': ['.###.', '#...#', '....#', '...#.', '..#..', '.#...', '#####'],
    '3': ['####.', '....#', '....#', '.###.', '....#', '....#', '####.'],
    '!': ['..#..', '..#..', '..#..', '..#..', '..#..', '.....', '..#..'],
    '.': ['.....', '.....', '.....', '.....', '.....', '.##..', '.##..'],
    ' ': ['.....', '.....', '.....', '.....', '.....', '.....', '.....'],
}
LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def dark(c, k=0.5):
    return tuple(int(v * k) for v in c)


class Canvas:
    """A frame in DESIGN units; every call scales by rig.RES so HD gets real curves, not blown-up blocks."""

    def __init__(self, w, h):
        self.S = rig.RES
        self.w, self.h = w, h
        self.im = Image.new('RGBA', (w * self.S, h * self.S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def _c(self, c):
        return tuple(c) + (255,)

    def px(self, x, y, c):
        S = self.S
        x, y = rig.rnd(x * S), rig.rnd(y * S)
        self.d.rectangle([x, y, x + S - 1, y + S - 1], fill=self._c(c))

    def rect(self, x0, y0, x1, y1, c):
        S = self.S
        self.d.rectangle([rig.rnd(x0 * S), rig.rnd(y0 * S), rig.rnd(x1 * S) + S - 1, rig.rnd(y1 * S) + S - 1], fill=self._c(c))

    def disc(self, cx, cy, r, c):
        S = self.S
        if r <= 0:
            return
        self.d.ellipse([rig.rnd((cx - r) * S), rig.rnd((cy - r) * S), rig.rnd((cx + r) * S) - 1, rig.rnd((cy + r) * S) - 1], fill=self._c(c))

    def ring(self, cx, cy, r, t, c):
        S = self.S
        if r <= 0:
            return
        self.d.ellipse([rig.rnd((cx - r) * S), rig.rnd((cy - r) * S), rig.rnd((cx + r) * S) - 1, rig.rnd((cy + r) * S) - 1],
                       outline=self._c(c), width=max(1, rig.rnd(t * S)))

    def line(self, p0, p1, c, t=1):
        S = self.S
        self.d.line([(p0[0] * S, p0[1] * S), (p1[0] * S, p1[1] * S)], fill=self._c(c), width=max(1, rig.rnd(t * S)))

    def poly(self, pts, c):
        S = self.S
        self.d.polygon([(rig.rnd(x * S), rig.rnd(y * S)) for x, y in pts], fill=self._c(c))

    def spike(self, cx, cy, ang, length, wid, c, inner=0.0):
        """A diamond / needle from (cx, cy) outward at `ang` degrees."""
        a = math.radians(ang)
        ux, uy = math.cos(a), math.sin(a)
        vx, vy = -uy, ux
        self.poly([(cx + ux * inner, cy + uy * inner), (cx + ux * length * 0.35 + vx * wid, cy + uy * length * 0.35 + vy * wid),
                   (cx + ux * length, cy + uy * length), (cx + ux * length * 0.35 - vx * wid, cy + uy * length * 0.35 - vy * wid)], c)

    def arc_band(self, cx, cy, r0, r1, a0, a1, c, steps=24):
        """A filled band between two radii over an angle span (degrees)."""
        pts = []
        for k in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * k / steps)
            pts.append((cx + r1 * math.cos(a), cy + r1 * math.sin(a)))
        for k in range(steps, -1, -1):
            a = math.radians(a0 + (a1 - a0) * k / steps)
            pts.append((cx + r0 * math.cos(a), cy + r0 * math.sin(a)))
        self.poly(pts, c)

    def text(self, x, y, s, c, scale=1, outline=None):
        """5x7 pixel font at `scale` design px per font pixel, optional 1-px outline colour."""
        gw = 5 * scale + scale
        if outline is not None:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        self._text_raw(x + dx, y + dy, s, outline, scale, gw)
        self._text_raw(x, y, s, c, scale, gw)

    def _text_raw(self, x, y, s, c, scale, gw):
        cx = x
        for ch in s:
            g = FONT.get(ch, FONT[' '])
            if ch == ' ':
                cx += 3 * scale
                continue
            for yy, row in enumerate(g):
                for xx, on in enumerate(row):
                    if on == '#':
                        self.rect(cx + xx * scale, y + yy * scale, cx + xx * scale + scale - 1, y + yy * scale + scale - 1, c)
            cx += gw

    def dither(self, keep=0):
        """Checkerboard in DESIGN cells: clear every pixel whose design cell parity != keep."""
        S = self.S
        px = self.im.load()
        for y in range(self.im.height):
            for x in range(self.im.width):
                if px[x, y][3] and (x // S + y // S) % 2 != keep:
                    px[x, y] = (0, 0, 0, 0)
        return self

    def done(self):
        return self.im


def text_size(s, scale):
    n_sp = s.count(' ')
    return (len(s) - n_sp) * (6 * scale) - scale + n_sp * 3 * scale, 7 * scale


# ---------------------------------------------------------------- generic effects (universal colours)
def fx_hit_light():
    out = []
    for k in range(4):
        c = Canvas(16, 16)
        cx = cy = 8
        if k == 0:
            c.disc(cx, cy, 2.5, W_)
            for a in (0, 90, 180, 270):
                c.spike(cx, cy, a, 4, 1, Y_)
        elif k == 1:
            for a in range(0, 360, 45):
                c.spike(cx, cy, a, 7 if a % 90 == 0 else 5, 1.2, O_ if a % 90 else Y_)
            c.disc(cx, cy, 3, W_)
        elif k == 2:
            c.ring(cx, cy, 6, 1.2, Y_)
            for a in range(0, 360, 90):
                c.spike(cx, cy, a + 45, 7.5, 0.8, O_, inner=4)
            c.disc(cx, cy, 1.5, W_)
        else:
            for a in range(0, 360, 60):
                r = 7
                c.px(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)), O_)
        out.append((c.done(), (50, 50, 60, 60)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0), hit_frame=1)


def fx_hit_heavy():
    out = []
    for k in range(5):
        c = Canvas(32, 32)
        cx = cy = 16
        if k == 0:
            c.disc(cx, cy, 6, W_)
            c.ring(cx, cy, 6, 1.5, Y_)
        elif k == 1:
            for a in range(0, 360, 45):
                c.spike(cx, cy, a + 22, 14 if a % 90 == 0 else 11, 2.2, O_)
            for a in range(0, 360, 90):
                c.spike(cx, cy, a + 22, 14, 1.2, Y_)
            c.disc(cx, cy, 7, Y_)
            c.disc(cx, cy, 4.5, W_)
        elif k == 2:
            c.ring(cx, cy, 11, 2.5, O_)
            c.ring(cx, cy, 10, 1.2, Y_)
            for a in range(0, 360, 45):
                c.spike(cx, cy, a + 22, 15.5, 1.4, Y_ if a % 90 == 0 else O_, inner=9)
                c.px(cx + 15 * math.cos(math.radians(a + 22)), cy + 15 * math.sin(math.radians(a + 22)), W_)
            c.disc(cx, cy, 3, W_)
        elif k == 3:
            for a in range(0, 360, 30):
                if a % 60 == 0:
                    c.arc_band(cx, cy, 11, 13.5, a - 10, a + 10, O_)
            for a in range(0, 360, 45):
                c.spike(cx, cy, a + 22, 15.5, 0.9, EMB, inner=12)
        else:
            for a in range(0, 360, 40):
                r = 14 + (a // 40) % 2
                c.px(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)), O_ if a % 80 else EMB)
        out.append((c.done(), (40, 60, 60, 70, 70)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0), hit_frame=1, shake=dict(frames=3, amp=2))


def fx_block_spark():
    out = []
    for k in range(4):
        c = Canvas(20, 20)
        cx, cy = 10, 10
        if k < 3:
            c.arc_band(cx - 2, cy, 6 + k, 7.5 + k, -60, 60, GL2)
            c.arc_band(cx - 2, cy, 6.3 + k, 7.0 + k, -40, 40, GL1)
        for j, a in enumerate((-50, -20, 15, 45)):
            L = 4 + k * 2 + (j % 2)
            if k < 3:
                c.spike(cx + 2, cy, a, L, 0.7, GL1 if j % 2 else W_, inner=2 + k)
            else:
                c.px(cx + 2 + L * math.cos(math.radians(a)), cy + L * math.sin(math.radians(a)), GL2)
        if k == 1:
            c.disc(cx + 2, cy, 2, W_)
        out.append((c.done(), (40, 60, 60, 60)[k]))
    return dict(frames=out, anchor='hand', offset=(0, 0), hit_frame=1)


def fx_dust():
    out = []
    for k in range(4):
        c = Canvas(28, 14)
        spread = 1 + k * 0.5
        for j, (x, r) in enumerate(((9, 3.2), (14, 4), (19, 3.2), (6, 2.2), (22, 2.2))):
            rr = r * (1.2 - k * 0.22)
            xx = 14 + (x - 14) * spread
            yy = 11 - k * 1.2 - rr
            if rr > 0.6:
                c.disc(xx, yy, rr, G2 if j < 3 else G3)
                c.disc(xx - rr * 0.3, yy - rr * 0.3, rr * 0.6, G1)
        if k == 3:
            for x in (4, 10, 17, 24):
                c.px(x, 6 - (x % 3), G2)
        out.append((c.done(), (60, 70, 80, 90)[k]))
    return dict(frames=out, anchor='ground', offset=(0, -7), layer='back')


def fx_ko_stars():
    out = []
    for k in range(4):
        c = Canvas(28, 12)
        for j in range(3):
            a = k * 0.8 + j * 2.094
            x, y = 14 + math.cos(a) * 11, 6 + math.sin(a) * 3
            front = math.sin(a) > 0
            col = Y_ if front else O_
            c.px(x, y, W_ if front else Y_)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                c.px(x + dx, y + dy, col)
            if front:
                for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                    c.px(x + dx, y + dy, col)
        out.append((c.done(), 130))
    return dict(frames=out, anchor='center', offset=(0, -22), loop=True)


def _cracks(c, cx, cy, n, segs, length, seed, light=True):
    rng = random.Random(seed)
    for j in range(n):
        a = rng.uniform(0, 2 * math.pi)
        x, y = cx, cy
        for s in range(segs):
            L = length * rng.uniform(0.6, 1.2) * (1.0 - s * 0.12)
            a += rng.uniform(-0.6, 0.6)
            nx, ny = x + L * math.cos(a), y + L * math.sin(a)
            if light:
                c.line((x + 0.6, y + 0.6), (nx + 0.6, ny + 0.6), GL1, 1)
            c.line((x, y), (nx, ny), INK, 1.4 if s == 0 else 1)
            if s < segs - 1 and rng.random() < 0.5:
                b = a + rng.choice((-1, 1)) * rng.uniform(0.6, 1.2)
                bl = L * 0.6
                c.line((nx, ny), (nx + bl * math.cos(b), ny + bl * math.sin(b)), INK, 1)
            x, y = nx, ny


def fx_crack_small():
    out = []
    for k in range(2):
        c = Canvas(28, 28)
        _cracks(c, 14, 14, 5, 2 + k, 4.5, seed=7)
        c.disc(14, 14, 1.5, GL1)
        c.disc(14, 14, 0.8, INK)
        out.append((c.done(), (60, 2000)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0), layer='back')


def fx_crack_big():
    out = []
    for k in range(3):
        c = Canvas(56, 56)
        _cracks(c, 28, 28, 8, 2 + k, 7, seed=11)
        c.ring(28, 28, 3 + k, 1, GL1)
        c.disc(28, 28, 2, INK)
        out.append((c.done(), (60, 60, 2000)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0), layer='back', shake=dict(frames=3, amp=2))


def fx_shatter():
    rng = random.Random(3)
    out = []
    for k in range(12):
        c = Canvas(12, 12)
        n = 3 + (k % 2)
        pts = []
        for j in range(n):
            a = 2 * math.pi * j / n + rng.uniform(-0.4, 0.4)
            r = rng.uniform(3, 5.5)
            pts.append((6 + r * math.cos(a), 6 + r * math.sin(a)))
        c.poly(pts, GL3 if k % 3 else GL4)
        inner = [(6 + (x - 6) * 0.65, 6 + (y - 6) * 0.65) for x, y in pts]
        c.poly(inner, GL2 if k % 3 else GL3)
        c.line(pts[0], pts[1], GL1, 1)
        c.px(inner[0][0], inner[0][1], W_)
        out.append((c.done(), 1000))
    return dict(frames=out, anchor='center', offset=(0, 0))


def _explosion(size, cols, n=7):
    """cols = (core, hot, warm, ember, smoke)."""
    core, hot, warm, emb, smk = cols
    out = []
    cx = cy = size / 2
    R = size / 2 - 2
    rng = random.Random(5)
    lumps = [(rng.uniform(0, 2 * math.pi), rng.uniform(0.5, 0.9)) for _ in range(7)]
    for k in range(n):
        c = Canvas(size, size)
        t = k / (n - 1)
        if k == 0:
            c.disc(cx, cy, R * 0.25, core)
            for a in range(0, 360, 45):
                c.spike(cx, cy, a, R * 0.55, 1.2, hot)
        elif k <= 3:
            r = R * (0.45 + 0.55 * (k / 3))
            c.disc(cx, cy, r, emb)
            for a, f in lumps:
                c.disc(cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55, r * 0.42 * f, emb)
            c.disc(cx, cy, r * 0.82, warm)
            for a, f in lumps[:5]:
                c.disc(cx + math.cos(a) * r * 0.45, cy + math.sin(a) * r * 0.45, r * 0.36 * f, warm)
            c.disc(cx, cy, r * 0.58, hot)
            c.disc(cx - r * 0.1, cy - r * 0.12, r * (0.36 - k * 0.05), core)
            for a in range(0, 360, 30):
                if (a // 30 + k) % 3 == 0:
                    c.spike(cx, cy, a, r * 1.25, 1.0, hot, inner=r * 0.8)
        else:                                                         # the fireball collapses into rolling smoke
            r = R * (0.95, 0.9, 0.8)[k - 4]
            puff = (0.42, 0.36, 0.26)[k - 4]
            if k == 4:
                c.disc(cx, cy, r * 0.8, emb)
                c.ring(cx, cy, r * 0.6, 2, warm)
                c.disc(cx, cy, r * 0.25, hot)
            for j, (a, f) in enumerate(lumps + lumps[:4]):
                rr = r * (0.85 if j < 7 else 0.5)
                ang = a + (k - 4) * 0.25 + (0.9 if j >= 7 else 0)
                x, y = cx + math.cos(ang) * rr, cy + math.sin(ang) * rr - (k - 4) * 2
                c.disc(x, y, r * puff * f, smk if j % 2 else dark(smk, 0.7))
                c.disc(x - r * puff * f * 0.3, y - r * puff * f * 0.3, r * puff * f * 0.5, G3 if k < 6 else smk)
                if k == 4 and j < 7:
                    c.disc(x, y + r * puff * f * 0.4, r * puff * f * 0.35, emb)
            for a in range(0, 360, 36):
                if (a // 36 + k) % 2:
                    c.px(cx + (r + 2) * math.cos(math.radians(a + k * 9)), cy + (r + 2) * math.sin(math.radians(a + k * 9)) - (k - 4) * 2, hot if k == 4 else emb)
        out.append((c.done(), (40, 50, 60, 70, 80, 90, 110)[k]))
    return out


def fx_explosion():
    return dict(frames=_explosion(48, (W_, Y_, O_, EMB, SMK)), anchor='center', offset=(0, 0), hit_frame=1, shake=dict(frames=6, amp=4))


def fx_letters():
    out = []
    for scale in (1, 2):
        for ch in LETTERS:
            w, h = text_size(ch, scale)
            c = Canvas(w + 2, h + 2)
            c.text(1, 1, ch, W_, scale, outline=INK)
            out.append((c.done(), 1000))
    return dict(frames=out, anchor='center', offset=(0, 0))


def _banner(s, fill, scale=2, outline=INK, shadow=None):
    w, h = text_size(s, scale)
    c = Canvas(w + 4, h + 4)
    if shadow is not None:
        c.text(3, 3, s, shadow, scale)
    c.text(1, 1, s, fill, scale, outline=outline)
    return c.done()


def fx_ko_text():
    return dict(frames=[(_banner('K.O.', W_, 3, INK), 80), (_banner('K.O.', Y_, 3, EMB, dark(EMB)), 80), (_banner('K.O.', R_, 3, INK, EMB), 1500)],
                anchor='center', offset=(0, -34), shake=dict(frames=4, amp=3))


def fx_round_text():
    return dict(frames=[(_banner(s, Y_ if s != 'FIGHT!' else R_, 2, INK, EMB if s == 'FIGHT!' else G3), 1200)
                        for s in ('ROUND 1', 'ROUND 2', 'ROUND 3', 'FIGHT!', 'WINNER')], anchor='center', offset=(0, -34))


GENERIC = dict(hit_light=fx_hit_light, hit_heavy=fx_hit_heavy, block_spark=fx_block_spark, dust=fx_dust, ko_stars=fx_ko_stars,
               crack_small=fx_crack_small, crack_big=fx_crack_big, shatter=fx_shatter, explosion=fx_explosion,
               letters=fx_letters, ko_text=fx_ko_text, round_text=fx_round_text)
ALIASES = {'round_1': ('round_text', 0), 'round_2': ('round_text', 1), 'round_3': ('round_text', 2),
           'fight': ('round_text', 3), 'winner': ('round_text', 4), 'ko': ('ko_text', 2)}
# an ultimate whose main effect has a more specific name also answers to the move's own name (same rects), so the
# engine's `get(<ultimate>)` never falls through to a procedural stand-in
ULT_ALIASES = {'rasengan': 'rasengan_burst', 'bankai': 'bankai_aura', 'odm_strike': 'odm_slash'}


# ---------------------------------------------------------------- character effects
def _energy(pal):
    """(core, hot, accent, deep) ramp from a character's fx palette: white -> yellow -> accent -> dark accent."""
    return W_, pal['fx']['b'], pal['fx']['a'], dark(pal['fx']['a'], 0.45)


def _orb(c, cx, cy, r, ramp, phase=0.0, spin=True):
    core, hot, acc, deep = ramp
    c.disc(cx, cy, r, deep)
    c.disc(cx, cy, r * 0.85, acc)
    c.disc(cx, cy, r * 0.62, hot)
    c.disc(cx - r * 0.12, cy - r * 0.15, r * 0.36, core)
    if spin and r >= 4:
        for j in range(3):
            a = phase + j * 2.094
            for s in range(6):
                rr = r * (0.3 + 0.1 * s)
                aa = a + s * 0.45
                c.px(cx + rr * math.cos(aa), cy + rr * math.sin(aa), core if s < 2 else (hot if s < 4 else deep))


def fx_charge(pal, size, n, ms, rmax, motes=True):
    """A growing ball of energy with orbiting motes (used for every charge phase)."""
    ramp = _energy(pal)
    out = []
    for k in range(n):
        c = Canvas(size, size)
        cx = cy = size / 2
        r = 1.5 + (rmax - 1.5) * k / max(1, n - 1)
        for a in range(0, 360, 60):
            rr = r + 2 + (k % 2)
            c.spike(cx, cy, a + k * 17, rr + 2.5, 0.8, ramp[2], inner=rr * 0.6)
        _orb(c, cx, cy, r, ramp, phase=k * 0.9, spin=k >= 1)
        if motes:
            rng = random.Random(k + 31)
            for j in range(4 + k):
                a = rng.uniform(0, 2 * math.pi)
                rr = r + 2 + rng.uniform(0, size / 2 - r - 3)
                c.px(cx + rr * math.cos(a), cy + rr * math.sin(a), ramp[0] if j % 3 == 0 else ramp[1])
        out.append((c.done(), ms[k] if isinstance(ms, (list, tuple)) else ms))
    return out


def fx_impact(pal, size=28, n=5):
    """A hit burst in the character's colours (special-projectile impacts, super bursts)."""
    core, hot, acc, deep = _energy(pal)
    out = []
    for k in range(n):
        c = Canvas(size, size)
        cx = cy = size / 2
        R = size / 2 - 1
        if k == 0:
            c.disc(cx, cy, R * 0.35, core)
        elif k == 1:
            for a in range(0, 360, 45):
                c.spike(cx, cy, a + 10, R * (0.95 if a % 90 == 0 else 0.7), 1.8, acc)
            c.disc(cx, cy, R * 0.45, hot)
            c.disc(cx, cy, R * 0.25, core)
        elif k == 2:
            c.ring(cx, cy, R * 0.7, 2, acc)
            c.ring(cx, cy, R * 0.62, 1, hot)
            for a in range(0, 360, 45):
                c.spike(cx, cy, a + 10, R, 1.0, hot if a % 90 == 0 else deep, inner=R * 0.62)
            c.disc(cx, cy, R * 0.15, core)
        elif k == 3:
            for a in range(0, 360, 60):
                c.arc_band(cx, cy, R * 0.8, R * 0.95, a - 12, a + 12, acc)
            for a in range(0, 360, 90):
                c.px(cx + R * math.cos(math.radians(a + 45)), cy + R * math.sin(math.radians(a + 45)), hot)
        else:
            for a in range(0, 360, 40):
                c.px(cx + R * math.cos(math.radians(a)), cy + R * math.sin(math.radians(a)), deep if a % 80 else acc)
        out.append((c.done(), (40, 60, 60, 70, 70)[k]))
    return out


def fx_big_proj(ch):
    """The upgraded special projectile: the proj.png idea at ~2x with a trail, 3 looping frames."""
    pal = ch.body.palette
    core, hot, acc, deep = _energy(pal)
    style = ch.projectile['style']
    out = []
    for k in range(3):
        c = Canvas(40, 24)
        if style == 'arc':
            for r, col, t in ((11 + k, deep, 3.5), (10 + k, acc, 2.4), (9.5 + k, hot, 1.3), (9.2 + k, core, 0.6)):
                c.arc_band(14, 12, r - t, r, -62, 62, col)
            for j in range(4):
                c.line((2 + (k + j) % 3, 5 + j * 4.5), (8 + (j % 2) * 3, 5 + j * 4.5), acc if j % 2 else hot, 1)
        elif style == 'term':
            ink = pal['ink']['base']
            c.rect(10, 4, 36, 20, ink)
            c.rect(11, 5, 35, 19, pal['trim']['base'] if ch.name == 'codex' else pal['cloth']['hi'])
            c.rect(11, 15, 35, 19, pal['trim']['sh'] if ch.name == 'codex' else pal['cloth']['base'])
            for dx, dy in ((0, 0), (1, 1), (2, 2), (3, 3), (2, 4), (1, 5), (0, 6)):
                c.rect(14 + dx, 7 + dy, 15 + dx, 7 + dy, core)
            if ch.projectile['glyph'].endswith('_'):
                c.rect(21, 13, 29, 14, core)
            else:
                c.rect(22, 7, 23 + (k == 1), 14, core)
            for j in range(4 + k):
                c.line((0, 6 + j * 3), (6 + (j % 2) * 3, 6 + j * 3), acc, 1)
        elif style == 'star':
            cx, cy = 24, 12
            for a in range(0, 360, 90):
                c.spike(cx, cy, a + k * 15, 11, 2.2, acc)
                c.spike(cx, cy, a + k * 15, 9, 1.2, hot)
            for a in range(45, 360, 90):
                c.spike(cx, cy, a + k * 15, 6, 1.2, acc)
            c.disc(cx, cy, 3, core)
            for j in range(3):
                c.px(4 + j * 4 + k, 5 + j * 5, hot)
        else:
            _orb(c, 26, 12, 9 + (k == 1), (core, hot, acc, deep), phase=k * 1.0)
            for j in range(4 + k):
                c.line((0 + j % 2, 4 + j * 4), (10 - (j % 2) * 3, 4 + j * 4), acc if j % 2 else hot, 1)
        out.append((c.done(), 90))
    return dict(frames=out, anchor='hand', offset=(14, 0), loop=True, travel=dict(speed=160))


def fx_super_burst(pal):
    """A flash ring for the supers: the big-glyph power-up gets a real burst."""
    core, hot, acc, deep = _energy(pal)
    out = []
    for k in range(4):
        c = Canvas(48, 48)
        cx = cy = 24
        r = 6 + k * 5.5
        c.ring(cx, cy, r, 3 - k * 0.5, acc)
        c.ring(cx, cy, r - 1, 1.2, hot)
        for a in range(0, 360, 30):
            c.px(cx + (r + 2) * math.cos(math.radians(a + k * 10)), cy + (r + 2) * math.sin(math.radians(a + k * 10)), core if a % 60 else hot)
        if k == 0:
            c.disc(cx, cy, 4, core)
        out.append((c.done(), 60))
    return dict(frames=out, anchor='center', offset=(0, 0), layer='back', shake=dict(frames=3, amp=2))


# ---- ultimates
def fx_kamehameha(pal):
    core, hot, acc, deep = _energy(pal)
    out = []
    L, Hh = 128, 28
    for k in range(6):
        c = Canvas(L, Hh)
        cy = Hh / 2
        if k == 0:
            _orb(c, 8, cy, 6, (core, hot, acc, deep), spin=False)
            for a in range(0, 360, 45):
                c.spike(8, cy, a, 11, 1.0, hot, inner=6)
        else:
            reach = L if k > 1 else L * 0.55
            fade = k == 5
            for (hw, col) in ((11, deep), (9, acc), (6.5, hot), (3.5, core)):
                if fade and hw > 6.5:
                    continue
                pts = []
                for x in range(0, int(reach) + 1, 2):
                    w = hw * (0.7 + 0.3 * min(1.0, x / 16.0)) + (0.9 * math.sin(x * 0.5 + k * 1.3) if hw > 4 else 0)
                    pts.append((x, cy - w))
                for x in range(int(reach), -1, -2):
                    w = hw * (0.7 + 0.3 * min(1.0, x / 16.0)) + (0.9 * math.sin(x * 0.5 + k * 1.3 + 1.5) if hw > 4 else 0)
                    pts.append((x, cy + w))
                c.poly(pts, col)
            if not fade:
                _orb(c, 8, cy, 9, (core, hot, acc, deep), phase=k * 0.7, spin=False)
                c.disc(8, cy, 5, core)
            for j in range(0, int(reach), 9):                      # energy streaks along the beam
                yy = cy + (-3 if (j // 9 + k) % 2 else 3)
                c.line((j + 2, yy), (j + 6, yy), core if not fade else hot, 1)
            if k >= 2 and reach >= L:
                for a in range(-70, 71, 35):
                    c.spike(L - 2, cy, 180 + a, 10, 1.2, hot, inner=4)
        out.append((c.done(), (80, 80, 150, 150, 150, 120)[k]))
    return dict(frames=out, anchor='hand', offset=(64, 0), hit_frame=1, shake=dict(frames=8, amp=3))


def fx_rasengan_orb(pal):
    out = []
    ramp = _energy(pal)
    for k in range(4):
        c = Canvas(22, 22)
        _orb(c, 11, 11, 7, ramp, phase=k * 1.3)
        for a in range(0, 360, 90):
            c.px(11 + 9.5 * math.cos(math.radians(a + k * 25)), 11 + 9.5 * math.sin(math.radians(a + k * 25)), ramp[1])
        out.append((c.done(), 60))
    return dict(frames=out, anchor='center', offset=(0, 0), loop=True)


def fx_rasengan_burst(pal):
    core, hot, acc, deep = _energy(pal)
    out = []
    for k in range(6):
        c = Canvas(56, 56)
        cx = cy = 28
        R = 6 + k * 4.2
        c.disc(cx, cy, R, deep)
        c.disc(cx, cy, R * 0.8, acc)
        if k < 4:
            c.disc(cx, cy, R * 0.55, hot)
            c.disc(cx, cy, R * 0.3, core)
        for j in range(3):                                            # spiral arms
            for s in range(14):
                t = s / 13.0
                rr = R * (0.2 + 0.85 * t)
                a = j * 2.094 + t * 4.2 + k * 0.6
                c.px(cx + rr * math.cos(a), cy + rr * math.sin(a), core if t < 0.5 else hot)
                c.px(cx + rr * math.cos(a + 0.12), cy + rr * math.sin(a + 0.12), hot if t < 0.5 else deep)
        if k >= 2:
            for a in range(0, 360, 30):
                c.spike(cx, cy, a + k * 7, R + 4 + (a % 60 == 0) * 3, 0.9, hot if a % 60 == 0 else acc, inner=R)
        out.append((c.done(), (60, 60, 70, 80, 90, 100)[k]))
    return dict(frames=out, anchor='hand', offset=(10, 0), hit_frame=1, shake=dict(frames=6, amp=3))


def fx_clone_poof():
    out = []
    for k in range(4):
        c = Canvas(36, 28)
        for j, (x, y, r) in enumerate(((10, 16, 5), (18, 12, 6.5), (26, 16, 5), (14, 20, 4), (22, 20, 4))):
            rr = r * (1.3 - k * 0.3)
            if rr > 0.8:
                c.disc(x + (x - 18) * k * 0.2, y - k * 1.5, rr, G1 if j % 2 else G2)
                c.disc(x + (x - 18) * k * 0.2 - rr * 0.3, y - k * 1.5 - rr * 0.3, rr * 0.45, W_)
        out.append((c.done(), (50, 70, 80, 90)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0))


def fx_shadow_clones(ch, hands):
    """Three looping run frames of the character itself, flattened to its trim colours with a checker shimmer."""
    import moves
    body = ch.body
    pal = body.palette
    mv = moves.build_moves(ch)['dash']
    hi, base, ink = pal['trim']['hi'], pal['trim']['base'], pal['ink']['base']
    out = []
    S = rig.RES
    for i in (1, 2, 3):
        pose = mv['frames'][i][0]
        buf, meta = rig.render_parts(body, pose, None)
        im = rig.finish(buf, body, pose, meta['hip'][1])
        px, bp = im.load(), buf.load()
        for y in range(im.height):
            for x in range(im.width):
                if px[x, y][3]:
                    px[x, y] = (ink if not bp[x, y] else (hi if (x // S + y // S) % 2 == 0 else base)) + (255,)
        out.append((im, 80))
    return dict(frames=out, anchor='ground', offset=(0, -rig.W // 2), loop=True, travel=dict(speed=220), layer='back')


def fx_getsuga_charge(pal):
    core, hot, acc, deep = _energy(pal)
    ink = INK
    out = []
    for k in range(3):
        c = Canvas(26, 26)
        cx = cy = 13
        for a in range(0, 360, 60):
            c.spike(cx, cy, a + k * 20, 11, 1.3, ink, inner=5)
            c.spike(cx, cy, a + k * 20, 9, 0.7, acc, inner=5)
        _orb(c, cx, cy, 3 + k * 1.5, (core, acc, deep, ink), phase=k, spin=False)
        out.append((c.done(), (200, 220, 240)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0))


def fx_getsuga(pal):
    core, hot, acc, deep = _energy(pal)
    out = []
    for k in range(4):
        c = Canvas(52, 56)
        cx, cy = 16, 28
        a0, a1 = -72, 72
        for (r0, r1, col) in ((19, 25, INK), (18, 24, deep), (17, 22, acc), (18, 20.5, pal['fx']['c']), (18.4, 19.6, core)):
            c.arc_band(cx, cy, r0 + (k % 2) * 0.5, r1 + (k % 2) * 0.5, a0, a1, col)
        for j in range(5):                                            # ragged energy flares off the outer edge
            a = math.radians(a0 + (a1 - a0) * (j + 0.5) / 5)
            L = 5 + ((j + k) % 3) * 2
            c.spike(cx + 24 * math.cos(a), cy + 24 * math.sin(a), math.degrees(a), L, 1.4, INK)
            c.spike(cx + 24 * math.cos(a), cy + 24 * math.sin(a), math.degrees(a), L * 0.7, 0.7, acc)
        for j in range(3):                                            # trailing streaks behind the wave
            yy = cy - 10 + j * 10
            c.line((1, yy), (7 + (k + j) % 2 * 3, yy), deep if j % 2 else acc, 1)
        out.append((c.done(), 70))
    return dict(frames=out, anchor='center', offset=(18, 0), loop=True, travel=dict(speed=260), hit_frame=0)


def fx_getsuga_impact(pal):
    fr = fx_impact(pal, 40, 5)
    return dict(frames=fr, anchor='center', offset=(0, 0), hit_frame=1, shake=dict(frames=5, amp=3))


def fx_odm_lines(pal):
    core, hot, acc, deep = _energy(pal)
    out = []
    L = 100
    for k in range(4):
        c = Canvas(L, 24)
        reach = L * (0.35, 0.7, 1.0, 1.0)[k]
        for j, y0 in enumerate((8, 16)):
            y1 = y0 + (1 if j == 0 else -1) * 3
            c.line((0, y0), (reach - 3, y1), GL3, 1.4)
            c.line((0, y0), (reach - 3, y1), GL1, 0.7)
            hx, hy = reach - 3, y1
            c.poly([(hx, hy - 2.5), (hx + 3.5, hy), (hx, hy + 2.5), (hx - 1.5, hy)], G1)   # the hook
            c.poly([(hx, hy - 1), (hx + 2, hy), (hx, hy + 1)], INK)
            if k == 3:
                for a in (-50, -20, 20, 50):
                    c.spike(hx + 2, hy, a, 4.5, 0.6, acc, inner=2)
                c.px(hx + 3, hy, core)
        for j in range(0, int(reach), 12):                            # gas puffs along the line
            c.px(j + (k * 3) % 12, 12, G2)
        out.append((c.done(), (50, 50, 100, 100)[k]))
    return dict(frames=out, anchor='hand', offset=(50, 2), layer='back')


def fx_odm_slash(pal):
    core, hot, acc, deep = _energy(pal)
    out = []
    for k in range(4):
        c = Canvas(48, 48)
        cx = cy = 24
        L = (12, 20, 22, 22)[k]
        for a in (45, 135, 225, 315):
            if k < 3:
                c.spike(cx, cy, a, L, 2.4, deep, inner=0)
                c.spike(cx, cy, a, L - 1, 1.5, acc, inner=0)
                c.spike(cx, cy, a, L - 3, 0.7, core, inner=0)
            else:
                c.spike(cx, cy, a, L, 0.8, acc, inner=L - 6)
        if k == 1:
            c.disc(cx, cy, 4, core)
            for a in range(0, 360, 45):
                c.arc_band(cx, cy, 15, 17, a - 8, a + 8, hot)
        if k == 2:
            c.ring(cx, cy, 19, 1.2, acc)
        out.append((c.done(), (50, 80, 80, 70)[k]))
    return dict(frames=out, anchor='center', offset=(10, 0), hit_frame=1, shake=dict(frames=4, amp=2))


def fx_wind_scar(pal):
    core, hot, acc, deep = _energy(pal)
    out = []
    Wd, Hh = 100, 52
    for k in range(5):
        c = Canvas(Wd, Hh)
        base = Hh - 3
        for j in range(3):                                            # three claws, tallest in the middle
            x = 14 + j * 30 + (k % 2) * 2
            h = (32, 44, 36)[j] * (0.5 + 0.5 * min(1.0, k / 2.0))
            lean = 8
            for (wid, col) in ((9, deep), (7, acc), (4.5, hot), (2, core)):
                c.poly([(x - wid, base), (x + wid, base), (x + lean + wid * 0.3, base - h * 0.55), (x + lean * 1.6, base - h)], col)
            for s in range(3):
                c.px(x + lean * 1.6 + s * 2 - 2, base - h - 2 - (s % 2) * 2 - k, hot if s % 2 else core)
        for x in range(0, Wd, 6):                                     # ripped ground: dirt and stone
            c.rect(x + (k * 2) % 6, base - 1 + (x // 6) % 2, x + 3 + (k * 2) % 6, base + 1, G3 if x % 12 else G2)
            if k >= 1:
                c.px(x + 2 + (k * 2) % 6, base - 3 - (x // 6) % 3 - k, G1 if x % 12 else G2)
        out.append((c.done(), (60, 70, 70, 70, 70)[k]))
    return dict(frames=out, anchor='ground', offset=(36, -Hh // 2 + 2), loop=True, travel=dict(speed=240), hit_frame=1,
                shake=dict(frames=6, amp=3))


def fx_wind_scar_impact(pal):
    fr = _explosion(56, (W_, pal['fx']['b'], pal['fx']['a'], EMB, SMK), 7)
    return dict(frames=fr, anchor='center', offset=(0, 4), hit_frame=1, shake=dict(frames=6, amp=4))


def fx_bankai_aura(pal):
    core, hot, acc, deep = _energy(pal)
    teal = pal['fx']['c']
    out = []
    Wd, Hh = 56, 100
    for k in range(6):
        c = Canvas(Wd, Hh)
        cx, base = Wd / 2, Hh - 4
        if k == 0:
            c.ring(cx, base - 2, 14, 2.5, acc)
            c.ring(cx, base - 2, 12, 1, core)
            c.disc(cx, base - 10, 6, core)
        elif k <= 3:
            h = Hh * (0.5, 0.95, 1.0)[k - 1]
            top = base - h
            for (hw, col) in ((24, deep), (20, acc), (15, teal), (9, hot), (4, core)):
                pts = []
                wob = 0.6 if hw > 9 else 0.3                          # a flame edge, not a ribbon
                for yy in range(int(top), int(base) + 1, 3):
                    t = (yy - top) / max(1.0, h)
                    w = hw * (0.55 + 0.45 * t) + wob * math.sin(yy * 0.3 + k * 1.1)
                    pts.append((cx - w, yy))
                for yy in range(int(base), int(top) - 1, -3):
                    t = (yy - top) / max(1.0, h)
                    w = hw * (0.55 + 0.45 * t) + wob * math.sin(yy * 0.3 + k * 1.1 + 2)
                    pts.append((cx + w, yy))
                pts.insert(0, (cx - 2, top - 4))                      # the pillar tapers to a flame tip
                pts.append((cx + 2, top - 4))
                c.poly(pts, col)
            for j in range(8):                                        # rising streaks
                xx = cx - 16 + j * 4.6
                y0 = base - (j * 13 + k * 17) % int(h)
                c.line((xx, y0), (xx, y0 - 6), core if j % 2 else hot, 1)
            c.ring(cx, base - 2, 16 + k * 2, 1.5, acc)
        else:
            for j in range(10):
                xx = cx - 20 + j * 4.4
                y0 = base - (j * 17 + k * 23) % (Hh - 10)
                c.line((xx, y0), (xx, y0 - 4), teal if j % 2 else acc, 1)
            if k == 4:
                c.ring(cx, base - 2, 22, 1.2, acc)
        out.append((c.done(), (60, 70, 90, 120, 90, 90)[k]))
    return dict(frames=out, anchor='ground', offset=(0, -Hh // 2 + 4), layer='back', hit_frame=2, shake=dict(frames=6, amp=3))


def fx_bankai_slash(pal):
    core, hot, acc, deep = _energy(pal)
    teal = pal['fx']['c']
    out = []
    for k in range(3):
        c = Canvas(44, 44)
        for j in range(3):
            a = -35 + j * 30 + k * 10
            L = 18 - j * 2
            x, y = 22 + (j - 1) * 5, 22 + (j - 1) * 3
            c.spike(x, y, a, L, 2.0, deep)
            c.spike(x, y, a + 180, L * 0.7, 2.0, deep)
            c.spike(x, y, a, L - 1, 1.1, acc if j % 2 else teal)
            c.spike(x, y, a + 180, L * 0.7 - 1, 1.1, acc if j % 2 else teal)
            c.spike(x, y, a, L - 4, 0.5, core)
        c.disc(22, 22, 3, core)
        for a in range(0, 360, 45):
            c.px(22 + 16 * math.cos(math.radians(a + k * 15)), 22 + 16 * math.sin(math.radians(a + k * 15)), hot)
        out.append((c.done(), 90))
    return dict(frames=out, anchor='center', offset=(12, 0), hit_frame=0, shake=dict(frames=3, amp=2))


def fx_spirit_bomb_orb(pal):
    out = []
    ramp = _energy(pal)
    for k in range(4):
        c = Canvas(44, 44)
        r = 5 + k * 4
        _orb(c, 22, 22, r, ramp, phase=k * 0.8, spin=k >= 2)
        rng = random.Random(k + 7)
        for j in range(6 + k * 3):                                    # gathered sparkles drifting in
            a = rng.uniform(0, 2 * math.pi)
            rr = r + 2 + rng.uniform(0, 20 - r)
            c.px(22 + rr * math.cos(a), 22 + rr * math.sin(a), ramp[0] if j % 3 == 0 else ramp[1])
        out.append((c.done(), (240, 260, 300, 300)[k]))
    return dict(frames=out, anchor='center', offset=(2, -34))


def fx_spirit_bomb(pal):
    out = []
    ramp = _energy(pal)
    for k in range(4):
        c = Canvas(44, 44)
        _orb(c, 22, 22, 17, ramp, phase=k * 0.9)
        for a in range(0, 360, 30):
            c.px(22 + 20 * math.cos(math.radians(a + k * 8)), 22 + 20 * math.sin(math.radians(a + k * 8)), ramp[0] if a % 60 else ramp[1])
        out.append((c.done(), 90))
    return dict(frames=out, anchor='center', offset=(24, -10), loop=True, travel=dict(speed=150), hit_frame=0)


def fx_spirit_bomb_impact(pal):
    fr = _explosion(64, (W_, pal['fx']['b'], pal['fx']['a'], EMB, SMK), 7)
    return dict(frames=fr, anchor='center', offset=(0, 0), hit_frame=1, shake=dict(frames=8, amp=5))


ULT_FX = {
    'kamehameha': lambda ch, h: {'kamehameha_charge': dict(frames=fx_charge(ch.body.palette, 24, 5, (200, 220, 240, 260, 280), 8),
                                                           anchor='center', offset=_hand_off(h, 'kamehameha', 2, 'hb')),
                                 'kamehameha': fx_kamehameha(ch.body.palette)},
    'rasengan': lambda ch, h: {'rasengan_orb': dict(fx_rasengan_orb(ch.body.palette), offset=_hand_off(h, 'rasengan', 1, 'hf', (1, -5))),
                               'rasengan_burst': fx_rasengan_burst(ch.body.palette),
                               'clone_poof': fx_clone_poof(), 'shadow_clones': fx_shadow_clones(ch, h)},
    'getsuga': lambda ch, h: {'getsuga_charge': dict(fx_getsuga_charge(ch.body.palette), offset=_hand_off(h, 'getsuga', 1, 'hf', (0, -4))),
                              'getsuga': fx_getsuga(ch.body.palette), 'getsuga_impact': fx_getsuga_impact(ch.body.palette)},
    'odm_strike': lambda ch, h: {'odm_lines': fx_odm_lines(ch.body.palette), 'odm_slash': fx_odm_slash(ch.body.palette)},
    'wind_scar': lambda ch, h: {'wind_scar_charge': dict(frames=fx_charge(ch.body.palette, 28, 4, (200, 220, 240, 240), 9),
                                                         anchor='center', offset=_hand_off(h, 'wind_scar', 1, 'hf', (0, -5))),
                                'wind_scar': fx_wind_scar(ch.body.palette), 'wind_scar_impact': fx_wind_scar_impact(ch.body.palette)},
    'bankai': lambda ch, h: {'bankai_aura': fx_bankai_aura(ch.body.palette), 'bankai_slash': fx_bankai_slash(ch.body.palette)},
    'spirit_bomb': lambda ch, h: {'spirit_bomb_orb': fx_spirit_bomb_orb(ch.body.palette), 'spirit_bomb': fx_spirit_bomb(ch.body.palette),
                                  'spirit_bomb_impact': fx_spirit_bomb_impact(ch.body.palette)},
}


_HAND_CACHE = {}


def _hand_off(hands, move, i, which, extra=(0, 0)):
    """Offset (design px) of a hand in frame i of `move` from the `center` anchor, from the rig's own metadata
    (passed in by the fighter build, or rendered here for a standalone effects rebuild)."""
    S = rig.RES
    m = hands.get((move, i)) if hands else None
    if m is None:
        key = (hands.get('_name') if hands else None, move, i, S)
        m = _HAND_CACHE.get(key)
        if m is None:
            import moves, roster
            ch = next(c for c in roster.ROSTER.values() if move in c.sig_moves)
            pose = moves.build_moves(ch)[move]['frames'][i][0]
            m = _HAND_CACHE[key] = rig.render_parts(ch.body, pose, None)[1]
    cx, cy = rig.hip_x_px(), rig.ground_px() - CENTER_DY * S
    hx, hy = m[which]
    return (rig.rnd((hx - cx) / S + extra[0]), rig.rnd((hy - cy) / S + extra[1]))


# ---------------------------------------------------------------- packing + json
def _scale_meta(e):
    """Design-unit placement -> px at this RES; exact schema keys only."""
    S = rig.RES
    off = e.get('offset', (0, 0))
    return dict(anchor=e.get('anchor', 'center'), offset=[int(off[0]) * S, int(off[1]) * S], loop=bool(e.get('loop', False)),
                layer=e.get('layer', 'front'), hit_frame=e.get('hit_frame'),
                travel=(dict(speed=int(e['travel']['speed']) * S) if e.get('travel') else None),
                shake=(dict(frames=int(e['shake']['frames']), amp=int(e['shake']['amp']) * S) if e.get('shake') else None))


def pack(effects, width):
    """Shelf-pack every frame into one RGBA sheet.  -> (sheet, {name: [frame rects]})."""
    items = []
    for name, e in effects.items():
        for i, (im, ms) in enumerate(e['frames']):
            items.append((im.height, im.width, name, i, im, ms))
    order = sorted(range(len(items)), key=lambda j: (-items[j][0], -items[j][1], items[j][2], items[j][3]))
    x = y = shelf = 0
    pos = {}
    for j in order:
        h, w, name, i, im, ms = items[j]
        if x + w > width:
            x, y, shelf = 0, y + shelf, 0
        pos[(name, i)] = (x, y, w, h, ms)
        x += w
        shelf = max(shelf, h)
    height = y + shelf
    sheet = Image.new('RGBA', (width, max(1, height)), (0, 0, 0, 0))
    rects = {}
    for h, w, name, i, im, ms in items:
        x, y, w, h, ms = pos[(name, i)]
        sheet.paste(im, (x, y))
        rects.setdefault(name, []).append(dict(x=x, y=y, w=w, h=h, ms=int(ms)))
    for name in rects:
        rects[name].sort(key=lambda r: effects[name]['frames'].index(next(f for f in effects[name]['frames'] if True)) if False else 0)
    # keep frame order as authored
    ordered = {}
    for name, e in effects.items():
        ordered[name] = [None] * len(e['frames'])
        for i in range(len(e['frames'])):
            x, y, w, h, ms = pos[(name, i)]
            ordered[name][i] = dict(x=x, y=y, w=w, h=h, ms=int(ms))
    return sheet, ordered


def colours(im):
    return {p[:3] for _, p in im.getcolors(1 << 20) if p[3]}


def write_sheet(effects, out_dir, res, cap, sheet_name='fx.png', json_name='fx.json'):
    width = 512 * res
    sheet, rects = pack(effects, width)
    cols = colours(sheet)
    if len(cols) + 1 > cap:
        raise SystemExit(f'{out_dir}: fx sheet has {len(cols)} colours + transparency, cap {cap}')
    a = sheet.getchannel('A')
    assert {v for _, v in a.getcolors()} <= {0, 255}, 'partial alpha in fx sheet'
    os.makedirs(out_dir, exist_ok=True)
    sheet.save(os.path.join(out_dir, sheet_name))
    meta = {'res': res, 'sheet': sheet_name, 'effects': {}}
    for name, e in effects.items():
        meta['effects'][name] = dict(frames=rects[name], **_scale_meta(e))
    for alias, (src, i) in ALIASES.items():
        if src in effects and i < len(rects[src]):
            meta['effects'][alias] = dict(frames=[dict(rects[src][i])], **_scale_meta(effects[src]))
    for alias, src in ULT_ALIASES.items():
        if src in effects and alias not in effects:
            meta['effects'][alias] = dict(frames=[dict(r) for r in rects[src]], **_scale_meta(effects[src]))
    with open(os.path.join(out_dir, json_name), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1)
    return meta, len(cols)


def generic_effects():
    return {name: fn() for name, fn in GENERIC.items()}


def character_effects(ch, hands=None):
    """Generic set + this character's upgraded special / super effects + its ultimate effects."""
    pal = ch.body.palette
    eff = generic_effects()
    special, sup, ult = ch.signature['special'], ch.signature['super'], ch.signature.get('ultimate')
    eff[f'{special}_proj'] = fx_big_proj(ch)
    eff[f'{special}_impact'] = dict(frames=fx_impact(pal, 28, 5), anchor='center', offset=(0, 0), hit_frame=1, shake=dict(frames=2, amp=1))
    eff[f'{sup}_burst'] = fx_super_burst(pal)
    if ult and ult in ULT_FX:
        eff.update(ULT_FX[ult](ch, hands or {}))
    return eff


def build_character(ch, out_dir, res, cap, hands=None, anims=None):
    """Write <out_dir>/fx.png + fx.json for one character at `res`.  Adds `hand` (px from the ground anchor) to every
    anim entry that has a proj_frame so the engine can resolve the `hand` anchor exactly."""
    rig.set_res(res)
    S = rig.RES
    if anims is not None and hands:
        for name, a in anims.items():
            pf = a.get('proj_frame')
            if pf is None or (name, pf) not in hands:
                continue
            m = hands[(name, pf)]
            a['hand'] = [int(rig.rnd(m['hf'][0] - rig.hip_x_px())), int(rig.rnd(m['hf'][1] - rig.ground_px()))]
    eff = character_effects(ch, hands)
    meta, n = write_sheet(eff, out_dir, res, cap)
    print(f'  fx {ch.name} @RES {S}: {len(meta["effects"])} effects, {sum(len(e["frames"]) for e in eff.values())} frames, {n} colours (+transparent)')
    return meta


def build_shared(out_dir, res, cap):
    """The colour-neutral generic set alone, at <out_dir>/ (the engine's first lookup path)."""
    rig.set_res(res)
    meta, n = write_sheet(generic_effects(), out_dir, res, cap)
    print(f'  fx shared @RES {res}: {len(meta["effects"])} effects, {n} colours (+transparent)')
    return meta


if __name__ == '__main__':
    import argparse, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import roster
    ap = argparse.ArgumentParser(description='Rebuild only the effects sheets (the fighter build calls this itself).')
    ap.add_argument('--res', type=int, default=1)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    root = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets' if a.res == 1 else 'assets_hd')
    cap = 32 if a.res == 1 else 64
    for name in roster.NAMES:
        build_character(roster.get(name), os.path.join(root, name), a.res, cap)
    build_shared(os.path.join(root, 'fx'), a.res, cap)
