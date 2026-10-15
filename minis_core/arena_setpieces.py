"""Arena set pieces (docs/ARENA.md "Set pieces"): hand-authored joint timelines for both fighters, played 2-4 times a match
at dramatic moments and mixed with the procedural fighting in arena.py.  Visual only, like everything in the arena.

A set piece is a list of keys (seconds from its start, op, args) for two actors, 'A' (the attacker) and 'D' (the
defender).  Positions are 1-D along the line between them: x = 0 is A's mark, x = `gap` is D's mark, positive x is the
direction A faces at the start; y stays on the shared ground (both stand on the same window top or the floor).

Poses are SLOTS, not move names, so any pairing works and nothing reads a move id literally:
  stance  low ready stance            charge  the power-up loop          dash   the dash smear frame
  wind    signature strike, frame before contact     cut / cut2 / cut3   contact frames of the strongest strikes
  follow  signature strike follow-through            guard  block         stagger / recoil   hit / heavy hit
  idle    released back to the animation clock
Each fighter's strikes are ranked from its own atlas (signature strike first, then by `power`).

Elements: every fighter's sword trails are painted in one element - flame, water, lightning, wind, petal or ink -
chosen from the atlas (`element` in anim.json when present, else the accent colour's hue).  The trail is a wide painted
ribbon that follows the blade arc: drawn on fast, held, then thinned from the tail and faded.  Impacts can use an
ink-wash frame: a black ink splash behind the struck fighter, both drawn as flat silhouettes, a white cut across it.
"""
from __future__ import annotations
import colorsys, math, random
from PIL import Image, ImageDraw

ELEMENTS = ('flame', 'water', 'lightning', 'wind', 'petal', 'ink')
EASES = {'lin': lambda k: k, 'out': lambda k: 1.0 - (1.0 - k) ** 3, 'inout': lambda k: 0.5 - 0.5 * math.cos(math.pi * k)}


def element_for(atlas):
    """The element of a fighter's trails: anim.json `element` when the art names one, else from the accent's hue."""
    e = (getattr(atlas, 'meta', None) or {}).get('element')
    if e in ELEMENTS:
        return e
    r, g, b = [v / 255.0 for v in atlas.accent]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h *= 360.0
    if s < 0.2:
        return 'ink'
    if h < 30 or h >= 355:
        return 'flame'
    if h < 70 or 235 <= h < 290:
        return 'lightning'
    if h < 190:
        return 'wind'
    if h < 235:
        return 'water'
    return 'petal'


# ---------------------------------------------------------------- pose slots
def strikes_ranked(atlas):
    """The fighter's strike moves, strongest first (signature strike leads); only moves that have a hit frame."""
    sig = atlas.signature().get('strike')
    pool = [n for n, a in atlas.anim.items() if a.get('cat') == 'strike' and 'hit_frame' in a]
    if sig and sig not in pool and sig in atlas.anim and 'hit_frame' in atlas.anim[sig]:
        pool.append(sig)

    def blade(n):                                       # a cut reads as a cut: slashes first, kicks and punches last
        a = atlas.anim[n]
        txt = (n + ' ' + str(a.get('desc') or '') + ' ' + str(a.get('family') or '')).lower()
        if any(k in n for k in ('kick', 'punch', 'jab', 'palm', 'fist')):
            return 3
        if n.startswith('air_') or 'aerial' in txt or 'mid-air' in txt:
            return 2                                        # an aerial pose looks like a jump on the ground
        return 0 if any(k in txt for k in ('slash', 'cut', 'blade', 'sword', 'swing', 'cleave')) else 1
    pool.sort(key=lambda n: (blade(n), n != sig, -int(atlas.anim[n].get('power') or 1), n))
    return pool


def resolve_slot(atlas, slot):
    """-> (anim, frame index) for a held pose, ('@play', anim) for an animation that runs, or None (release)."""
    if slot in (None, 'idle'):
        return None
    has = atlas.anim.__contains__
    n = lambda a: len(atlas.anim[a]['frames'])
    if slot == 'charge':
        return ('@play', 'powerup') if has('powerup') else ('crouch', n('crouch') - 1) if has('crouch') else None
    if slot == 'stance':
        return ('crouch', n('crouch') - 1) if has('crouch') else ('idle', 0)
    if slot == 'dash':
        return ('dash', min(2, n('dash') - 1)) if has('dash') else ('jump', 0) if has('jump') else ('idle', 0)
    if slot == 'guard':
        return ('block', n('block') - 1) if has('block') else ('idle', 0)
    if slot in ('stagger', 'recoil'):
        a = 'hit' if slot == 'stagger' else 'hit_heavy'
        a = a if has(a) else ('hit' if has('hit') else 'idle')
        return (a, min(2 if slot == 'recoil' else 1, n(a) - 1))
    if slot in ('wind', 'cut', 'follow', 'cut2', 'cut3'):
        ranked = strikes_ranked(atlas) or ['idle']
        m = ranked[{'cut2': 1, 'cut3': 2}.get(slot, 0) % len(ranked)]
        if m == 'idle':
            return ('idle', 0)
        hf = int(atlas.anim[m].get('hit_frame', 0))
        idx = hf - 1 if slot == 'wind' else hf + 1 if slot == 'follow' else hf
        return (m, max(0, min(n(m) - 1, idx)))
    return None


# ---------------------------------------------------------------- the set pieces (hand-authored)
def cut(r, a0, a1, width, draw, hold, fade, seed, chest=-100, k=0.62, **kw):
    """An arc trail that passes THROUGH the body: its circle's centre sits behind the chest, opposite the arc's middle,
    so the ribbon sweeps across the torso instead of circling it."""
    m = math.radians((a0 + a1) / 2.0)
    return dict(path='arc', cx=round(-math.cos(m) * r * k, 1), cy=round(chest - math.sin(m) * r * k, 1), r=r, a0=a0, a1=a1, width=width,
                draw=draw, hold=hold, fade=fade, seed=seed, **kw)


def _flurry_keys():
    keys = [(0.00, 'pose', 'A', 'stance'), (0.00, 'pose', 'D', 'guard'), (0.00, 'cam', dict(box=2.0)),
            (0.18, 'ghost', 'A'), (0.18, 'pose', 'A', 'dash'), (0.18, 'pos', 'A', dict(near=0, dur=0.07, ease='out', ghosts=True))]
    arcs = [(-150, -20), (150, 25), (-120, 30), (160, -10), (-170, 0)]
    slots = ['cut', 'cut2', 'cut3', 'cut2', 'cut']
    for i in range(5):
        t = 0.28 + 0.11 * i
        a0, a1 = arcs[i]
        keys += [(t, 'pose', 'A', slots[i]), (t, 'ghost', 'A'), (t, 'pos', 'A', dict(near=7 * i + (5 if i % 2 else -3), dur=0.04)),
                 (t + 0.03, 'trail', 'D', cut(92 + 6 * (i % 2), a0, a1, 24, 0.05, 0.04, 0.16, i, chest=-104 + (i % 3) * 8)),
                 (t + 0.04, 'hit', dict(dmg=3, react='stagger' if i % 2 == 0 else 'recoil', push=7)),
                 (t + 0.04, 'spark', 'D')]
    keys += [(0.86, 'pose', 'A', 'wind'), (0.86, 'cam', dict(punch='D', hold=0.3, lines='h', until=1.2)),
             (1.06, 'pose', 'A', 'follow'), (1.06, 'ghost', 'A'), (1.06, 'pos', 'A', dict(near=40, dur=0.05, ease='out')),
             (1.07, 'trail', 'D', cut(210, -72, -8, 46, 0.07, 0.22, 0.3, 9, k=1.0)),
             (1.08, 'ink', 'D'), (1.08, 'hit', dict(dmg=14, react='knockdown', final=True)), (1.08, 'shake', dict(frames=8, amp=8)),
             (1.55, 'pose', 'A', 'idle')]
    return keys


SETPIECES = {
    # the attacker vanishes, reappears behind the defender in its follow-through, a frozen beat, then the cut lands
    'vanishing_cut': dict(gap=300, span=(-40, 520), dur=2.0, dmg=26, keys=[
        (0.00, 'pose', 'A', 'stance'), (0.00, 'pose', 'D', 'guard'), (0.00, 'cam', dict(box=1.9)),
        (0.08, 'trail', 'A', dict(path='arc', cx=18, cy=-92, r=70, a0=-70, a1=60, width=20, draw=0.28, hold=0.1, fade=0.12, seed=1)),
        (0.52, 'ghost', 'A'), (0.52, 'alpha', 'A', 0.0),
        (0.53, 'trail', 'A', dict(path='line', x0=20, x1=470, y=-118, width=16, draw=0.06, hold=0.3, fade=0.25, seed=2, world=True, layer='back')),
        (0.56, 'pos', 'A', dict(x=490, dur=0.0)), (0.56, 'pose', 'A', 'follow'), (0.56, 'alpha', 'A', 1.0),
        (0.58, 'cam', dict(punch='D', hold=0.42, lines='h', until=1.02)),
        (1.02, 'trail', 'D', cut(220, -168, -104, 42, 0.08, 0.24, 0.3, 3, chest=-104, k=1.0)),
        (1.03, 'ink', 'D'), (1.03, 'hit', dict(dmg=26, react='knockdown', final=True)), (1.03, 'shake', dict(frames=8, amp=8)),
        (1.45, 'face', 'A', 'toward'), (1.45, 'pose', 'A', 'idle')]),
    # a rapid flurry of cuts with afterimages, then one big cut that sends the defender down
    'flurry': dict(gap=230, span=(-40, 330), dur=1.8, dmg=29, keys=_flurry_keys()),
    # a long stance and charge (element swirling round the blade, focus lines), a vanishing dash, the finisher
    'stance_finisher': dict(gap=420, span=(-60, 640), dur=2.6, dmg=36, keys=[
        (0.00, 'pose', 'A', 'stance'), (0.00, 'pose', 'D', 'guard'), (0.00, 'cam', dict(box=2.5, radial='A', until=0.98)),
        (0.05, 'trail', 'A', dict(path='arc', cx=0, cy=-96, r=96, a0=-90, a1=180, width=26, draw=0.45, hold=0.35, fade=0.2, seed=4)),
        (0.25, 'trail', 'A', dict(path='arc', cx=0, cy=-96, r=118, a0=90, a1=350, width=20, draw=0.4, hold=0.25, fade=0.2, seed=5)),
        (0.45, 'trail', 'A', dict(path='arc', cx=0, cy=-96, r=78, a0=180, a1=420, width=16, draw=0.35, hold=0.15, fade=0.2, seed=6)),
        (0.62, 'shake', dict(frames=10, amp=3)), (0.70, 'cam', dict(punch='A', hold=0.22)),
        (0.98, 'ghost', 'A'), (0.98, 'pose', 'A', 'dash'), (0.98, 'alpha', 'A', 0.55),
        (0.98, 'trail', 'A', dict(path='line', x0=20, x1=550, y=-118, width=18, draw=0.09, hold=0.35, fade=0.3, seed=7, world=True, layer='back')),
        (0.98, 'pos', 'A', dict(x=570, dur=0.1, ghosts=True)),
        (1.09, 'pose', 'A', 'follow'), (1.09, 'alpha', 'A', 1.0), (1.10, 'cam', dict(punch='D', hold=0.5, lines='h', until=1.6)),
        (1.60, 'trail', 'D', cut(250, -76, -12, 58, 0.1, 0.32, 0.35, 8, chest=-102, k=1.0)),
        (1.61, 'ink', 'D'), (1.61, 'flash', 'A'), (1.61, 'hit', dict(dmg=36, react='knockdown', final=True)),
        (1.61, 'shake', dict(frames=10, amp=10)),
        (2.15, 'face', 'A', 'toward'), (2.15, 'pose', 'A', 'idle')]),
}


# ---------------------------------------------------------------- painted ribbons
def _path_points(spec, step_deg=4.0):
    """Local points of a trail (origin = the anchor, +x = the facing direction, y down)."""
    if spec['path'] == 'line':
        n = max(2, int(abs(spec['x1'] - spec['x0']) / 14))
        return [(spec['x0'] + (spec['x1'] - spec['x0']) * i / (n - 1), spec['y']) for i in range(n)]
    a0, a1, r = spec['a0'], spec['a1'], spec['r']
    n = max(3, int(abs(a1 - a0) / step_deg) + 1)
    out = []
    for i in range(n):
        a = math.radians(a0 + (a1 - a0) * i / (n - 1))
        out.append((spec['cx'] + r * math.cos(a), spec['cy'] + r * math.sin(a)))
    return out


COLORS = {   # (edge, body, core) - original palettes, one per element
    'flame': ((200, 40, 20), (255, 140, 40), (255, 240, 170)),
    'water': ((20, 70, 190), (70, 170, 255), (235, 250, 255)),
    'lightning': (None, None, (255, 255, 235)),
    'wind': ((90, 190, 160), (190, 250, 225), (255, 255, 255)),
    'petal': ((210, 70, 120), (255, 170, 200), (255, 240, 246)),
    'ink': ((14, 12, 18), (34, 30, 40), (90, 84, 96)),
}


def ribbon(element, spec, head, tail, alpha, tint=(255, 255, 255)):
    """-> (image, ox, oy): the painted trail between path fractions tail..head (0..1), at `alpha`; (ox, oy) is where the
    path origin sits in the image.  Pure function of its arguments (callers cache it)."""
    pts = _path_points(spec)
    n = len(pts)
    i0, i1 = int(round(tail * (n - 1))), int(round(head * (n - 1)))
    if i1 - i0 < 1:
        return None
    seg = pts[i0:i1 + 1]
    w = float(spec['width'])
    xs, ys = [p[0] for p in seg], [p[1] for p in seg]
    pad = int(w * 1.6) + 16
    ox, oy = pad - min(xs), pad - min(ys)
    W, H = int(max(xs) - min(xs)) + 2 * pad, int(max(ys) - min(ys)) + 2 * pad
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rng = random.Random(spec.get('seed', 0) * 7919 + i0)
    P = [(x + ox, y + oy) for x, y in seg]
    m = len(P)

    def normal(i):
        a, b = P[max(0, i - 1)], P[min(m - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        return -dy / L, dx / L

    def prof(i):                                    # thin at the tail, full behind the head, a rounded tip
        k = i / max(1, m - 1)
        return max(0.08, min(1.0, k * 1.6)) * (1.0 if k < 0.9 else 0.4 + 0.6 * (1.0 - k) / 0.1)

    def band(scale, col, a):
        outer, inner = [], []
        for i in range(m):
            nx, ny = normal(i)
            h = w * 0.5 * scale * prof(i)
            outer.append((P[i][0] + nx * h, P[i][1] + ny * h))
            inner.append((P[i][0] - nx * h, P[i][1] - ny * h))
        d.polygon(outer + inner[::-1], fill=col + (int(a * alpha),))
        return outer

    edge, body, core = COLORS[element]
    if element == 'lightning':
        glow = tuple(min(255, int(0.7 * t + 0.3 * 255)) for t in tint)
        zz = []
        for i in range(0, m, 2):
            nx, ny = normal(i)
            off = rng.uniform(-0.45, 0.45) * w * prof(i)
            zz.append((P[i][0] + nx * off, P[i][1] + ny * off))
        if len(zz) >= 2:
            d.line(zz, fill=glow + (int(120 * alpha),), width=max(4, int(w * 0.75)), joint='curve')
            d.line(zz, fill=tint + (int(235 * alpha),), width=max(3, int(w * 0.32)), joint='curve')
            d.line(zz, fill=core + (int(255 * alpha),), width=4, joint='curve')
            for j in range(1, len(zz) - 1, 3):              # forks
                x, y = zz[j]
                nx, ny = normal(min(m - 1, j * 2))
                s = rng.choice((-1, 1))
                fork = [(x, y), (x + nx * s * w * 0.7 + rng.uniform(-8, 8), y + ny * s * w * 0.7 + rng.uniform(-8, 8)),
                        (x + nx * s * w * 1.2 + rng.uniform(-10, 10), y + ny * s * w * 1.2 + rng.uniform(-10, 10))]
                d.line(fork, fill=glow + (int(150 * alpha),), width=4)
                d.line(fork, fill=core + (int(230 * alpha),), width=2)
        return im, ox, oy
    if element == 'wind':
        body = tuple(int(0.6 * c + 0.4 * t) for c, t in zip(body, tint))
    outer = band(1.0, edge, 150 if element in ('wind', 'petal') else 215)
    band(0.66, body, 200 if element in ('wind', 'petal') else 235)
    band(0.2, core, 255 if element != 'ink' else 0)
    if element == 'flame':                               # tongues licking off the outer edge, pointing back along the arc
        for i in range(2, m - 1, 2):
            nx, ny = normal(i)
            tx, ty = P[i - 2][0] - P[i][0], P[i - 2][1] - P[i][1]
            L = w * rng.uniform(0.35, 0.8) * prof(i)
            bx, by = outer[i]
            tip = (bx + nx * L * 0.8 + tx * 0.6, by + ny * L * 0.8 + ty * 0.6)
            d.polygon([outer[max(0, i - 1)], tip, outer[i]], fill=(255, 120 + rng.randrange(80), 30, int(220 * alpha)))
    elif element == 'water':                             # curls breaking off the outer edge
        for i in range(3, m - 1, 4):
            nx, ny = normal(i)
            r = w * 0.22 * prof(i) + 3
            cx, cy = outer[i][0] + nx * r * 0.6, outer[i][1] + ny * r * 0.6
            d.arc([cx - r, cy - r, cx + r, cy + r], 200, 470, fill=(235, 250, 255, int(230 * alpha)), width=2)
            if rng.random() < 0.6:
                dr = rng.uniform(2, 4)
                dx, dy = cx + nx * r * 1.6, cy + ny * r * 1.6
                d.ellipse([dx - dr, dy - dr, dx + dr, dy + dr], fill=(180, 230, 255, int(220 * alpha)))
    elif element == 'wind':                              # streak lines riding the ribbon
        for k in (-0.35, 0.0, 0.35):
            line = []
            for i in range(m):
                nx, ny = normal(i)
                h = w * 0.5 * k * prof(i)
                line.append((P[i][0] + nx * h, P[i][1] + ny * h))
            d.line(line[int(m * 0.15):], fill=(255, 255, 255, int(235 * alpha)), width=2)
    elif element == 'petal':                             # petals shed along the trail
        for i in range(1, m, 2):
            nx, ny = normal(i)
            o = rng.uniform(-0.9, 0.9) * w * 0.7
            x, y = P[i][0] + nx * o, P[i][1] + ny * o
            a = rng.uniform(0, math.pi)
            s = rng.uniform(6, 10)
            pet = [(x + math.cos(a) * s, y + math.sin(a) * s), (x + math.cos(a + 1.9) * s * 0.45, y + math.sin(a + 1.9) * s * 0.45),
                   (x - math.cos(a) * s, y - math.sin(a) * s), (x + math.cos(a - 1.9) * s * 0.45, y + math.sin(a - 1.9) * s * 0.45)]
            d.polygon(pet, fill=(255, 205, 222, int(240 * alpha)) if i % 4 else (255, 250, 252, int(240 * alpha)), outline=(205, 80, 130, int(240 * alpha)))
    elif element == 'ink':                               # dry-brush bristle gaps and splatter
        for k in (-0.3, 0.1, 0.38):
            for i in range(1, m - 1):
                if rng.random() < 0.3:
                    nx, ny = normal(i)
                    h = w * 0.5 * k * prof(i)
                    d.line([(P[i][0] + nx * h, P[i][1] + ny * h), (P[i + 1][0] + nx * h, P[i + 1][1] + ny * h)], fill=(250, 248, 240, int(90 * alpha)), width=2)
        for i in range(0, m, 3):
            nx, ny = normal(i)
            o = rng.choice((-1, 1)) * rng.uniform(0.7, 1.2) * w * 0.6
            r = rng.uniform(1.5, 3.5)
            x, y = P[i][0] + nx * o, P[i][1] + ny * o
            d.ellipse([x - r, y - r, x + r, y + r], fill=(14, 12, 18, int(230 * alpha)))
    return im, ox, oy


def ink_splash(w, h, seed):
    """The ink-wash impact backdrop: a black brush blot with splatter and drips, a white cut across it."""
    rng = random.Random(seed)
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = w / 2.0, h / 2.0
    for _ in range(14):
        rx, ry = rng.uniform(0.18, 0.42) * w, rng.uniform(0.18, 0.4) * h
        x, y = cx + rng.uniform(-0.18, 0.18) * w, cy + rng.uniform(-0.15, 0.15) * h
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=(10, 8, 12, 238))
    for _ in range(26):
        a = rng.uniform(0, 2 * math.pi)
        L = rng.uniform(0.38, 0.5)
        x, y = cx + math.cos(a) * w * L, cy + math.sin(a) * h * L
        r = rng.uniform(2, 7)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(10, 8, 12, 238))
        d.line([(cx + math.cos(a) * w * 0.3, cy + math.sin(a) * h * 0.3), (x, y)], fill=(10, 8, 12, 238), width=int(r))
    for _ in range(4):                                   # drips
        x = cx + rng.uniform(-0.25, 0.25) * w
        y0 = cy + h * 0.25
        d.line([(x, y0), (x, y0 + rng.uniform(0.08, 0.18) * h)], fill=(10, 8, 12, 238), width=rng.randint(3, 6))
    d.polygon([(w * 0.04, h * 0.78), (w * 0.96, h * 0.16), (w * 0.97, h * 0.2), (w * 0.06, h * 0.84)], fill=(255, 255, 255, 255))
    return im


# ---------------------------------------------------------------- the player
class SetPiece:
    """Plays one set piece on the arena's two bodies.  The arena calls tick(now) every frame, drawables(now) for the
    trails / ink / backdrop lines, and supplies the hit (arena._setpiece_hit) so HP, KOs and records stay in one place."""

    def __init__(self, arena, name, att, dfn, ground_y, origin_x, s, now):
        self.arena, self.name = arena, name
        self.spec = SETPIECES[name]
        self.slot = {'A': att, 'D': dfn}
        self.y, self.ox, self.s = float(ground_y), float(origin_x), s
        self.t0 = now
        self.i = 0
        self.keys = sorted(self.spec['keys'], key=lambda k: k[0])
        self.tweens = {}                                   # who -> (t0, dur, x_from, x_to, ease, ghosts)
        self.trails = []                                   # (t0, who/anchor (x, y), facing, spec)
        self.ink = None                                    # (t0, x, y)
        self.lines = None                                  # (kind, until, x, y)
        self.released = set()
        self.done = False
        self.hits = 0
        self.el = {r: element_for(arena.f[self.slot[r]].atlas) for r in 'AD'}
        A = arena.f[att].atlas                              # striking distance from the attacker's own longest cut
        reach = 0.0
        for m in strikes_ranked(A)[:3]:
            try:
                reach = max(reach, float(A.anim[m].get('reach') or 0) / max(1, getattr(A, 'res', 1)))
            except (TypeError, ValueError):
                pass
        self.reach = min(200.0, max(140.0, reach * 4.0 * 0.9 + 60.0))

    def body(self, role):
        return self.arena.f[self.slot[role]]

    def world_x(self, x):
        return self.ox + self.s * x

    def tick(self, now):
        el = now - self.t0
        while self.i < len(self.keys) and self.keys[self.i][0] <= el:
            self._apply(self.keys[self.i], now)
            self.i += 1
        for role, tw in list(self.tweens.items()):
            t0, dur, x0, x1, ease, ghosts = tw
            k = 1.0 if dur <= 0 else min(1.0, (now - t0) / dur)
            b = self.body(role)
            b.x = x0 + (x1 - x0) * EASES[ease](k)
            if ghosts:
                self._ghost(b, now)
            if k >= 1.0:
                del self.tweens[role]
        for role in 'AD':
            b = self.body(role)
            if role not in self.released:
                b.y, b.vx, b.vy = self.y, 0.0, 0.0
                b.hover, b.fly_until, b.target, b.grounded = True, now + 1.0, None, False
        if el >= self.spec['dur']:
            self.finish(now)

    def finish(self, now):
        if self.done:
            return
        self.done = True
        for role in 'AD':
            b = self.body(role)
            b.alpha = None
            if role not in self.released:
                b.pose = None
                b.hover, b.fly_until = False, 0.0
                b.y, b.grounded = self.y, True
                if not b.down:
                    b.play('idle', now)

    def _ghost(self, b, now):
        if not b.trail or now - b.trail[-1][0] >= 0.02:
            b.trail.append((now, b.drawn_anim(), b.frame(now)[0], b.facing, b.x, b.y))

    def _apply(self, key, now):
        t, op, *args = key
        ar = self.arena
        if op == 'pose':
            role, slot = args
            if role in self.released:
                return
            b = self.body(role)
            r = resolve_slot(b.atlas, slot)
            if r is None:
                b.pose = None
                b.play('idle', now)
            elif r[0] == '@play':
                b.pose = None
                b.play(r[1], now)
            else:
                b.pose = r
        elif op == 'pos':
            role, p = args
            b = self.body(role)
            x1 = self.world_x(p['x'] if 'x' in p else self.spec['gap'] - self.reach + p['near'])
            if p.get('dur', 0) <= 0:
                b.x = x1
                b.trail.clear() if not p.get('ghosts') else None
            else:
                self.tweens[role] = (now, p['dur'], b.x, x1, p.get('ease', 'lin'), bool(p.get('ghosts')))
        elif op == 'alpha':
            role, a = args
            self.body(role).alpha = None if a >= 1.0 else a
        elif op == 'ghost':
            b = self.body(args[0])
            b.trail.append((now, b.drawn_anim(), b.frame(now)[0], b.facing, b.x, b.y))
        elif op == 'face':
            role, how = args
            b = self.body(role)
            other = self.body('D' if role == 'A' else 'A')
            b.facing = (1 if other.x >= b.x else -1) if how == 'toward' else -(1 if other.x >= b.x else -1)
        elif op == 'trail':
            role, spec = args
            b = self.body(role)
            if spec.get('world'):
                anchor = (self.ox, self.y)
                facing = self.s
            else:
                anchor = (b.x, self.y)
                facing = self.s                                 # the blade travels the attacker's way
            self.trails.append((now, anchor, facing, spec, self.el['A']))
            ar.fx_count += 1
        elif op == 'ink':
            if ar.flashes_on(now):
                b = self.body(args[0])
                self.ink = (now, b.x + self.s * 36, self.y - 96)
                ar.impact = (now, now + 0.18, self.slot[args[0]], 'ink')    # the struck fighter white on the ink; the other stays
                ar.note('ink', now)
                ar.note('impact', now, who=self.slot[args[0]])       # an ink frame is this set piece's impact frame
        elif op == 'hit':
            p = args[0]
            ar._setpiece_hit(self, p, now)
            self.hits += 1
        elif op == 'spark':
            b = self.body(args[0])
            ar.fxp.spawn_at('hit_light', now, b.x - self.s * 10, self.y - 100, self.s)
            ar.fx_count += 1
        elif op == 'shake':
            p = args[0]
            ar.fxp.add_shake(now, p['frames'], p['amp'] * ar.I['shake_k'])
        elif op == 'flash':
            if ar.flashes_on(now):
                ar.cam.color_flash(now, self.body(args[0]).atlas.accent, alpha=0.28, secs=0.12)
        elif op == 'cam':
            p = args[0]
            if 'box' in p:
                ar.cam.letterbox(now, now + p['box'])
            if 'punch' in p:
                b = self.body(p['punch'])
                ar.cam.punch(now, b.x, self.y - 100, hold=p.get('hold', 0.22))
                ar.note('zoom', now)
            if 'lines' in p:
                self.lines = ('h', self.t0 + p['until'], (self.body('A').x + self.body('D').x) / 2.0, self.y - 100)
            if 'radial' in p:
                b = self.body(p['radial'])
                ar.cam.radial = (now, self.t0 + p['until'], b.x, self.y - 100)

    def drawables(self, now, layer):
        """'back': speed-line backdrop and the ink splash; 'front': the painted trails."""
        ar = self.arena
        out = []
        if layer == 'back':
            if self.lines is not None and now < self.lines[1]:
                from .arena import _speedlines
                im = _speedlines(int(now * 20) % 3, True, 980, 300)
                out.append((im, int(self.lines[2] - im.width / 2), int(self.lines[3] - im.height / 2)))
            if self.ink is not None and now - self.ink[0] < 0.18:
                im = _cached(('ink', 0), lambda: ink_splash(330, 270, 5))
                if self.s < 0:
                    im = _cached(('inkflip', 0), lambda: ink_splash(330, 270, 5).transpose(Image.FLIP_LEFT_RIGHT))
                out.append((im, int(self.ink[1] - im.width / 2), int(self.ink[2] - im.height / 2)))
        keep = []
        for tr in self.trails:
            t0, anchor, facing, spec, element = tr
            el = now - t0
            total = spec['draw'] + spec['hold'] + spec['fade']
            if el >= total:
                continue
            keep.append(tr)
            if spec.get('layer', 'front') != layer:
                continue
            if el < spec['draw']:
                head, tail, alpha = 1.0 - (1.0 - el / spec['draw']) ** 2, 0.0, 1.0
            elif el < spec['draw'] + spec['hold']:
                head, tail, alpha = 1.0, 0.0, 1.0
            else:
                k = (el - spec['draw'] - spec['hold']) / spec['fade']
                head, tail, alpha = 1.0, 0.85 * k, 1.0 - k
            q = lambda v, n=16: round(v * n) / n
            key = ('rib', element, id(spec), facing, q(head), q(tail), round(alpha * 4) / 4.0)
            tint = ar.f[self.slot['A']].atlas.accent
            res = _cached(key, lambda: ribbon(element, spec, q(head), q(tail), max(0.25, round(alpha * 4) / 4.0), tint))
            if res is None:
                continue
            im, ox, oy = res
            if facing < 0:
                im = _cached(key + ('flip',), lambda: im.transpose(Image.FLIP_LEFT_RIGHT))
                ox = im.width - ox
            out.append((im, int(anchor[0] - ox), int(anchor[1] - oy)))
        self.trails = keep
        return out


_CACHE = {}


def _cached(key, make):
    if key not in _CACHE:
        if len(_CACHE) > 600:
            _CACHE.clear()
        _CACHE[key] = make()
    return _CACHE[key]
