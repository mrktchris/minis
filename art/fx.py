"""Effects sheets: every effect is rendered from code at the current rig RES into <out>/fx.png + fx.json.

fx.json (docs/V4-WORKORDER.md "Shared interfaces", exact per-effect keys):
  {"res": k, "sheet": "fx.png",
   "effects": {"<name>": {"frames": [{"x","y","w","h","ms"}], "anchor": "hand|ground|center", "offset": [dx, dy],
                          "loop": bool, "layer": "front|back", "hit_frame": n|null,
                          "travel": {"speed": px_per_s}|null, "shake": {"frames": n, "amp": px}|null,
                          "grow": {"from_w", "to_w", "ms"}|null, "flash": bool}},
   "schema_notes": {...}}                                       (V5.1: `grow` and `flash`, see FX_SCHEMA_NOTES)

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


# ---------------------------------------------------------------- V7 contact sparks (per hit type; drawn facing +x = toward the
# attacker, since they spawn on the defender, who faces the attacker)
def fx_hit_slash():
    """Slash: a thin, bright arc cut diagonally across the body (hairline -> full -> broken), sparks thrown off the edge."""
    out = []
    ox, oy, r = 30, 30, 22.5                   # the cut is an arc of a big circle: low-back to high-front
    for k in range(4):
        c = Canvas(32, 28)
        if k == 0:
            c.arc_band(ox, oy, r - 0.4, r + 0.4, 200, 252, W_)
        elif k == 1:
            c.arc_band(ox, oy, r - 1.4, r + 1.0, 194, 258, Y_)
            c.arc_band(ox, oy, r - 0.6, r + 0.4, 198, 254, W_)
            for a, L in ((-70, 6), (-35, 7), (0, 6), (35, 5)):
                c.spike(15, 13, a, L, 0.6, W_ if L > 5 else Y_, inner=2)
        elif k == 2:
            for a0 in range(196, 256, 10):
                c.arc_band(ox, oy, r - 0.8, r + 0.6, a0, a0 + 6, O_)
            for a, L in ((-70, 9), (-35, 10), (0, 9), (35, 8)):
                c.px(15 + L * math.cos(math.radians(a)), 13 + L * math.sin(math.radians(a)), Y_)
        else:
            for a, L in ((-70, 12), (0, 12), (35, 10)):
                c.px(15 + L * math.cos(math.radians(a)), 14 + L * math.sin(math.radians(a)), O_)
        out.append((c.done(), (40, 60, 60, 70)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0), hit_frame=1)


def fx_hit_blunt():
    """Blunt: a white core, then a radial shock ring that widens and thins, with dust kicked out at the bottom."""
    out = []
    for k in range(4):
        c = Canvas(32, 32)
        cx = cy = 16
        if k == 0:
            c.disc(cx, cy, 5, W_)
            c.ring(cx, cy, 7, 1.2, Y_)
        elif k == 1:
            c.ring(cx, cy, 9, 2.6, Y_)
            c.ring(cx, cy, 8.5, 1.2, W_)
            for a in range(0, 360, 45):
                c.spike(cx, cy, a, 14, 1.0, O_ if a % 90 else Y_, inner=11)
            c.disc(cx, cy, 3, W_)
        elif k == 2:
            c.ring(cx, cy, 13, 1.4, O_)
            for x, r in ((7, 2.4), (11, 3.0), (21, 3.0), (25, 2.4)):
                c.disc(x, 27, r, G2)
                c.disc(x - 0.7, 26.3, r * 0.55, G1)
        else:
            for a in range(0, 360, 30):
                c.px(cx + 14.5 * math.cos(math.radians(a)), cy + 14.5 * math.sin(math.radians(a)), O_ if a % 60 else EMB)
            for x in (5, 12, 20, 27):
                c.px(x, 25 + (x % 2), G2)
        out.append((c.done(), (40, 60, 70, 80)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0), hit_frame=1, shake=dict(frames=2, amp=1))


def fx_hit_pierce():
    """Pierce: a long white streak driven straight through from the front, then a spray fanning out behind."""
    out = []
    ox = 14                                     # where the point comes out of the back
    for k in range(4):
        c = Canvas(40, 18)
        cy = 9
        if k == 0:
            c.line((38, cy), (ox, cy), W_, 1.2)
            c.line((38, cy), (24, cy), Y_, 2.2)
        elif k == 1:
            c.poly([(39, cy - 1.6), (ox + 2, cy - 0.4), (ox - 2, cy), (ox + 2, cy + 0.4), (39, cy + 1.6)], Y_)
            c.line((38, cy), (ox, cy), W_, 1.0)
            for a, L in ((160, 7), (175, 9), (190, 7), (150, 5), (205, 5)):
                c.spike(ox, cy, a, L, 0.5, W_ if L > 6 else Y_)
        elif k == 2:
            for a, L in ((160, 9), (175, 11), (190, 9), (150, 7), (205, 7)):
                c.px(ox + L * math.cos(math.radians(a)), cy + L * math.sin(math.radians(a)), Y_)
                c.px(ox + (L - 2) * math.cos(math.radians(a)), cy + (L - 2) * math.sin(math.radians(a)), O_)
            for x in range(24, 38, 3):
                c.px(x, cy, O_)
        else:
            for a, L in ((160, 12), (190, 12), (175, 13)):
                c.px(ox + L * math.cos(math.radians(a)), cy + L * math.sin(math.radians(a)), O_)
        out.append((c.done(), (40, 60, 60, 70)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0), hit_frame=1)


def fx_block_deflect():
    """Block: a clang flash on the guard and sparks deflected back toward the attacker, then a ringing arc."""
    out = []
    for k in range(4):
        c = Canvas(24, 24)
        cx, cy = 9, 12
        if k == 0:
            c.disc(cx, cy, 4, W_)
            c.ring(cx, cy, 5.5, 1.0, GL1)
        elif k == 1:
            c.arc_band(cx, cy, 6, 8, -70, 70, GL2)
            c.arc_band(cx, cy, 6.6, 7.4, -50, 50, W_)
            for a, L in ((-55, 10), (-25, 12), (10, 13), (40, 10), (65, 8)):
                c.spike(cx + 2, cy, a, L, 0.6, W_ if L > 11 else GL1, inner=4)
            c.disc(cx, cy, 2, W_)
        elif k == 2:
            c.arc_band(cx, cy, 8, 9.2, -60, 60, GL2)
            for a, L in ((-55, 13), (-25, 15), (10, 15), (40, 13), (65, 11)):
                c.px(cx + 2 + L * math.cos(math.radians(a)), cy + L * math.sin(math.radians(a)), Y_)
        else:
            for a0 in range(-60, 60, 20):
                c.arc_band(cx, cy, 9.5, 10.2, a0, a0 + 9, GL3)
        out.append((c.done(), (40, 60, 60, 70)[k]))
    return dict(frames=out, anchor='hand', offset=(0, 0), hit_frame=1)


def fx_clash_sparks():
    """Clash: two weapons lock - a white star where they meet, a fountain of sparks up and out both ways, embers."""
    out = []
    for k in range(5):
        c = Canvas(32, 32)
        cx, cy = 16, 14
        if k == 0:
            c.disc(cx, cy, 4, W_)
            for a in (45, 135, 225, 315):
                c.spike(cx, cy, a, 8, 1.2, W_)
        elif k in (1, 2):
            rr = 1.0 + 0.5 * k
            for a, L in ((-150, 9), (-120, 12), (-90, 13), (-60, 12), (-30, 9), (200, 8), (-20, 7), (160, 8), (20, 8)):
                c.spike(cx, cy, a, L * rr * 0.75, 0.6, W_ if L >= 12 else Y_, inner=2 * k)
            c.disc(cx, cy, 3.5 - k, Y_ if k == 2 else W_)
        elif k == 3:
            for a, L in ((-150, 13), (-120, 16), (-90, 17), (-60, 16), (-30, 13), (200, 11), (160, 11)):
                x, y = cx + L * math.cos(math.radians(a)), cy + L * math.sin(math.radians(a)) + 2
                c.px(x, y, Y_)
                c.px(x, y + 1, O_)
        else:
            for a, L in ((-120, 16), (-60, 16), (200, 12), (160, 12)):
                c.px(cx + L * math.cos(math.radians(a)), cy + L * math.sin(math.radians(a)) + 5, O_)
        out.append((c.done(), (50, 60, 70, 80, 90)[k]))
    return dict(frames=out, anchor='center', offset=(14, -6), hit_frame=0, shake=dict(frames=3, amp=1))


GENERIC = dict(hit_light=fx_hit_light, hit_heavy=fx_hit_heavy, block_spark=fx_block_spark, dust=fx_dust, ko_stars=fx_ko_stars,
               crack_small=fx_crack_small, crack_big=fx_crack_big, shatter=fx_shatter, explosion=fx_explosion,
               letters=fx_letters, ko_text=fx_ko_text, round_text=fx_round_text,
               hit_slash=fx_hit_slash, hit_blunt=fx_hit_blunt, hit_pierce=fx_hit_pierce, block_deflect=fx_block_deflect,
               clash_sparks=fx_clash_sparks)                # V7 contact sparks (after the V4 set, so older rects never move)
ALIASES = {'round_1': ('round_text', 0), 'round_2': ('round_text', 1), 'round_3': ('round_text', 2),
           'fight': ('round_text', 3), 'winner': ('round_text', 4), 'ko': ('ko_text', 2)}
# an ultimate whose main effect has a more specific name also answers to the move's own name (same rects), so the
# engine's `get(<ultimate>)` never falls through to a procedural stand-in
ULT_ALIASES = {'spiral_orb': 'spiral_orb_burst', 'awakening': 'awakening_aura', 'grapple_strike': 'grapple_slash'}


# ---------------------------------------------------------------- character effects
def _energy(pal):
    """(core, hot, accent, deep) ramp from a character's fx palette: white -> yellow -> accent -> dark accent."""
    return W_, pal['fx']['b'], pal['fx']['a'], dark(pal['fx']['a'], 0.45)


def _glow(c, draw_fn, k):
    """A halo layer: draw it on a scratch canvas, checker-dither it (parity flips with k so the halo shimmers frame to
    frame) and composite it UNDER whatever is drawn next.  Pixel art has no alpha, so a glow is a dithered ring."""
    g = Canvas(c.w, c.h)
    draw_fn(g)
    g.dither(keep=k % 2)
    c.im.alpha_composite(g.im)


def _burst(c, cx, cy, r, ramp, k, spikes=8, ring=True):
    """An impact burst: layered disc, alternating licks that rotate with k, a thin ring every other frame."""
    core, hot, acc, deep = ramp
    for j in range(spikes):
        a = j * 360.0 / spikes + k * 13
        c.spike(cx, cy, a, r * (1.7 if j % 2 else 1.35), 1.1, hot if j % 2 else acc, inner=r * 0.55)
    c.disc(cx, cy, r, deep)
    c.disc(cx, cy, r * 0.78, acc)
    c.disc(cx, cy, r * 0.55, hot)
    c.disc(cx, cy, r * 0.3, core)
    if ring and k % 2:
        c.ring(cx, cy, r * 1.3, 0.9, acc)


def _converge(c, cx, cy, r_in, r_out, ramp, k, n, count=8, seed=0):
    """Charge particles converging on (cx, cy): frame k of n puts every mote a step further in along its own spoke, each
    with a short streak pointing the way it travels (inward), so the gathering reads as motion, not sprinkles."""
    core, hot, acc, deep = ramp
    rng = random.Random(seed)
    for j in range(count):
        a = rng.uniform(0, 2 * math.pi)
        lag = rng.uniform(0.0, 0.6)
        t = (k / max(1.0, n - 1) + lag) % 1.0                          # motes at different stages of the fall
        rr = r_out - (r_out - r_in) * t
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        col = core if t > 0.7 else (hot if j % 2 else acc)
        c.px(x, y, col)
        tail = 1.5 + 1.5 * t
        c.line((x, y), (x + tail * math.cos(a), y + tail * math.sin(a)), acc if t > 0.7 else deep, 1)


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


def _trail(c, x_head, cy, ramp, k, n=5, spread=4, step=5):
    """Motion trail behind a travelling projectile (to the left of x_head): staggered dashes that shift with k."""
    core, hot, acc, deep = ramp
    for j in range(n):
        y = cy + ((j * 7 + k * 3) % (2 * spread + 1)) - spread
        x = x_head - 3 - j * step - (k * 2) % step
        ln = 2 + (j % 3)
        if x - ln < 0:
            continue
        c.line((x - ln, y), (x, y), hot if j % 2 == 0 else (acc if j % 3 else deep), 1)
        if j % 2:
            c.px(x - ln - 2, y, deep)


def beam(c, x0, x1, cy, hw, ramp, k, seed=0, head=True, muzzle=True, fade=False):
    """A horizontal energy beam from x0 to x1 with half-width hw: dithered glow halo, deep edge, accent, hot band and a
    white-hot core.  Every band's edge ripples with a phase that moves with k (so consecutive frames differ), the inner
    bands carry noise streaks, the beam necks just off the hands then flares into a wider head at x1, the muzzle flares
    at x0 and the head throws licks.  `fade`: the dying beam, thin and dithered."""
    core, hot, acc, deep = ramp
    rng = random.Random(seed * 131 + k)
    L = max(1.0, x1 - x0)

    def w_at(x, hw_, ph):
        t = (x - x0) / L
        flare = 1.0 + (0.6 * max(0.0, (t - 0.8) / 0.2) ** 1.4 if head else 0.0)
        neck = 0.55 + 0.45 * min(1.0, (x - x0) / 9.0)
        rip = 0.9 * math.sin(x * 0.45 + k * 1.7 + ph) + 0.5 * math.sin(x * 0.21 - k * 1.1 + 2.0 + ph)
        return max(0.6, hw_ * flare * neck + rip * (hw_ / hw))

    def band(cv, hw_, col):
        top = [(x, cy - w_at(x, hw_, 0.0)) for x in range(int(x0), int(x1) + 1, 2)]
        bot = [(x, cy + w_at(x, hw_, 1.9)) for x in range(int(x1), int(x0) - 1, -2)]
        cv.poly(top + bot, col)

    if not fade:
        _glow(c, lambda g: band(g, hw * 1.45, deep), k)
        band(c, hw, deep)
        band(c, hw * 0.78, acc)
        band(c, hw * 0.55, hot)
        band(c, hw * 0.28, core)
    else:
        _glow(c, lambda g: band(g, hw * 0.9, acc), k)
        band(c, hw * 0.45, hot)
        band(c, hw * 0.18, core)
    for j in range(int(L / 5)):                                       # internal noise: streaks ride the inner bands
        x = rng.uniform(x0 + 5, x1 - 7)
        y = cy + rng.uniform(-hw * 0.5, hw * 0.5)
        ln = rng.uniform(2, 6)
        c.line((x, y), (x + ln, y), core if abs(y - cy) < hw * 0.3 else hot, 1)
    for j in range(int(L / 7)):                                       # deep flecks ride the edges
        x = rng.uniform(x0 + 6, x1 - 4)
        s = rng.choice((-1, 1))
        c.px(x, cy + s * (w_at(x, hw, 0.0 if s < 0 else 1.9) * 0.85), deep if not fade else acc)
    if muzzle:
        mx = x0 + hw * 0.35
        for j in range(8):
            a = j * 45 + k * 23
            c.spike(mx, cy, a, hw * 2.0 if j % 2 else hw * 1.6, 1.0, hot if j % 2 else acc, inner=hw * 1.05)
        _orb(c, mx, cy, hw * 1.2, ramp, spin=False)
        c.disc(mx, cy, hw * 0.6, core)
    if head:
        hx = x1 - hw * 0.4
        for j, a in enumerate((-62, -38, -14, 14, 38, 62)):
            ln = hw * (0.9 + 0.5 * ((j + k) % 3))
            c.spike(x1 - 1, cy, 180 + a + k * 5, ln, 1.0, hot if j % 2 else acc, inner=hw * 0.3)
        c.arc_band(hx - hw * 0.4, cy, hw * 1.35, hw * 1.6, 180 - 55 + k * 7, 180 + 55 + k * 7, acc)
        c.arc_band(hx - hw * 0.4, cy, hw * 1.0, hw * 1.15, 180 - 40 - k * 9, 180 + 40 - k * 9, core)


def _wavy_band(c, cx, cy, r0, r1, a0, a1, col, k, amp=0.8, freq=5.0, steps=28):
    """arc_band whose radii ripple along the arc (phase moves with k): an energy crescent, not a drawn arc."""
    pts = []
    for s in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * s / steps)
        w = amp * math.sin(s * freq * 0.35 + k * 1.4)
        pts.append((cx + (r1 + w) * math.cos(a), cy + (r1 + w) * math.sin(a)))
    for s in range(steps, -1, -1):
        a = math.radians(a0 + (a1 - a0) * s / steps)
        w = amp * math.sin(s * freq * 0.35 + k * 1.4 + 2.2)
        pts.append((cx + (r0 + w) * math.cos(a), cy + (r0 + w) * math.sin(a)))
    c.poly(pts, col)


def fx_charge(pal, size, n, ms, rmax, motes=True):
    """A growing ball of energy with particles converging on it (used for every charge phase)."""
    ramp = _energy(pal)
    out = []
    for k in range(n):
        c = Canvas(size, size)
        cx = cy = size / 2
        r = 1.5 + (rmax - 1.5) * k / max(1, n - 1)
        _glow(c, lambda g: g.disc(cx, cy, r + 2.5 + (k % 2), ramp[3]), k)
        for a in range(0, 360, 60):
            rr = r + 2 + (k % 2)
            c.spike(cx, cy, a + k * 17, rr + 2.5, 0.8, ramp[2], inner=rr * 0.6)
        _orb(c, cx, cy, r, ramp, phase=k * 0.9, spin=k >= 1)
        if motes:
            _converge(c, cx, cy, r + 1.5, size / 2 - 1.5, ramp, k, n, count=7 + k, seed=31)
        out.append((c.done(), ms[k] if isinstance(ms, (list, tuple)) else ms))
    return out


def fx_impact(pal, size=28, n=5):
    """A hit burst in the character's colours (special-projectile impacts, super bursts): a flash, a licking burst with
    a dithered halo, a ring, then embers."""
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    out = []
    for k in range(n):
        c = Canvas(size, size)
        cx = cy = size / 2
        R = size / 2 - 1
        if k == 0:
            c.disc(cx, cy, R * 0.45, core)
            for a in range(0, 360, 60):
                c.spike(cx, cy, a, R * 0.8, 1.0, hot, inner=R * 0.3)
        elif k == 1:
            _glow(c, lambda g: g.disc(cx, cy, R * 0.95, deep), k)
            _burst(c, cx, cy, R * 0.55, ramp, k, spikes=8, ring=False)
        elif k == 2:
            _glow(c, lambda g: g.disc(cx, cy, R, deep), k)
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
    """The upgraded special projectile: the proj.png idea at ~2x, four looping frames that spin / pulse, each with a
    dithered halo and a motion trail."""
    pal = ch.body.palette
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    style = ch.projectile['style']
    out = []
    for k in range(4):
        c = Canvas(44, 26)
        cy = 13
        if style == 'arc':                                            # a crescent wave that breathes and ripples
            cx = 16
            _glow(c, lambda g: _wavy_band(g, cx, cy, 8.5 + (k % 2) * 0.5, 13.5 + (k % 2) * 0.5, -70, 70, deep, k, amp=0.6), k)
            for r0, r1, col in ((8.0, 11.8, deep), (8.4, 11.0, acc), (8.9, 10.3, hot), (9.3, 9.9, core)):
                _wavy_band(c, cx, cy, r0 + (k % 2) * 0.4, r1 + (k % 2) * 0.4, -64, 64, col, k, amp=0.5)
            for j, a in enumerate((-58, -30, 0, 30, 58)):
                c.spike(cx + 11.5 * math.cos(math.radians(a)), cy + 11.5 * math.sin(math.radians(a)), a, 2.5 + ((j + k) % 2) * 2, 0.8, hot if j % 2 else acc)
            _trail(c, cx - 4, cy, ramp, k, n=5, spread=6)
        elif style == 'term':                                         # a terminal block bobbing on its glow, caret blinking
            ink = pal['ink']['base']
            face = pal['trim']['base'] if ch.name == 'codex' else pal['cloth']['hi']
            shade = pal['trim']['sh'] if ch.name == 'codex' else pal['cloth']['base']
            dy = (0, -1, 0, 1)[k]
            _glow(c, lambda g: g.rect(11, 4 + dy, 39, 22 + dy, acc), k)
            c.rect(13, 6 + dy, 37, 20 + dy, ink)
            c.rect(14, 7 + dy, 36, 19 + dy, face)
            c.rect(14, 16 + dy, 36, 19 + dy, shade)
            for ddx, ddy in ((0, 0), (1, 1), (2, 2), (3, 3), (2, 4), (1, 5), (0, 6)):
                c.rect(17 + ddx, 9 + dy + ddy, 18 + ddx, 9 + dy + ddy, core)
            if ch.projectile['glyph'].endswith('_'):
                c.rect(24, 15 + dy, 32, 16 + dy, core if k % 2 == 0 else hot)
            else:
                c.rect(25, 9 + dy, 26 + (k % 2), 16 + dy, core if k % 2 == 0 else hot)
            for j in (0, 1):
                c.px(13 + j * 24, 6 + dy + (k % 2) * 13, core)
            _trail(c, 12, cy + dy, ramp, k, n=5, spread=6)
        elif style == 'star':                                         # a four-point star that spins and pulses
            cx = 27
            rot_ = k * 22.5
            pulse = (0, 1, 0, -1)[k]
            _glow(c, lambda g: g.disc(cx, cy, 8 + pulse * 0.5, deep), k)
            for a in range(0, 360, 90):
                c.spike(cx, cy, a + rot_, 12 + pulse, 2.4, acc)
                c.spike(cx, cy, a + rot_, 10 + pulse, 1.3, hot)
            for a in range(45, 360, 90):
                c.spike(cx, cy, a + rot_, 6.5, 1.2, acc)
                c.spike(cx, cy, a + rot_, 4.5, 0.6, core)
            c.disc(cx, cy, 3.2, core)
            for j in range(4):
                a = math.radians(j * 90 + 45 - rot_ * 2)
                c.px(cx + 10.5 * math.cos(a), cy + 10.5 * math.sin(a), hot)
            _trail(c, cx - 11, cy, ramp, k, n=4, spread=5)
        else:                                                         # an orb with spinning arms and a halo
            cx = 29
            pulse = (0, 1, 0, 1)[k] * 0.6
            _glow(c, lambda g: g.disc(cx, cy, 11.5 + pulse, deep), k)
            _orb(c, cx, cy, 9 + pulse, ramp, phase=k * 1.1)
            for a in range(0, 360, 72):
                aa = math.radians(a + k * 20)
                c.px(cx + 11.3 * math.cos(aa), cy + 11.3 * math.sin(aa), hot)
            _trail(c, cx - 9, cy, ramp, k, n=5, spread=6)
        out.append((c.done(), 80))
    return dict(frames=out, anchor='hand', offset=(16, 0), loop=True, travel=dict(speed=160))


def fx_super_burst(pal):
    """A flash ring for the supers: the big-glyph power-up gets a real burst with a shimmering halo."""
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    out = []
    for k in range(4):
        c = Canvas(48, 48)
        cx = cy = 24
        r = 6 + k * 5.5
        _glow(c, lambda g: g.ring(cx, cy, r + 2.5, 3.5, deep), k)
        c.ring(cx, cy, r, 3 - k * 0.5, acc)
        c.ring(cx, cy, r - 1, 1.2, hot)
        for a in range(0, 360, 30):
            c.px(cx + (r + 2) * math.cos(math.radians(a + k * 10)), cy + (r + 2) * math.sin(math.radians(a + k * 10)), core if a % 60 else hot)
        if k == 0:
            c.disc(cx, cy, 4, core)
            for a in range(0, 360, 45):
                c.spike(cx, cy, a, 9, 1.0, hot, inner=4)
        out.append((c.done(), 60))
    return dict(frames=out, anchor='center', offset=(0, 0), layer='back', shake=dict(frames=3, amp=2), flash=True)


# ---- ultimates
def fx_radiant_beam(pal):
    """Frame 0 is the release flash (a white-hot muzzle burst and a core-only stub), 1 the beam reaching, 2-4 the full
    beam (each with its own ripple phase and noise), 5 the dying beam, 6 embers.  `grow` tells the engine to stretch
    the first 100 ms from the hands outward; `flash` marks frame 0 as the release flash."""
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    L, Hh = 128, 40
    cy, hw = Hh / 2, 9
    out = []
    for k in range(7):
        c = Canvas(L, Hh)
        if k == 0:
            beam(c, 6, L * 0.32, cy, hw * 0.75, (core, core, hot, acc), 0, seed=3, head=False, muzzle=False)
            _burst(c, 6 + hw * 0.4, cy, hw * 2.0, (core, core, hot, acc), 0, spikes=12, ring=False)
            c.disc(6 + hw * 0.4, cy, hw * 1.1, core)
        elif k == 1:
            beam(c, 6, L * 0.72, cy, hw, ramp, 1, seed=3)
        elif k <= 4:
            beam(c, 6, L - 10, cy, hw, ramp, k, seed=3)
            _burst(c, L - 13, cy, hw * (1.0 + 0.2 * (k - 2)), ramp, k, spikes=10)
        elif k == 5:
            beam(c, 6, L - 10, cy, hw * 0.8, ramp, k, seed=3, fade=True, muzzle=False, head=False)
            c.ring(L - 13, cy, hw * 1.5, 1.2, acc)
            c.ring(L - 13, cy, hw * 0.9, 0.8, hot)
        else:
            rng = random.Random(77)
            for j in range(26):
                x = rng.uniform(8, L - 4)
                c.px(x, cy + rng.uniform(-hw * 0.9, hw * 0.9), (acc, deep, hot)[j % 3])
            for a in range(0, 360, 45):
                c.px(L - 13 + hw * 1.9 * math.cos(math.radians(a)), cy + hw * 1.9 * math.sin(math.radians(a)), deep if a % 90 else acc)
        out.append((c.done(), (40, 60, 150, 150, 150, 110, 80)[k]))
    return dict(frames=out, anchor='hand', offset=(64, 0), hit_frame=2, shake=dict(frames=8, amp=3),
                grow=dict(from_w=28, to_w=L, ms=100), flash=True)


def fx_spiral_orb_core(pal):
    """The sphere forming in the hand: it spins, pulses, and the air around it is pulled in (converging motes)."""
    out = []
    ramp = _energy(pal)
    for k in range(4):
        c = Canvas(28, 28)
        r = 7 + (k % 2) * 0.6
        _glow(c, lambda g: g.disc(14, 14, r + 3, ramp[3]), k)
        _orb(c, 14, 14, r, ramp, phase=k * 1.3)
        for a in range(0, 360, 90):
            c.px(14 + (r + 2.5) * math.cos(math.radians(a + k * 25)), 14 + (r + 2.5) * math.sin(math.radians(a + k * 25)), ramp[1])
        _converge(c, 14, 14, r + 2, 13, ramp, k, 4, count=6, seed=5)
        out.append((c.done(), 60))
    return dict(frames=out, anchor='center', offset=(0, 0), loop=True)


def fx_spiral_orb_burst(pal):
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    out = []
    for k in range(6):
        c = Canvas(56, 56)
        cx = cy = 28
        R = 6 + k * 4.2
        if k == 0:                                                    # release flash
            c.disc(cx, cy, R * 1.6, core)
            for a in range(0, 360, 30):
                c.spike(cx, cy, a, R * 3.2, 1.0, hot, inner=R * 1.4)
        _glow(c, lambda g: g.disc(cx, cy, R * 1.25, deep), k)
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
        out.append((c.done(), (50, 60, 70, 80, 90, 100)[k]))
    return dict(frames=out, anchor='hand', offset=(10, 0), hit_frame=1, shake=dict(frames=6, amp=3), flash=True)


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


def fx_mirror_images(ch, hands):
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


def fx_crescent_fang_charge(pal):
    """Energy gathering on the raised fist: black-edged licks, a growing core, motes converging."""
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    ink = INK
    out = []
    for k in range(4):
        c = Canvas(30, 30)
        cx = cy = 15
        _glow(c, lambda g: g.disc(cx, cy, 6 + k * 1.5, deep), k)
        for a in range(0, 360, 60):
            c.spike(cx, cy, a + k * 20, 11 + (k % 2), 1.3, ink, inner=5)
            c.spike(cx, cy, a + k * 20, 9 + (k % 2), 0.7, acc, inner=5)
        _orb(c, cx, cy, 3 + k * 1.2, (core, acc, deep, ink), phase=k, spin=False)
        _converge(c, cx, cy, 5 + k, 14, ramp, k, 4, count=7, seed=9)
        out.append((c.done(), (200, 220, 240, 180)[k]))
    return dict(frames=out, anchor='center', offset=(0, 0))


def fx_crescent_fang(pal):
    """The crescent slash wave: dithered halo, ink edge, deep / accent / pale / white-hot bands that ripple along the
    arc, ragged licks off the leading edge, a trail of streaks behind.  Four looping frames, none alike."""
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    pale = pal['fx']['c']
    out = []
    for k in range(4):
        c = Canvas(60, 64)
        cx, cy = 18, 32
        a0, a1 = -74, 74
        _glow(c, lambda g: _wavy_band(g, cx, cy, 19, 29, a0 - 4, a1 + 4, deep, k, amp=1.0), k)
        for (r0, r1, col) in ((19.5, 27.5, INK), (20.0, 26.5, deep), (20.5, 25.0, acc), (21.2, 23.6, pale), (21.8, 22.8, core)):
            _wavy_band(c, cx, cy, r0, r1, a0, a1, col, k, amp=0.8 if col in (INK, deep) else 0.5)
        for j in range(7):                                            # ragged energy flares off the outer edge
            a = math.radians(a0 + (a1 - a0) * (j + 0.5) / 7)
            Ln = 4 + ((j + k) % 3) * 2.5
            px_, py_ = cx + 27 * math.cos(a), cy + 27 * math.sin(a)
            c.spike(px_, py_, math.degrees(a), Ln, 1.4, INK)
            c.spike(px_, py_, math.degrees(a), Ln * 0.75, 0.7, acc if j % 2 else hot)
        for j in range(4):                                            # white-hot sparks dancing on the core
            a = math.radians(a0 + 12 + (a1 - a0 - 24) * ((j * 3 + k) % 4) / 3.0)
            c.px(cx + 22.3 * math.cos(a), cy + 22.3 * math.sin(a), core)
        for j in range(5):                                            # trailing streaks behind the wave
            yy = cy - 16 + j * 8
            ln = 5 + ((k + j) % 3) * 3
            x1 = cx + 1 + 18 * abs(math.cos(math.radians(a0 + (a1 - a0) * j / 4)))
            c.line((x1 - ln, yy), (x1, yy), (deep, acc, hot)[j % 3], 1)
        out.append((c.done(), 70))
    return dict(frames=out, anchor='center', offset=(20, 0), loop=True, travel=dict(speed=260), hit_frame=0)


def fx_crescent_fang_impact(pal):
    fr = fx_impact(pal, 40, 5)
    return dict(frames=fr, anchor='center', offset=(0, 0), hit_frame=1, shake=dict(frames=5, amp=3), flash=True)


def fx_grapple_lines(pal):
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
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
            if k == 0:                                                # gas burst at the launchers
                for a in (150, 180, 210):
                    c.spike(2, y0, a + j * 10, 5, 1.0, G2, inner=1)
                c.px(1, y0, core)
        for j in range(0, int(reach), 12):                            # gas puffs along the line
            c.px(j + (k * 3) % 12, 12, G2)
        out.append((c.done(), (50, 50, 100, 100)[k]))
    return dict(frames=out, anchor='hand', offset=(50, 2), layer='back')


def fx_grapple_slash(pal):
    """The spinning cross slash: two blades drawn as layered energy with a halo, a flash ring on contact, embers."""
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    out = []
    for k in range(4):
        c = Canvas(52, 52)
        cx = cy = 26
        L = (13, 22, 24, 24)[k]
        if k < 3:
            _glow(c, lambda g: [g.spike(cx, cy, a + k * 8, L + 3, 3.6, deep, inner=0) for a in (45, 135, 225, 315)], k)
        for a in (45, 135, 225, 315):
            a_ = a + k * 8
            if k < 3:
                c.spike(cx, cy, a_, L, 2.6, deep, inner=0)
                c.spike(cx, cy, a_, L - 1, 1.6, acc, inner=0)
                c.spike(cx, cy, a_, L - 3, 0.8, core, inner=0)
                for j in (0.45, 0.75):                                 # licks off the blade edges
                    px_, py_ = cx + L * j * math.cos(math.radians(a_)), cy + L * j * math.sin(math.radians(a_))
                    c.spike(px_, py_, a_ + 60, 3 + k, 0.7, hot)
            else:
                c.spike(cx, cy, a_, L, 0.8, acc, inner=L - 6)
        if k == 0:
            c.disc(cx, cy, 6, core)
        if k == 1:
            c.disc(cx, cy, 4, core)
            for a in range(0, 360, 45):
                c.arc_band(cx, cy, 16, 18.5, a - 8, a + 8, hot)
        if k == 2:
            c.ring(cx, cy, 21, 1.2, acc)
            for a in range(0, 360, 60):
                c.px(cx + 23 * math.cos(math.radians(a + 20)), cy + 23 * math.sin(math.radians(a + 20)), hot)
        out.append((c.done(), (50, 80, 80, 70)[k]))
    return dict(frames=out, anchor='center', offset=(10, 0), hit_frame=1, shake=dict(frames=4, amp=2), flash=True)


def fx_gale_rend(pal):
    """Three claws of energy ripping along the ground: each a layered column (halo, deep, accent, hot, white core) with
    rippling edges, licks off the tips, dirt and stone thrown up, and a burst at the leading claw once it bites."""
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    Wd, Hh = 104, 56
    out = []
    for k in range(5):
        c = Canvas(Wd, Hh)
        base = Hh - 3
        claws = []
        for j in range(3):                                            # three claws, tallest in the middle
            x = 14 + j * 31 + (k % 2) * 2
            h = (34, 46, 38)[j] * (0.5 + 0.5 * min(1.0, k / 2.0))
            lean = 8
            claws.append((x, h, lean))

        def claw(cv, x, h, lean, wid, col, ph):
            pts = []
            for s in range(8):                                        # left edge up, rippling
                t = s / 7.0
                w = wid * (1.0 - 0.8 * t) + 0.8 * math.sin(t * 9 + k * 1.5 + ph)
                pts.append((x - w + lean * 1.6 * t, base - h * t))
            for s in range(7, -1, -1):
                t = s / 7.0
                w = wid * (1.0 - 0.8 * t) + 0.8 * math.sin(t * 9 + k * 1.5 + ph + 2)
                pts.append((x + w + lean * 1.6 * t, base - h * t))
            cv.poly(pts, col)
        for x, h, lean in claws:
            _glow(c, lambda g, x=x, h=h, lean=lean: claw(g, x, h + 3, lean, 12, deep, 0.0), k)
        for x, h, lean in claws:
            for (wid, col) in ((9, deep), (7, acc), (4.6, hot), (2.2, core)):
                claw(c, x, h, lean, wid, col, 0.0)
            tipx, tipy = x + lean * 1.6, base - h
            for s in range(4):                                        # licks off the tip
                a = -90 + (s - 1.5) * 28 + k * 9
                c.spike(tipx, tipy + 2, a, 4 + ((s + k) % 3) * 2, 0.9, hot if s % 2 else acc, inner=1)
            for s in range(3):
                c.px(tipx + s * 2 - 2, tipy - 2 - (s % 2) * 2 - k, hot if s % 2 else core)
        if k >= 2:                                                    # the leading claw bites: a burst at its foot
            x, h, lean = claws[2]
            _burst(c, x + 8, base - 6, 5 + k, ramp, k, spikes=8)
        for x in range(0, Wd, 6):                                     # ripped ground: dirt and stone
            c.rect(x + (k * 2) % 6, base - 1 + (x // 6) % 2, x + 3 + (k * 2) % 6, base + 1, G3 if x % 12 else G2)
            if k >= 1:
                c.px(x + 2 + (k * 2) % 6, base - 3 - (x // 6) % 3 - k, G1 if x % 12 else G2)
        out.append((c.done(), (60, 70, 70, 70, 70)[k]))
    return dict(frames=out, anchor='ground', offset=(38, -Hh // 2 + 2), loop=True, travel=dict(speed=240), hit_frame=1,
                shake=dict(frames=6, amp=3))


def fx_gale_rend_impact(pal):
    fr = _explosion(56, (W_, pal['fx']['b'], pal['fx']['a'], EMB, SMK), 7)
    return dict(frames=fr, anchor='center', offset=(0, 4), hit_frame=1, shake=dict(frames=6, amp=4), flash=True)


def fx_awakening_aura(pal):
    """The pillar of aura: frame 0 is the release flash, then the pillar climbs as layered flame (halo, deep, accent,
    teal, hot, white core) with rippling edges and rising streaks, then it breaks into drifting motes."""
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    teal = pal['fx']['c']
    out = []
    Wd, Hh = 60, 100
    for k in range(6):
        c = Canvas(Wd, Hh)
        cx, base = Wd / 2, Hh - 4
        if k == 0:
            c.ring(cx, base - 2, 16, 3.0, core)
            c.ring(cx, base - 2, 12, 1.5, hot)
            c.disc(cx, base - 10, 9, core)
            for a in range(0, 360, 30):
                c.spike(cx, base - 10, a, 18, 1.0, hot, inner=9)
        elif k <= 3:
            h = Hh * (0.5, 0.95, 1.0)[k - 1]
            top = base - h

            def flame(cv, hw, col, wob, ph=0.0):
                # each band ripples with its own phase and frequency, so the layers slide against each other like
                # flame instead of stacking into stripes; the tip leans with the phase too
                pts = []
                for yy in range(int(top), int(base) + 1, 3):
                    t = (yy - top) / max(1.0, h)
                    w = hw * (0.55 + 0.45 * t) + wob * math.sin(yy * (0.3 + 0.05 * ph) + k * 1.1 + ph) + 0.4 * wob * math.sin(yy * 0.9 - k + ph)
                    pts.append((cx - w, yy))
                for yy in range(int(base), int(top) - 1, -3):
                    t = (yy - top) / max(1.0, h)
                    w = hw * (0.55 + 0.45 * t) + wob * math.sin(yy * (0.3 + 0.05 * ph) + k * 1.1 + 2 + ph) + 0.4 * wob * math.sin(yy * 0.9 + k - ph)
                    pts.append((cx + w, yy))
                tip = 3 * math.sin(k * 1.3 + ph)
                pts.insert(0, (cx - 2 + tip, top - 4 - (hw % 3)))    # the pillar tapers to a flame tip
                pts.append((cx + 2 + tip, top - 4 - (hw % 3)))
                cv.poly(pts, col)
            _glow(c, lambda g: flame(g, 28, deep, 1.2, 0.0), k)
            for j, (hw, col) in enumerate(((24, deep), (20, acc), (15, teal), (9, hot), (4, core))):
                flame(c, hw, col, (1.4, 1.6, 1.8, 1.4, 0.8)[j], ph=j * 1.9)
            rng = random.Random(k + 40)
            for j in range(10):                                       # rising streaks inside the flame
                xx = cx - 16 + j * 3.6
                y0 = base - (j * 13 + k * 17) % int(h)
                c.line((xx, y0), (xx, y0 - 4 - rng.randint(0, 4)), core if j % 2 else hot, 1)
            for j in range(6):                                        # licks off the edges
                side = -1 if j % 2 else 1
                yy = base - (j * 17 + k * 11) % int(h) - 6
                t = (yy - top) / max(1.0, h)
                w = 24 * (0.55 + 0.45 * t)
                c.spike(cx + side * w, yy, -90 + side * 40 + k * 10, 5 + (j % 3) * 2, 1.0, acc if j % 3 else hot)
            c.ring(cx, base - 2, 16 + k * 2, 1.5, acc)
        else:
            for j in range(12):
                xx = cx - 22 + j * 4.0
                y0 = base - (j * 17 + k * 23) % (Hh - 10)
                c.line((xx, y0), (xx, y0 - 4), teal if j % 2 else acc, 1)
                c.px(xx + 1, y0 - 7 - (j % 3), hot if j % 3 else core)
            if k == 4:
                c.ring(cx, base - 2, 22, 1.2, acc)
        out.append((c.done(), (60, 70, 90, 120, 90, 90)[k]))
    return dict(frames=out, anchor='ground', offset=(0, -Hh // 2 + 4), layer='back', hit_frame=2, shake=dict(frames=6, amp=3),
                grow=dict(from_w=Wd // 2, to_w=Wd, ms=120), flash=True)


def fx_awakening_slash(pal):
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    teal = pal['fx']['c']
    out = []
    for k in range(3):
        c = Canvas(44, 44)
        _glow(c, lambda g: [g.spike(22 + (j - 1) * 5, 22 + (j - 1) * 3, -35 + j * 30 + k * 10, 20 - j * 2, 3.2, deep) for j in range(3)], k)
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


def fx_star_core_orb(pal):
    """The ball gathering overhead: it grows, spins, pulses, and sparkles stream in from all round."""
    out = []
    ramp = _energy(pal)
    for k in range(4):
        c = Canvas(48, 48)
        r = 5 + k * 4
        _glow(c, lambda g: g.disc(24, 24, r + 3 + (k % 2), ramp[3]), k)
        _orb(c, 24, 24, r, ramp, phase=k * 0.8, spin=k >= 1)
        _converge(c, 24, 24, r + 2, 23, ramp, k, 4, count=9 + k * 2, seed=7)
        out.append((c.done(), (240, 260, 300, 300)[k]))
    return dict(frames=out, anchor='center', offset=(2, -34))


def fx_star_core(pal):
    """The thrown ball: a big spinning orb with a shimmering halo, pulsing, its spin arms turning, a trail behind."""
    out = []
    ramp = _energy(pal)
    core, hot, acc, deep = ramp
    for k in range(4):
        c = Canvas(56, 48)
        cx, cy = 32, 24
        pulse = (0, 0.7, 0, -0.5)[k]
        _glow(c, lambda g: g.disc(cx, cy, 21 + pulse, deep), k)
        _orb(c, cx, cy, 17 + pulse, ramp, phase=k * 0.9)
        for a in range(0, 360, 30):
            c.px(cx + (20 + pulse) * math.cos(math.radians(a + k * 8)), cy + (20 + pulse) * math.sin(math.radians(a + k * 8)), core if a % 60 else hot)
        for j in range(4):                                            # arcs of energy skimming the surface
            a0 = j * 90 + k * 25
            c.arc_band(cx, cy, 13.5, 14.5, a0, a0 + 35, core if j % 2 else hot)
        _trail(c, cx - 19, cy, ramp, k, n=6, spread=10, step=4)
        out.append((c.done(), 90))
    return dict(frames=out, anchor='center', offset=(24, -10), loop=True, travel=dict(speed=150), hit_frame=0)


def fx_star_core_impact(pal):
    fr = _explosion(64, (W_, pal['fx']['b'], pal['fx']['a'], EMB, SMK), 7)
    return dict(frames=fr, anchor='center', offset=(0, 0), hit_frame=1, shake=dict(frames=8, amp=5), flash=True)


ULT_FX = {
    'radiant_beam': lambda ch, h: {'radiant_beam_charge': dict(frames=fx_charge(ch.body.palette, 28, 5, (200, 220, 240, 260, 280), 8),
                                                           anchor='center', offset=_hand_off(h, 'radiant_beam', 2, 'hb')),
                                 'radiant_beam': fx_radiant_beam(ch.body.palette)},
    'spiral_orb': lambda ch, h: {'spiral_orb_core': dict(fx_spiral_orb_core(ch.body.palette), offset=_hand_off(h, 'spiral_orb', 1, 'hf', (1, -5))),
                               'spiral_orb_burst': fx_spiral_orb_burst(ch.body.palette),
                               'clone_poof': fx_clone_poof(), 'mirror_images': fx_mirror_images(ch, h)},
    'crescent_fang': lambda ch, h: {'crescent_fang_charge': dict(fx_crescent_fang_charge(ch.body.palette), offset=_hand_off(h, 'crescent_fang', 1, 'hf', (0, -4))),
                              'crescent_fang': fx_crescent_fang(ch.body.palette), 'crescent_fang_impact': fx_crescent_fang_impact(ch.body.palette)},
    'grapple_strike': lambda ch, h: {'grapple_lines': fx_grapple_lines(ch.body.palette), 'grapple_slash': fx_grapple_slash(ch.body.palette)},
    'gale_rend': lambda ch, h: {'gale_rend_charge': dict(frames=fx_charge(ch.body.palette, 32, 4, (200, 220, 240, 240), 9),
                                                         anchor='center', offset=_hand_off(h, 'gale_rend', 1, 'hf', (0, -5))),
                                'gale_rend': fx_gale_rend(ch.body.palette), 'gale_rend_impact': fx_gale_rend_impact(ch.body.palette)},
    'awakening': lambda ch, h: {'awakening_aura': fx_awakening_aura(ch.body.palette), 'awakening_slash': fx_awakening_slash(ch.body.palette)},
    'star_core': lambda ch, h: {'star_core_orb': fx_star_core_orb(ch.body.palette), 'star_core': fx_star_core(ch.body.palette),
                                  'star_core_impact': fx_star_core_impact(ch.body.palette)},
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
FX_SCHEMA_NOTES = {                              # V5.1 keys (every effect carries them; older engines ignore them)
    'grow': 'optional {from_w, to_w, ms} (px at this res): the engine draws the effect stretched horizontally from from_w to '
            'to_w over its first ms after spawn, the anchored end fixed, so a beam extends from the hands instead of '
            'appearing whole; null = draw the frames as authored.',
    'flash': 'bool: frame 0 is a one-frame release flash (white-hot); the engine may whiten the owner sprite / flash the '
             'scene for that frame\'s ms.  Never true on a looping effect.',
    'impact': 'V6 effect id (every character sheet): the 2D impact-frame sequence for a heavy hit (power 3) or an ultimate\'s '
              'contact - dark silhouette with white rays and rim, the white inverse with speed lines, outline strokes, a '
              'white silhouette (40/40/40/30 ms, one cell each, transparent outside the figure - never an opaque box).  '
              'Play it once on the contact frame, never on light hits.',
}


def _scale_meta(e):
    """Design-unit placement -> px at this RES; exact schema keys only."""
    S = rig.RES
    off = e.get('offset', (0, 0))
    grow = e.get('grow')
    return dict(anchor=e.get('anchor', 'center'), offset=[int(off[0]) * S, int(off[1]) * S], loop=bool(e.get('loop', False)),
                layer=e.get('layer', 'front'), hit_frame=e.get('hit_frame'),
                travel=(dict(speed=int(e['travel']['speed']) * S) if e.get('travel') else None),
                shake=(dict(frames=int(e['shake']['frames']), amp=int(e['shake']['amp']) * S) if e.get('shake') else None),
                grow=(dict(from_w=int(grow['from_w']) * S, to_w=int(grow['to_w']) * S, ms=int(grow['ms'])) if grow else None),
                flash=bool(e.get('flash', False)))


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
    meta = {'res': res, 'sheet': sheet_name, 'schema_notes': dict(FX_SCHEMA_NOTES), 'effects': {}}
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
    """Generic set + this character's upgraded special / super effects + its ultimate effects + its impact frames.

    The ultimate's effects come from its TEMPLATE (ch.sig_moves[ult][0]); a character whose ultimate move has another
    name (the V6 extras reuse the seven templates) also gets the main effect under its own move name."""
    pal = ch.body.palette
    eff = generic_effects()
    special, sup, ult = ch.signature['special'], ch.signature['super'], ch.signature.get('ultimate')
    eff[f'{special}_proj'] = fx_big_proj(ch)
    eff[f'{special}_impact'] = dict(frames=fx_impact(pal, 28, 5), anchor='center', offset=(0, 0), hit_frame=1, shake=dict(frames=2, amp=1))
    eff[f'{sup}_burst'] = fx_super_burst(pal)
    tpl = ch.sig_moves[ult][0] if ult and ult in ch.sig_moves else ult
    if tpl and tpl in ULT_FX:
        h = dict(hands or {})
        if tpl != ult:                                  # the template's hand lookups use the template's move name
            for (name, i), m in list(h.items()):
                if name == ult:
                    h[(tpl, i)] = m
        h['_name'] = ch.name
        eff.update(ULT_FX[tpl](ch, h))
        if tpl != ult:
            main = tpl if tpl in eff else ULT_ALIASES.get(tpl)
            eff[ult] = dict(eff[main])
    eff['impact'] = fx_impact_frames(ch)
    return eff


def fx_impact_frames(ch):
    """The 2D impact-frame sequence for heavy hits and ultimates (docs/ANIMATION-NOTES.md section 6): the fighter's
    ultimate contact pose as a dark silhouette with white radial lines and a white rim, the white inverse with longer,
    chaotic speed lines, broken outline strokes, then a white silhouette; transparent outside the figure.  One cell per frame,
    centred on the `center` anchor; 40 / 40 / 40 / 30 ms."""
    import moves
    S = rig.RES
    cw = rig.cell_px()
    ult = ch.signature.get('ultimate')
    mv = moves.build_moves(ch)[ult]
    pose = mv['frames'][mv.get('hit_frame', len(mv['frames']) - 2)][0]
    from dataclasses import replace
    pose = replace(pose, fx=(), ghost=(), flash=False, aura=0)
    buf, _ = rig.render_parts(ch.body, pose, None)
    bp = buf.load()
    sil = Image.new('L', (cw, cw), 0)
    sp = sil.load()
    xs, ys = [], []
    for y in range(cw):
        for x in range(cw):
            n = bp[x, y]
            if n and rig.NAME[n] not in rig.NOLINE:
                sp[x, y] = 255
                xs.append(x)
                ys.append(y)
    cx, cy = (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else (cw / 2, cw / 2)
    rng = random.Random(sum(map(ord, ch.name)))

    def rays(d, n, r0, r1, jitter, width, col):
        for k in range(n):
            a = 2 * math.pi * k / n + rng.uniform(-jitter, jitter)
            ra, rb = r0 * rng.uniform(0.6, 1.0), r1 * rng.uniform(0.7, 1.15)
            d.line([(cx + math.cos(a) * ra, cy + math.sin(a) * ra), (cx + math.cos(a) * rb, cy + math.sin(a) * rb)], fill=col, width=width)

    white, black = W_ + (255,), INK + (255,)
    out = []
    # 1: silhouette on white, radial white lines clipped inside it
    f = Image.new('RGBA', (cw, cw), white)
    f.paste(black, (0, 0), sil)
    lines = Image.new('L', (cw, cw), 0)
    rays(ImageDraw.Draw(lines), 14, 2 * S, 30 * S, 0.08, S, 255)
    lp = lines.load()
    fp = f.load()
    for y in range(cw):
        for x in range(cw):
            if lp[x, y] and sp[x, y]:
                fp[x, y] = white
    out.append((f, 40))
    # 2: inverse, longer chaotic lines across the whole frame
    f = Image.new('RGBA', (cw, cw), black)
    f.paste(white, (0, 0), sil)
    lines = Image.new('L', (cw, cw), 0)
    rays(ImageDraw.Draw(lines), 22, 6 * S, 46 * S, 0.25, S, 255)
    lp, fp = lines.load(), f.load()
    for y in range(cw):
        for x in range(cw):
            if lp[x, y]:
                fp[x, y] = black if sp[x, y] else white
    out.append((f, 40))
    # 3: short broken outline strokes on white
    f = Image.new('RGBA', (cw, cw), white)
    fp = f.load()
    for y in range(1, cw - 1):
        for x in range(1, cw - 1):
            if sp[x, y] and not (sp[x - 1, y] and sp[x + 1, y] and sp[x, y - 1] and sp[x, y + 1]):
                if ((x // S) * 3 + (y // S) * 5) % 7 < 4:
                    fp[x, y] = black
    out.append((f, 40))
    # 4: a white silhouette (a full blank cell drew an opaque white box over the taskbar)
    f = Image.new('RGBA', (cw, cw), (0, 0, 0, 0))
    f.paste(white, (0, 0), sil)
    out.append((f, 30))
    # Owner saw the opaque cells as a glitch box on the live strip: keep only the silhouette, a thin rim and the
    # radial lines; everything else is transparent.
    from PIL import ImageFilter
    rim = sil.filter(ImageFilter.MaxFilter(2 * S + 1)).load()
    for i, (f, ms) in enumerate(out[:3]):
        fp = f.load()
        for y in range(cw):
            for x in range(cw):
                if not rim[x, y] and not (i == 1 and fp[x, y] == white):     # frame 2 keeps its white speed lines
                    fp[x, y] = (0, 0, 0, 0)
    off = (rig.W // 2 - rig.HIP_X, rig.W // 2 - (rig.GROUND - CENTER_DY))
    return dict(frames=out, anchor='center', offset=off, hit_frame=0, layer='front')


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
