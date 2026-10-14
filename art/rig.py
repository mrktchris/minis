"""Pixel-fighter rig: pose data -> part-id buffer -> shaded, outlined RGBA frame.

Pipeline (mirrors the pro workflow from the references):
  structure  = parts drawn as flat part-ids (this module: render_parts)
  lines+shade = edge-based 3-tone shading + selective outline (finish)
Everything is deterministic and palette-limited.  Fighters face RIGHT; the left-facing
version is the mirrored part buffer with the cap sigil redrawn un-mirrored.

Resolution (V4): every pose, body and glyph is authored in DESIGN units (the 64 px cell).  `set_res(k)` renders the
same data into a k*64 px cell: all dims, offsets, glyph pixels and effects scale by k, and the finish pass widens its
shading bands and outline to k px and adds one rim tone (`hi2`).  RES 1 is byte-identical to the V3 output.
`W`, `H`, `GROUND`, `HIP_X`, `ANKLE_Y` stay design constants; `cell_px()`, `ground_px()`, `hip_x_px()` give pixels.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, replace, field
from PIL import Image, ImageDraw

W = H = 64             # design cell
GROUND = 57            # lowest body row of a planted foot (design)
HIP_X = 30             # hip column in the cell (facing right, design)
ANKLE_Y = GROUND - 2
RES = 1                # resolution factor: 1 = 64 px cell, 2 = 128 px cell


def set_res(k):
    """Render at k x the design resolution (1 or 2).  Affects every render/finish call after it."""
    global RES
    k = int(k)
    if k < 1:
        raise ValueError('RES must be >= 1')
    RES = k


def cell_px():
    return W * RES


def ground_px():
    """Lowest body row of a planted foot, in pixels at the current RES."""
    return GROUND * RES


def hip_x_px():
    return HIP_X * RES


PART_ORDER = ['scarf_b', 'scarf_a', 'hood', 'leg_b_th', 'leg_b_sh', 'shoe_b', 'sole_b',
              'torso', 'belt', 'arm_b_up', 'arm_b_fo', 'cuff_b', 'hand_b',
              'leg_f_th', 'leg_f_sh', 'shoe_f', 'sole_f',
              'head', 'ear', 'hair', 'cap', 'visor', 'strap', 'sigil',
              'eye', 'brow', 'mouth',
              'arm_f_up', 'arm_f_fo', 'cuff_f', 'hand_f',
              'doc', 'doc_line', 'fx_a', 'fx_b', 'fx_w', 'fx_c']
PID = {n: i + 1 for i, n in enumerate(PART_ORDER)}
NAME = {v: k for k, v in PID.items()}
Z = {PID[n]: i for i, n in enumerate(PART_ORDER)}

GROUP = {'head': 'skin', 'hand_b': 'skin', 'hand_f': 'skin', 'hair': 'hair',
         'torso': 'cloth', 'arm_b_up': 'cloth', 'arm_b_fo': 'cloth', 'arm_f_up': 'cloth', 'arm_f_fo': 'cloth',
         'hood': 'cloth', 'cap': 'cloth', 'visor': 'cloth', 'scarf_b': 'cloth',
         'cuff_b': 'trim', 'cuff_f': 'trim', 'strap': 'trim', 'belt': 'trim', 'scarf_a': 'trim',
         'leg_b_th': 'pants', 'leg_b_sh': 'pants', 'leg_f_th': 'pants', 'leg_f_sh': 'pants',
         'shoe_b': 'shoe', 'shoe_f': 'shoe', 'sole_b': 'sole', 'sole_f': 'sole'}
DARK = {'leg_b_th', 'leg_b_sh', 'shoe_b', 'sole_b', 'arm_b_up', 'arm_b_fo', 'cuff_b', 'hand_b'}   # far-side limbs
FLAT = {'ear': ('skin', 'sh'), 'eye': ('ink', None), 'brow': ('ink', None), 'mouth': ('ink', None),
        'sigil': ('trim', 'hi'), 'doc': ('paper', None), 'doc_line': ('paper', 'sh'),
        'fx_a': ('fx', 'a'), 'fx_b': ('fx', 'b'), 'fx_w': ('fx', 'w'), 'fx_c': ('fx', 'c')}
NOLINE = {'fx_a', 'fx_b', 'fx_w', 'fx_c'}
TEXT_FX = ('bigsigil', 'bigglyph', 'qmark', 'zzz')   # effects that are letters: never mirrored on left-facing frames
RIM_GROUPS = ('skin', 'hair', 'cloth', 'trim', 'pants', 'shoe')   # groups that get the HD rim tone `hi2`

GLYPH = {'/': ["..#", "..#", ".#.", "#..", "#.."],
         '$': [".##", "##.", ".#.", ".##", "##."],
         '*': ["#.#", ".#.", "###", ".#.", "#.#"],
         '>': ["#..", ".#.", "..#", ".#.", "#.."],
         'o': [".#.", "#.#", "#.#", "#.#", ".#."],
         'L': ["#..", "#..", "#..", "#..", "###"],
         '+': [".#.", ".#.", "###", ".#.", ".#."]}
ZGLYPH = ["####", "..#.", ".#..", "####"]          # the sleep 'z': a real diagonal, so it never reads as 'I'


def hexrgb(s):
    s = s.lstrip('#')
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def mix(c0, c1, k):
    return tuple(int(round(a + (b - a) * k)) for a, b in zip(c0, c1))


def rim_tone(grp):
    """The HD-only fourth tone of a group: its highlight pushed toward white."""
    return grp.get('hi2') or mix(grp['hi'], (255, 255, 255), 0.45)


@dataclass(frozen=True)
class Body:
    name: str
    thigh: float
    shin: float
    torso: float
    torso_w: float
    upper: float
    fore: float
    limb: int
    head_w: int
    head_h: int
    foot_len: int
    sigil: str
    scarf: bool
    hood: bool
    palette: dict          # group -> dict(base, hi, sh, ol)
    skin_tone_note: str = ''
    ponytail: bool = False             # a hair tail simulated like the scarf (drawn in the hair group)
    tail_anchor: tuple = (-5.0, 4.5)   # head-local attach point of scarf / ponytail
    tail_seg: tuple = (4, 2.4)         # (segments, segment length px)
    ghost_group: str = 'trim'          # afterimage tint
    ghost_style: str = 'dither'        # 'dither' = checker copies in the ghost group; 'holo' = neon scanline copies (cyber look)

    @property
    def hip_y0(self):
        return ANKLE_Y - (self.thigh + self.shin) + 1

    @property
    def has_tail(self):
        return self.scarf or self.ponytail

    @property
    def lie_dy(self):
        """Hip drop when lying flat: puts the hips on the same row (51) for every leg length."""
        return (self.thigh + self.shin) - 5

    @property
    def sit_dy(self):
        """Hip drop when sitting: the same hip height above the floor for every leg length."""
        return (self.thigh + self.shin) - 1


def group_of(body, nm):
    if body.ponytail and nm in ('scarf_a', 'scarf_b'):
        return 'hair'
    return GROUP[nm]


def _g(base, hi, sh, ol):
    return dict(base=hexrgb(base), hi=hexrgb(hi), sh=hexrgb(sh), ol=hexrgb(ol))


CLAUDE = Body('claude', thigh=8, shin=8, torso=12, torso_w=10, upper=6, fore=6, limb=3, head_w=13, head_h=13,
              foot_len=6, sigil='/', scarf=True, hood=False, ghost_group='cloth', palette={
    'skin': _g('E9B88F', 'F6D6B6', 'C48A66', '7A4A34'),
    'hair': _g('2B2420', '4A3E36', '1A1512', '100C0A'),
    'cloth': _g('D97757', 'F0A184', 'A8553C', '5E2C1E'),
    'trim': _g('F0EEE6', 'FFFFFF', 'C7C2B3', '7D7766'),
    'pants': _g('2E2B38', '45414F', '1E1C26', '121118'),
    'shoe': _g('F0EEE6', 'FFFFFF', 'C7C2B3', '7D7766'),
    'sole': _g('1F1E1D', '45414F', '1F1E1D', '121118'),
    'ink': _g('1F1E1D', '1F1E1D', '1F1E1D', '1F1E1D'),
    'paper': _g('F4F4F2', 'FFFFFF', 'A9A9B4', '4A4A55'),
    'fx': dict(a=hexrgb('FF9C2C'), b=hexrgb('FFE27A'), w=hexrgb('FFFFFF'), c=hexrgb('F0A184')),
    'flash': dict(fill=hexrgb('FFFFFF'), ol=hexrgb('B8BCD0')),
})

CODEX = Body('codex', thigh=7, shin=7, torso=12, torso_w=13, upper=5.5, fore=5.5, limb=4, head_w=13, head_h=13,
             foot_len=7, sigil='$', scarf=False, hood=True, palette={
    'skin': _g('BB7A50', 'D79E74', '8F5736', '4C2A1B'),
    'hair': _g('17130F', '2E2620', '0D0A08', '070504'),
    'cloth': _g('24242E', '3A3A4A', '15151C', '08080C'),
    'trim': _g('7C6CFF', 'A99DFF', '5648D6', '2A2270'),
    'pants': _g('3A3A47', '52525F', '26262F', '111117'),
    'shoe': _g('F4F4F8', 'FFFFFF', 'B7B8C9', '5C5D70'),
    'sole': _g('5648D6', '7C6CFF', '5648D6', '2A2270'),
    'ink': _g('0B0B10', '0B0B10', '0B0B10', '0B0B10'),
    'paper': _g('F4F4F2', 'FFFFFF', 'A9A9B4', '4A4A55'),
    'fx': dict(a=hexrgb('9B6BFF'), b=hexrgb('FFE27A'), w=hexrgb('FFFFFF'), c=hexrgb('A99DFF')),
    'flash': dict(fill=hexrgb('FFFFFF'), ol=hexrgb('B8BCD0')),
})


@dataclass(frozen=True)
class Pose:
    dx: float = 0           # world root motion this frame (px, +forward)
    cx: float = 0           # in-cell shift of the whole body
    dy: float = 1           # hips lower by dy (negative = up)
    lean: float = 10        # torso lean, degrees, + = forward
    head: tuple = (1, 0)
    tilt: float = 0
    hf: tuple = (8, -1)     # front hand target, relative to the front shoulder
    hb: tuple = (4, 1)
    ff: tuple = (7, 0)      # front foot: (x from hip, lift above ground)
    fb: tuple = (-6, 0)
    eb_f: str = 'down'
    eb_b: str = 'down'
    kb_f: str = 'fwd'
    kb_b: str = 'fwd'
    face: str = 'f'
    fist_f: int = 3
    fist_b: int = 3
    open_f: bool = False
    turn: float = 1.0       # torso width scale (spin)
    fx: tuple = ()
    flash: bool = False
    aura: int = 0
    ang_f: float = 0        # foot angle, degrees
    ang_b: float = 0
    doc: str = ''           # '' | 'hf' | 'hb': which hand holds the diff
    ghost: tuple = ()       # afterimage: distances (design px) of each trailing copy back along the motion, nearest first
    # ---- V5 (fluid pass)
    sq: float = 1.0         # squash / stretch: torso length and head height scale by sq, head width by 1/sqrt(sq)
    chest: float = 1.0      # torso width scale on top of `turn` (inhale on idle, puff on a power-up)
    smear_f: tuple = ()     # (x, y) the front hand's PREVIOUS target: this frame the forearm is drawn as the arc it swept
    smear_b: tuple = ()     # same for the back hand
    smear_ff: tuple = ()    # previous (x, lift) target of the front foot: the shin is drawn as the kick's arc
    smear_fb: tuple = ()    # same for the back foot


# ---------------------------------------------------------------- geometry helpers
def ik2(a, t, l1, l2, bend, maxy=None):
    dx, dy = t[0] - a[0], t[1] - a[1]
    d = max(1e-6, math.hypot(dx, dy))
    reach = l1 + l2 - 0.05 * RES
    if d > reach:
        k = reach / d
        dx, dy, d = dx * k, dy * k, reach
    ca = max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)))
    ang = math.acos(ca)
    base = math.atan2(dy, dx)
    e1 = (a[0] + l1 * math.cos(base + ang), a[1] + l1 * math.sin(base + ang))
    e2 = (a[0] + l1 * math.cos(base - ang), a[1] + l1 * math.sin(base - ang))
    key = {'down': lambda e: e[1], 'up': lambda e: -e[1], 'fwd': lambda e: e[0], 'back': lambda e: -e[0]}[bend]
    cands = [e1, e2]
    if maxy is not None:                         # a knee must never dip below the foot line
        ok = [c for c in cands if c[1] <= maxy]
        cands = ok or [min(cands, key=lambda c: c[1])]
    e = max(cands, key=key)
    return e, (a[0] + dx, a[1] + dy)


def rot(pt, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (pt[0] * c - pt[1] * s, pt[0] * s + pt[1] * c)


def rnd(v):
    return int(math.floor(v + 0.5))


def stamp(d, x, y, t, fill):
    t = max(1, int(t))
    x0, y0 = rnd(x - t / 2 + 0.5), rnd(y - t / 2 + 0.5)
    S = RES
    if t >= 4 * S:                               # fat limbs and fists: a square minus its four corners
        d.rectangle([x0 + S, y0, x0 + t - 1 - S, y0 + t - 1], fill=fill)
        d.rectangle([x0, y0 + S, x0 + t - 1, y0 + t - 1 - S], fill=fill)
    else:
        d.rectangle([x0, y0, x0 + t - 1, y0 + t - 1], fill=fill)


def thick_line(d, p0, p1, t, fill):
    n = max(1, int(math.ceil(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * 1.5)))
    for i in range(n + 1):
        k = i / n
        stamp(d, p0[0] + (p1[0] - p0[0]) * k, p0[1] + (p1[1] - p0[1]) * k, t, fill)


def taper_line(d, p0, p1, t0, t1, fill):
    """A limb segment whose thickness runs from t0 at p0 to t1 at p1 (px): thick at the joint, thin at the extremity."""
    n = max(1, int(math.ceil(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * 1.5)))
    for i in range(n + 1):
        k = i / n
        stamp(d, p0[0] + (p1[0] - p0[0]) * k, p0[1] + (p1[1] - p0[1]) * k, rnd(t0 + (t1 - t0) * k), fill)


def smear_arc(d, pivot, a, b, t, fill, inner=None):
    """A smear frame's limb: the arc a limb swept from `a` to `b` around `pivot`, drawn as one stroke that starts hairline
    at the old position and thickens to the limb width at the new one.  The arc bulges away from the pivot (a swing,
    not a chord).  `inner`, when given, is a lighter one-pixel streak along the middle of the sweep."""
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    vx, vy = mx - pivot[0], my - pivot[1]
    n = max(1e-6, math.hypot(vx, vy))
    chord = math.hypot(b[0] - a[0], b[1] - a[1])
    bulge = 0.30 * chord
    floor = (GROUND - 1.5) * RES                              # a sweep never dips into the taskbar
    c = (mx + vx / n * bulge, min(my + vy / n * bulge, floor))   # quadratic control point, outside the chord
    steps = max(6, int(chord * 1.5))
    pts = []
    for i in range(steps + 1):
        k = i / steps
        x = (1 - k) ** 2 * a[0] + 2 * (1 - k) * k * c[0] + k * k * b[0]
        y = (1 - k) ** 2 * a[1] + 2 * (1 - k) * k * c[1] + k * k * b[1]
        pts.append((x, min(y, floor)))
    for i in range(steps + 1):
        k = i / steps
        stamp(d, pts[i][0], pts[i][1], max(RES, rnd(RES + (t - RES) * k)), fill)
    if inner is not None:
        for i in range(steps // 4, 3 * steps // 4 + 1):
            stamp(d, pts[i][0], pts[i][1], RES, inner)


def poly(d, pts, fill):
    d.polygon([(rnd(x), rnd(y)) for x, y in pts], fill=fill)


def body_frame(body: Body, pose: Pose):
    """Design-unit geometry every consumer shares (the renderer, the scarf solver): hip, shoulder, head centre,
    head tilt and the torso's unit axes, with squash/stretch applied."""
    hip = (HIP_X + pose.cx, body.hip_y0 + pose.dy)
    th = math.radians(pose.lean)
    u = (math.sin(th), -math.cos(th))
    v = (math.cos(th), math.sin(th))
    torso = body.torso * pose.sq
    S_ = (hip[0] + u[0] * torso, hip[1] + u[1] * torso)
    hh = body.head_h * pose.sq
    hc = (S_[0] + u[0] * (hh / 2 - 1) + pose.head[0], S_[1] + u[1] * (hh / 2 - 1) + pose.head[1])
    tilt = pose.lean * 0.5 + pose.tilt
    return dict(hip=hip, S=S_, head=hc, tilt=tilt, u=u, v=v, torso=torso, head_h=hh,
                head_w=body.head_w / math.sqrt(pose.sq))


def rot_rect(c, w, h, ang):
    pts = []
    for sx, sy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        rx, ry = rot((sx, sy), ang)
        pts.append((c[0] + rx, c[1] + ry))
    return pts


FACES = {
    'n': dict(eye=[(3, 1), (3, 2)], brow=[(3, -1), (4, -1)], mouth=[(3, 4), (4, 4)]),
    'f': dict(eye=[(3, 1), (3, 2)], brow=[(3, -1), (4, 0)], mouth=[(3, 4), (4, 4), (5, 3)]),
    'b': dict(eye=[(3, 2), (4, 2)], brow=[(3, -1), (4, -1)], mouth=[(3, 4), (4, 4)]),
    'h': dict(eye=[(2, 0), (3, 1), (2, 2)], brow=[(2, -2), (3, -2)], mouth=[(3, 4), (4, 4), (3, 5), (4, 5)]),
    'x': dict(eye=[(2, 0), (4, 0), (3, 1), (2, 2), (4, 2)], brow=[], mouth=[(3, 4), (4, 4), (5, 4)]),
    'w': dict(eye=[(2, 2), (3, 1), (4, 2)], brow=[], mouth=[(3, 3), (4, 4), (5, 4), (6, 3)]),
    'g': dict(eye=[(3, 1), (3, 2)], brow=[(3, -1), (4, -2)], mouth=[(3, 4), (4, 4), (5, 3)]),
    'z': dict(eye=[(2, 2), (3, 2), (4, 2)], brow=[], mouth=[(4, 4)]),
    'o': dict(eye=[(3, 0), (3, 1), (3, 2)], brow=[(2, -2), (3, -2), (4, -2)], mouth=[(4, 4), (4, 5)]),
    'back': dict(eye=[], brow=[], mouth=[]),
}


def _px(d, x, y, fill):
    """One DESIGN pixel at cell position (x, y): a RES x RES block (a single pixel at RES 1)."""
    S = RES
    cw = W * S
    if 0 <= x < cw and 0 <= y < cw:
        if S == 1:
            d.point((x, y), fill=fill)
        else:
            d.rectangle([x, y, x + S - 1, y + S - 1], fill=fill)


def fx_draw(d, kind, x, y, extra=0, sigil='/'):
    """Small in-frame effects.  (x, y) is a cell position; the pattern offsets are design pixels."""
    x, y = rnd(x), rnd(y)
    S = RES
    a, b, w_, c = PID['fx_a'], PID['fx_b'], PID['fx_w'], PID['fx_c']

    def P(dx, dy, p):
        _px(d, x + dx * S, y + dy * S, p)
    if kind == 'spark':                  # 5x5 impact burst
        for (dx, dy, p) in [(0, 0, w_), (-1, 0, b), (1, 0, b), (0, -1, b), (0, 1, b),
                            (-2, 0, a), (2, 0, a), (0, -2, a), (0, 2, a), (-1, -1, a), (1, 1, a), (1, -1, a), (-1, 1, a)]:
            P(dx, dy, p)
    elif kind == 'spark_s':
        for (dx, dy, p) in [(0, 0, w_), (-1, 0, b), (1, 0, b), (0, -1, b), (0, 1, b)]:
            P(dx, dy, p)
    elif kind == 'block':                # cyan-white parry/block flash, uses white + accent
        for (dx, dy, p) in [(0, 0, w_), (-1, 0, c), (1, 0, c), (0, -1, c), (0, 1, c), (-2, -2, w_), (2, 2, w_), (2, -2, w_), (-2, 2, w_)]:
            P(dx, dy, p)
    elif kind == 'star':
        for (dx, dy, p) in [(0, 0, w_), (-1, 0, b), (1, 0, b), (0, -1, b), (0, 1, b)]:
            P(dx, dy, p)
    elif kind == 'zzz':
        s = 1 + (extra % 2)
        pts = [(xx, yy) for yy, row in enumerate(ZGLYPH) for xx, ch in enumerate(row) if ch == '#']
        for (dx, dy) in pts:
            for sx in range(s):
                for sy in range(s):
                    P(dx * s + sx, dy * s + sy, w_)
    elif kind == 'sweat':
        for (dx, dy, p) in [(0, 0, w_), (0, 1, w_), (-1, 2, c), (0, 2, c), (1, 2, c)]:
            P(dx, dy, p)
    elif kind == 'dust':
        for (dx, dy) in [(0, 0), (1, 0), (-1, 1), (0, 1), (1, 1), (2, 1)]:
            P(dx, dy, w_)
    elif kind == 'thumb':
        P(0, 0, PID['hand_f'])
        P(0, -1, PID['hand_f'])
    elif kind == 'qmark':
        for (dx, dy) in [(0, 0), (1, 0), (2, 1), (1, 2), (1, 4)]:
            P(dx, dy, w_)
        P(1, 3, w_)
    elif kind == 'excl':
        for dy in range(4):
            P(0, dy, b)
        P(0, 5, b)
    elif kind == 'rewind':               # << glyph (Claude super)
        for off in (0, 4):
            for (dx, dy) in [(3, 0), (2, 1), (1, 2), (2, 3), (3, 4)]:
                P(off + dx - 3, dy, w_)
                P(off + dx - 2, dy, a if dy not in (2,) else b)
    elif kind == 'bigsigil':             # big $ above the head (Codex super)
        rows = ["..###..", ".#.#...", ".###...", "..###..", "...#.#.", "..###..", "...#..."]
        for yy, row in enumerate(rows):
            for xx, ch in enumerate(row):
                if ch == '#':
                    P(xx - 3, yy, b if yy in (3,) else w_)
    elif kind == 'bigglyph':             # the character's own cap sigil at 2x above the head (supers)
        for yy, row in enumerate(GLYPH[sigil]):
            for xx, ch in enumerate(row):
                if ch == '#':
                    for sx in range(2):
                        for sy in range(2):
                            P(-3 + xx * 2 + sx, yy * 2 + sy, b if yy == 2 else w_)
    elif kind == 'charge':
        for (dx, dy, p) in [(0, 0, w_), (3, -2, b), (-3, -1, b), (2, 3, a), (-2, 3, w_), (5, 1, a)]:
            P(dx, dy, p)
    elif kind == 'charge_big':           # V4: a denser charge ball for ultimates (two rings of motes)
        for (dx, dy, p) in [(0, 0, w_), (1, 0, w_), (0, 1, w_), (1, 1, w_), (-1, 0, b), (2, 0, b), (0, -1, b), (1, 2, b),
                            (3, -2, a), (-3, -1, a), (2, 3, a), (-2, 3, b), (5, 1, a), (-4, 2, a), (4, -4, b), (-3, -4, a)]:
            P(dx, dy, p)
    elif kind == 'shock':                # ground shock wave streaks
        for k in range(6):
            P(k * 2, 0, w_)
            P(-k * 2, 0, w_)
            if k in (1, 3):
                P(k * 2, -1, b)
                P(-k * 2, -1, b)
    elif kind == 'speedlines':           # V4: horizontal dash streaks behind a zipping fighter
        for k, (dx, dy) in enumerate([(-4, -6), (-6, -2), (-5, 2), (-7, 6)]):
            for i in range(4 + (k % 2) * 2):
                P(dx - i, dy, w_ if i < 2 else c)


def draw_doc(d, x, y):
    x, y = rnd(x), rnd(y)
    S = RES
    d.rectangle([x, y, x + 6 * S - 1, y + 8 * S - 1], fill=PID['doc'])
    for yy in (2, 4, 6):
        d.rectangle([x + S, y + yy * S, x + 5 * S - 1, y + yy * S + S - 1], fill=PID['doc_line'])


def render_parts(body: Body, pose: Pose, scarf_pts=None):
    """Returns (part buffer 'L', meta dict).  Facing right.  Pose, body and scarf are design units; the buffer is RES x."""
    S = RES
    cw = W * S
    img = Image.new('L', (cw, cw), 0)
    d = ImageDraw.Draw(img)
    pid = PID
    bf = body_frame(body, pose)
    hip = (bf['hip'][0] * S, bf['hip'][1] * S)
    th = math.radians(pose.lean)
    u, v = bf['u'], bf['v']
    torso = bf['torso'] * S
    Sh = (bf['S'][0] * S, bf['S'][1] * S)
    hc = (bf['head'][0] * S, bf['head'][1] * S)
    tilt = bf['tilt']
    L = lambda p: (hc[0] + rot((p[0] * S, p[1] * S), tilt)[0], hc[1] + rot((p[0] * S, p[1] * S), tilt)[1])   # head-local -> cell
    meta = {'hip': hip, 'head': hc}
    limb = body.limb * S
    thin = max(2, body.limb - 1) * S                 # wrists and ankles
    wide = (body.limb + 1) * S                       # shoulders, thighs, hips

    # ---- scarf / ponytail (behind everything)
    if body.has_tail and scarf_pts:
        pts = [(x * S, y * S) for x, y in scarf_pts]
        n = len(pts) - 1
        for i in range(n):                           # the tail tapers: full width at the neck, a ribbon at the tip
            w_b = 3 * S if i < n - 1 else 2 * S
            thick_line(d, (pts[i][0], pts[i][1] + S), (pts[i + 1][0], pts[i + 1][1] + S), w_b, pid['scarf_b'])
        for i in range(n):
            thick_line(d, pts[i], pts[i + 1], 2 * S if i < n - 1 else S, pid['scarf_a'])
    # ---- hood (Codex)
    if body.hood:
        hx, hy = Sh[0] - 3.0 * S * math.cos(th) + u[0] * S, Sh[1] - 1.5 * S
        d.ellipse([rnd(hx - 4 * S), rnd(hy - 3 * S), rnd(hx + 3 * S) + S - 1, rnd(hy + 3 * S) + S - 1], fill=pid['hood'])

    # ---- legs
    def foot_target(t):
        return ((HIP_X + pose.cx + t[0]) * S, (ANKLE_Y - t[1]) * S)

    def shoe(side, ank, ang):
        """A real shoe: rounded heel at the back, a tapered toe at the front; the sole band is untouched (it is the
        baseline every planted frame is tested on)."""
        fl = body.foot_len * S
        cx_, cy_ = ank[0] + (fl - 4 * S) / 2.0, ank[1]
        hw, hh = fl / 2.0, 1.5 * S
        local = [(-hw, -hh + S), (-hw + S, -hh), (hw - 1.5 * S, -hh), (hw, -hh + S), (hw, hh), (-hw, hh)]
        poly(d, [(cx_ + rot(p_, ang)[0], cy_ + rot(p_, ang)[1]) for p_ in local], pid[f'shoe_{side}'])
        sole = rot_rect((cx_, ank[1] + 1.5 * S), fl, 1.2 * S, ang)
        poly(d, sole, pid[f'sole_{side}'])

    def leg(side, target, bend, ang, smear):
        sgn = 1.0 if side == 'f' else -1.0
        hp = (hip[0] + sgn * v[0] * S, hip[1] + sgn * v[1] * S)
        tx = foot_target(target)
        knee, ank = ik2(hp, tx, body.thigh * S, body.shin * S, bend, maxy=(GROUND - (body.limb + 1) / 2.0 - 0.5) * S)
        stamp(d, hp[0], hp[1], wide, pid[f'leg_{side}_th'])                       # round hip
        taper_line(d, hp, knee, wide, limb, pid[f'leg_{side}_th'])
        if smear:                                                                  # the shin as the arc it swept
            _, prev_ank = ik2(hp, foot_target(smear), body.thigh * S, body.shin * S, bend)
            smear_arc(d, hp, prev_ank, ank, limb, pid[f'leg_{side}_sh'], inner=pid[f'sole_{side}'])
        taper_line(d, knee, ank, limb, thin, pid[f'leg_{side}_sh'])
        shoe(side, ank, ang)
        return ank

    ank_b = leg('b', pose.fb, pose.kb_b, pose.ang_b, pose.smear_fb)
    # ---- torso (chest wider than the hips; `chest` is the breath / puff)
    ws = pose.turn * pose.chest
    hh, hs = body.torso_w * 0.42 * pose.turn * S, body.torso_w * 0.5 * ws * S
    poly(d, [(hip[0] - v[0] * hh, hip[1] - v[1] * hh), (hip[0] + v[0] * hh, hip[1] + v[1] * hh),
             (Sh[0] + v[0] * hs, Sh[1] + v[1] * hs), (Sh[0] - v[0] * hs, Sh[1] - v[1] * hs)], pid['torso'])
    thick_line(d, (hip[0] - v[0] * hh + u[0] * S, hip[1] - v[1] * hh + u[1] * S), (hip[0] + v[0] * hh + u[0] * S, hip[1] + v[1] * hh + u[1] * S), S, pid['belt'])

    # ---- arms
    def hand_at(side, hand, dirx, diry, fist, open_):
        hx, hy = hand[0] + dirx * 1.4 * S, hand[1] + diry * 1.4 * S
        if open_:                                    # palm + three fingers fanned along the forearm direction
            d.rectangle([rnd(hx - S), rnd(hy - 2 * S), rnd(hx + S) + S - 1, rnd(hy + S) + S - 1], fill=pid[f'hand_{side}'])
            px_, py_ = -diry, dirx
            for k in (-1, 0, 1):
                fx_, fy_ = hx + dirx * 2.2 * S + px_ * k * 1.1 * S, hy + diry * 2.2 * S + py_ * k * 1.1 * S
                _px(d, rnd(fx_), rnd(fy_), pid[f'hand_{side}'])
        else:                                        # a fist with a thumb knuckle on top
            stamp(d, hx, hy, fist * S, pid[f'hand_{side}'])
            tx_, ty_ = hx - dirx * 0.6 * S - diry * (fist / 2.0) * S, hy - diry * 0.6 * S + dirx * (fist / 2.0) * S
            if ty_ <= hy:                            # only when "up" is up: a thumb below the fist reads as a drip
                _px(d, rnd(tx_), rnd(ty_), pid[f'hand_{side}'])

    def arm(side, target, bend, fist, open_, smear):
        sgn = 1.0 if side == 'f' else -1.0
        base = (Sh[0] - u[0] * 1.5 * S + sgn * v[0] * 2.0 * pose.turn * S, Sh[1] - u[1] * 1.5 * S + sgn * v[1] * 2.0 * pose.turn * S)
        tgt = (base[0] + target[0] * S, base[1] + target[1] * S)
        el, hand = ik2(base, tgt, body.upper * S, body.fore * S, bend)
        stamp(d, base[0], base[1], wide, pid[f'arm_{side}_up'])                    # round shoulder
        taper_line(d, base, el, limb, limb, pid[f'arm_{side}_up'])
        dirx, diry = hand[0] - el[0], hand[1] - el[1]
        n = max(1e-6, math.hypot(dirx, diry))
        dirx, diry = dirx / n, diry / n
        if smear:                                    # the forearm as the arc the hand swept this frame
            _, prev_hand = ik2(base, (base[0] + smear[0] * S, base[1] + smear[1] * S), body.upper * S, body.fore * S, bend)
            sweep = math.hypot(hand[0] - prev_hand[0], hand[1] - prev_hand[1])
            smear_arc(d, base, prev_hand, hand, limb + (S if sweep <= 12 * S else 0), pid[f'arm_{side}_fo'], inner=pid[f'cuff_{side}'])
        taper_line(d, el, hand, limb, thin, pid[f'arm_{side}_fo'])
        thick_line(d, (hand[0] - dirx * 2.2 * S, hand[1] - diry * 2.2 * S), (hand[0] - dirx * 0.8 * S, hand[1] - diry * 0.8 * S), limb, pid[f'cuff_{side}'])
        hand_at(side, hand, dirx, diry, fist, open_)
        return hand

    hb = arm('b', pose.hb, pose.eb_b, pose.fist_b, False, pose.smear_b)
    ank_f = leg('f', pose.ff, pose.kb_f, pose.ang_f, pose.smear_ff)

    # ---- head
    hw, hh_ = rnd(bf['head_w'] * S), rnd(bf['head_h'] * S)
    x0, y0 = rnd(hc[0] - hw / 2 + 0.5), rnd(hc[1] - hh_ / 2 + 0.5)
    d.ellipse([x0, y0, x0 + hw - 1, y0 + hh_ - 1], fill=pid['head'])
    for p in [(7, 2), (7, 3)]:                               # nose
        gx, gy = L(p)
        _px(d, rnd(gx), rnd(gy), pid['head'])
    gx, gy = L((-1, 2))
    d.rectangle([rnd(gx), rnd(gy), rnd(gx) + 2 * S - 1, rnd(gy) + 3 * S - 1], fill=pid['ear'])
    # hair under the cap: forehead + nape
    for (x1, y1, x2, y2) in [(4.0, -2, 6.5, -0.5), (-6.5, 0, -4.5, 2)]:
        poly(d, [L((x1, y1)), L((x2, y1)), L((x2, y2)), L((x1, y2))], pid['hair'])
    # reversed cap: crown, visor to the back, strap at the front
    crown = [(-6.8, -1.8), (-6.5, -4.2), (-4, -6.7), (1, -7.2), (4.5, -6), (6.8, -3.5), (6.8, -1.8)]
    poly(d, [L(p) for p in crown], pid['cap'])
    poly(d, [L((-6, -2.5)), L((-11.5, -1)), L((-11.5, 1)), L((-6, 0))], pid['visor'])
    poly(d, [L((5.5, -2.3)), L((7, -2.3)), L((7, -1.7)), L((5.5, -1.7))], pid['strap'])
    gl = GLYPH[body.sigil]
    cx_, cy_ = L((-0.5, -4.2))
    gx0, gy0 = rnd(cx_) - S, rnd(cy_) - 2 * S
    for yy, row in enumerate(gl):
        for xx, ch in enumerate(row):
            if ch == '#':
                _px(d, gx0 + xx * S, gy0 + yy * S, pid['sigil'])
    meta['sigil'] = (gx0, gy0)
    fc = FACES.get(pose.face, FACES['n'])
    for key in ('eye', 'brow', 'mouth'):
        for p in fc[key]:
            gx, gy = L(p)
            _px(d, rnd(gx), rnd(gy), pid[key])

    # ---- front arm (last = in front of everything)
    hf = arm('f', pose.hf, pose.eb_f, pose.fist_f, pose.open_f, pose.smear_f)
    meta.update(hf=hf, hb=hb, ff=ank_f, fb=ank_b, S=Sh)

    # ---- effects
    if pose.doc:
        ax_, ay_ = hf if pose.doc == 'hf' else hb
        draw_doc(d, ax_ + 0.5 * S, ay_ - 5 * S)
    anchors = {'hf': hf, 'hb': hb, 'ff': ank_f, 'fb': ank_b, 'head': hc, 'hip': hip, 'S': Sh, 'abs': (0, 0)}
    text = []
    for f in pose.fx:
        kind, anc, ox, oy = f[0], f[1], f[2], f[3]
        extra = f[4] if len(f) > 4 else 0
        ax, ay = anchors[anc]
        if kind in TEXT_FX:                      # drawn last, on top, so the mirror step can redraw them un-mirrored
            text.append((kind, ax + ox * S, ay + oy * S, extra))
        else:
            fx_draw(d, kind, ax + ox * S, ay + oy * S, extra, body.sigil)
    if text:
        meta['pre_text'] = img.copy()
        meta['text_fx'] = text
        for kind, x, y, extra in text:
            fx_draw(d, kind, x, y, extra, body.sigil)
    return img, meta


def sigil_box_l(meta: dict, body: Body):
    """Top-left of the sigil's (3*RES x 5*RES) box in the LEFT-facing (mirrored) cell."""
    gx0, gy0 = meta['sigil']
    return W * RES - len(GLYPH[body.sigil][0]) * RES - gx0, gy0


def _glyph_cells(sym):
    """Every pixel of the sigil box at the current RES -> True where the glyph is inked."""
    S = RES
    gl = GLYPH[sym]
    return [((xx, yy), gl[yy // S][xx // S] == '#') for yy in range(len(gl) * S) for xx in range(len(gl[0]) * S)]


def mirror_parts(buf: Image.Image, meta: dict, body: Body):
    """Left-facing: mirror the buffer, then redraw the sigil un-mirrored so '/', '$', '>' still read correctly.

    Only pixels that are cap or sigil in the flipped buffer are touched: a hand, arm or face that occludes the cap in
    this frame stays on top (painting the whole glyph box used to draw the sigil over hands, e.g. in `review`)."""
    m = meta.get('pre_text', buf).transpose(Image.FLIP_LEFT_RIGHT)
    cw = W * RES
    mx0, gy0 = sigil_box_l(meta, body)
    px = m.load()
    ok = (PID['cap'], PID['sigil'])
    for (xx, yy), on in _glyph_cells(body.sigil):
        x, y = mx0 + xx, gy0 + yy
        if 0 <= x < cw and 0 <= y < cw and px[x, y] in ok:
            px[x, y] = PID['sigil'] if on else PID['cap']
    # letters ('$', '>', 'L', '?', 'z') are redrawn un-mirrored over the same mirrored footprint
    d = ImageDraw.Draw(m)
    for kind, x, y, extra in meta.get('text_fx', ()):
        bb = text_fx_bbox(kind, x, y, extra, body.sigil)
        if bb:
            shift = (cw - 1 - bb[2]) - bb[0]
            fx_draw(d, kind, x + shift, y, extra, body.sigil)
    return m


def text_fx_bbox(kind, x, y, extra, sigil):
    """Inclusive (x0, y0, x1, y1) of one effect's pixels as drawn at (x, y)."""
    cw = W * RES
    tmp = Image.new('L', (cw, cw), 0)
    fx_draw(ImageDraw.Draw(tmp), kind, x, y, extra, sigil)
    bb = tmp.getbbox()
    return (bb[0], bb[1], bb[2] - 1, bb[3] - 1) if bb else None


def mirror_rgba(im: Image.Image, meta: dict, body: Body):
    """Left-facing version of a finished RGBA frame (hand-polished override): flip it, then redraw the sigil
    un-mirrored at the generator's sigil position, only over pixels that are cap cloth or sigil colour."""
    m = im.convert('RGBA').transpose(Image.FLIP_LEFT_RIGHT)
    cw = W * RES
    pal = body.palette
    sig = pal['trim']['hi']
    cap = {pal['cloth'][t] for t in ('base', 'hi', 'sh')}
    if RES > 1:
        cap.add(rim_tone(pal['cloth']))
    mx0, gy0 = sigil_box_l(meta, body)
    px = m.load()
    for (xx, yy), on in _glyph_cells(body.sigil):
        x, y = mx0 + xx, gy0 + yy
        if 0 <= x < cw and 0 <= y < cw and px[x, y][3] and (px[x, y][:3] in cap or px[x, y][:3] == sig):
            px[x, y] = (sig if on else pal['cloth']['base']) + (255,)
    return m


def lum(c):
    return 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]


def _tone(grp, name, tone):
    return grp[tone]


def finish(buf: Image.Image, body: Body, pose: Pose, hip_y=None):
    """Part buffer -> RGBA with edge-based 3-tone shading and selective outline.

    At RES k > 1 the highlight / shadow bands are k px wide, the outline is k px, and the outermost highlight pixel
    next to empty space takes the group's rim tone (`hi2`): one extra tone, so the bigger cell reads as more detail
    rather than as a blow-up."""
    S = RES
    cw = W * S
    px = buf.load()
    out = Image.new('RGBA', (cw, cw), (0, 0, 0, 0))
    op = out.load()
    pal = body.palette

    def part(x, y):
        return px[x, y] if 0 <= x < cw and 0 <= y < cw else 0

    def occluder(n, a):
        return n != 0 and n != a and NAME[n] not in FLAT and NAME[n] not in NOLINE and Z[n] > Z[a]

    def opens_hi(n, a):
        return n == 0 or (n != a and Z[n] < Z[a] and NAME[n] not in FLAT)

    for y in range(cw):
        for x in range(cw):
            a = px[x, y]
            if not a:
                continue
            nm = NAME[a]
            if pose.flash and nm not in NOLINE:
                op[x, y] = pal['flash']['fill'] + (255,)
                continue
            if nm in FLAT:
                g, tone = FLAT[nm]
                if g == 'fx':
                    op[x, y] = pal['fx'][tone] + (255,)
                else:
                    op[x, y] = pal[g][tone or 'base'] + (255,)
                continue
            gname = group_of(body, nm)
            grp = pal[gname]
            if S == 1:
                up, lf, dn, rt = part(x, y - 1), part(x - 1, y), part(x, y + 1), part(x + 1, y)
                hi = up == 0 or lf == 0 or (up != a and Z[up] < Z[a] and NAME[up] not in FLAT) or (lf != a and Z[lf] < Z[a] and NAME[lf] not in FLAT)
                sh = dn == 0 or rt == 0 or occluder(dn, a) or occluder(rt, a)
                rim = False
            else:
                hi = any(opens_hi(part(x, y - k), a) or opens_hi(part(x - k, y), a) for k in range(1, S + 1))
                sh = any((part(x, y + k) == 0 or occluder(part(x, y + k), a) or part(x + k, y) == 0 or occluder(part(x + k, y), a))
                         for k in range(1, S + 1))
                rim = part(x, y - 1) == 0 or part(x - 1, y) == 0
            tone = 'base' if (hi and sh) or (not hi and not sh) else ('hi' if hi else 'sh')
            if nm in DARK:                       # far-side limbs sit one tone darker
                tone = {'hi': 'base', 'base': 'sh', 'sh': 'sh'}[tone]
            elif tone == 'hi' and rim and gname in RIM_GROUPS:
                op[x, y] = rim_tone(grp) + (255,)
                continue
            op[x, y] = grp[tone] + (255,)

    # selective outline: tinted by the darkest neighbouring material, ink on ground contact (RES px wide)
    ol_pixels = {}
    steps = [(0, -k) for k in range(1, S + 1)] + [(-k, 0) for k in range(1, S + 1)] + \
            [(k, 0) for k in range(1, S + 1)] + [(0, k) for k in range(1, S + 1)]
    if S == 1:
        steps = [(0, -1), (-1, 0), (1, 0), (0, 1)]
    for y in range(cw):
        for x in range(cw):
            if px[x, y]:
                continue
            best = None
            for dx, dy in steps:
                n = part(x + dx, y + dy)
                if not n or NAME[n] in NOLINE:
                    continue
                nm = NAME[n]
                if pose.flash:
                    c = pal['flash']['ol']
                elif nm in FLAT:
                    c = pal['ink']['base']
                else:
                    c = pal[group_of(body, nm)]['ol']
                    if dy < 0 and nm in ('sole_f', 'sole_b'):
                        c = pal['ink']['base']
                if best is None or lum(c) < lum(best):
                    best = c
            if best is not None:
                ol_pixels[(x, y)] = best
    for (x, y), c in ol_pixels.items():
        op[x, y] = c + (255,)

    if pose.aura:                                    # flickering flame ring (rage / power-up)
        import random
        rng = random.Random(pose.aura * 7919)
        ys = hip_y if hip_y is not None else body.hip_y0 * S
        cols = [pal['fx']['a'], pal['fx']['b'], pal['fx']['a']]
        cand = []
        r = 2 * S
        for y in range(r, cw - r):
            for x in range(r, cw - r):
                if op[x, y][3] or y > ys + 8 * S:
                    continue
                near = any(px[x + dx, y + dy] and NAME[px[x + dx, y + dy]] not in NOLINE
                           for dx in range(-r, r + 1) for dy in range(-r, r + 1) if 0 <= x + dx < cw and 0 <= y + dy < cw)
                if near:
                    cand.append((x, y))
        rng.shuffle(cand)
        for (x, y) in cand[:max(10 * S * S, len(cand) // 5)]:
            op[x, y] = cols[(x * 3 + y) % 3] + (255,)
    return out


def palette_of(frames):
    cols = set()
    for im in frames:
        px = im.load()
        w, h = im.size
        for y in range(h):
            for x in range(w):
                if px[x, y][3]:
                    cols.add(px[x, y][:3])
    return cols
