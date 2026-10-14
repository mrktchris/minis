"""Move library: every move is a list of (Pose, ms) keyframes + metadata.

Names are API: the planner and the HUD refer to them.  Categories mirror a fighting-game move list:
locomotion / strikes / specials / defense / reactions / emotes / supers / pair.

V5 (fluid pass, docs/ANIMATION-NOTES.md): every strike is keyed anticipation (opposite direction, 60-100 ms) ->
smear (one frame, 40 ms, the limb drawn as its arc) -> contact hold (`hit_frame`, carries `hitstop_ms`) -> overshoot
(60-80 ms) -> settle.  No two consecutive frames share a duration.  Landings and crouches squash (`sq` < 1), launches
stretch (`sq` > 1), the chest breathes (`chest`), the head leads a hit and the arms follow a frame later.
"""
from __future__ import annotations
from dataclasses import replace
from rig import Pose

S0 = Pose()
HITSTOP = {1: 150, 2: 180, 3: 220}       # ms by power: light / medium / heavy (SF-style 9 / 11 / 13 frames at 60 fps)


def p(**kw):
    return replace(S0, **kw)


def M(frames, loop=False, cat='', desc='', **meta):
    """A move.  Derives `smear_frames` from the poses and a default `hitstop_ms` from `power` when it has a hit_frame."""
    sm = [i for i, (ps, _) in enumerate(frames) if ps.smear_f or ps.smear_b or ps.smear_ff or ps.smear_fb]
    if sm:
        meta.setdefault('smear_frames', sm)
    if 'hit_frame' in meta and 'hitstop_ms' not in meta:
        meta['hitstop_ms'] = HITSTOP.get(meta.get('power', 1), 150)
    return dict(frames=frames, loop=loop, cat=cat, desc=desc, **meta)


# ---------------------------------------------------------------------- signature templates
# A character's strike / special / super are built from these, so any roster entry can reuse them with its own
# name, description and effect (the planner reads the names from `signature`, never from the character's name).
def sig_spin(desc, **_):
    """Spinning kick: wind up facing away, the kick is one smear, the contact holds, the body overshoots past it."""
    return M([
        (p(dy=3, lean=12, sq=0.94, hf=(5, 2), hb=(3, 2)), 100),
        (p(dy=2, lean=0, turn=0.6, face='back', hf=(3, -2), hb=(-3, -2), ff=(3, 0), fb=(-3, 0)), 70),
        (p(dy=0, lean=-10, turn=0.35, face='back', hf=(-6, -4), hb=(-8, -4), ff=(2, 2), fb=(-2, 0)), 50),
        (p(dy=-1, lean=-18, turn=0.5, face='n', sq=1.04, hf=(-6, -6), hb=(-8, -3), ff=(14, 14), fb=(-1, 0), ang_f=-10, dx=2, smear_ff=(2, 2)), 40),
        (p(dy=-1, lean=-18, turn=0.8, face='n', hf=(-6, -6), hb=(-8, -3), ff=(15, 14), fb=(-1, 0), ang_f=-10, fx=(('spark', 'ff', 4, -1),)), 150),
        (p(dy=-1, lean=-20, turn=0.9, face='n', hf=(-7, -6), hb=(-8, -3), ff=(16, 13), fb=(-1, 0), ang_f=-12), 60),
        (p(dy=0, lean=-8, turn=0.8, ff=(10, 8), fb=(-3, 0)), 90),
        (p(dy=2, lean=6, ff=(8, 1)), 100)],
        cat='strike', desc=desc, hit_frame=4, power=3)


def sig_pound(desc, **_):
    """Leaping slam: squash, stretch into the air, hang, a smear down, the landing squashes and shakes."""
    return M([
        (p(dy=4, lean=14, sq=0.90, hf=(5, 3), hb=(3, 3)), 120),
        (p(dy=-8, lean=0, sq=1.10, hf=(7, -9), hb=(4, -10), ff=(4, 6), fb=(-3, 5)), 60),
        (p(dy=-12, lean=-4, sq=1.0, hf=(8, -11), hb=(5, -12), ff=(5, 7), fb=(-4, 6)), 150),
        (p(dy=6, lean=40, sq=0.96, head=(2, 2), hf=(7, 9), hb=(4, 10), fist_f=4, fist_b=4, ff=(9, 2), fb=(-6, 2), smear_f=(8, -11), smear_b=(5, -12)), 40),
        (p(dy=10, lean=45, sq=0.88, head=(2, 2), hf=(7, 8), hb=(4, 10), fist_f=4, fist_b=4, ff=(9, 0), fb=(-6, 0),
           fx=(('shock', 'abs', 38, 56), ('dust', 'ff', 4, -1), ('dust', 'fb', -5, -1))), 160),
        (p(dy=9, lean=42, sq=0.92, head=(2, 2), hf=(7, 8), hb=(4, 10), fist_f=4, fist_b=4, ff=(9, 0), fb=(-6, 0),
           fx=(('dust', 'ff', 6, -2), ('dust', 'fb', -7, -2))), 60),
        (p(dy=5, lean=20, hf=(6, 4), hb=(3, 5)), 100), (p(dy=2, lean=12), 110)],
        cat='strike', desc=desc, hit_frame=4, power=3, shake=dict(frames=4, amp=2))


def sig_throw(desc, **_):
    """Two-handed push; the projectile leaves on proj_frame (the contact hold after the smear)."""
    return M([
        (p(dy=2, lean=6, hf=(2, 3), hb=(1, 3), fx=(('charge', 'hf', 2, -1),)), 110),
        (p(dy=3, lean=2, sq=0.97, chest=1.04, hf=(-1, 4), hb=(-2, 4), fx=(('charge', 'hf', 0, -2), ('charge', 'hb', -1, -3))), 90),
        (p(dy=3, lean=16, hf=(12, -2), hb=(11, -1), ff=(10, 0), fb=(-8, 0), fist_f=4, fist_b=4, dx=2, smear_f=(-1, 4), smear_b=(-2, 4)), 40),
        (p(dy=2, lean=22, hf=(12, -2), hb=(11, -1), ff=(11, 0), fb=(-9, 0), fist_f=4, fist_b=4, fx=(('spark', 'hf', 4, 0),)), 180),
        (p(dy=2, lean=24, hf=(13, -2), hb=(12, -1), ff=(11, 0), fb=(-9, 0), fist_f=4, fist_b=4), 60),
        (p(lean=12, hf=(9, -1), hb=(6, 0)), 90), (S0, 100)],
        cat='special', desc=desc, proj_frame=3, power=2)


def sig_cast(desc, **_):
    """Type, hit ENTER, punch the projectile out on proj_frame."""
    return M([
        (p(dy=2, lean=6, hf=(6, 0), hb=(5, 1), fx=(('charge', 'hf', 4, -3),)), 110),
        (p(dy=3, lean=4, hf=(7, -1), hb=(6, 0), fx=(('charge', 'hf', 3, -4), ('charge', 'hb', -2, -3))), 80),
        (p(dy=2, lean=10, sq=0.97, hf=(9, 3), hb=(8, 2)), 60),
        (p(dy=3, lean=20, hf=(12, -1), hb=(6, 3), fist_f=4, dx=1, smear_f=(9, 3)), 40),
        (p(dy=3, lean=22, hf=(12, -1), hb=(6, 3), fist_f=4, fx=(('spark', 'hf', 4, -1),)), 180),
        (p(dy=2, lean=24, hf=(13, -1), hb=(6, 2)), 60), (p(lean=12), 90), (S0, 100)],
        cat='special', desc=desc, proj_frame=4, power=2)


def sig_rewind(desc, glyph='rewind', **_):
    """Super: snap back a second in time with an afterimage trail.  glyph: 'rewind' (<<) or 'bigglyph' (2x cap sigil)."""
    gfx = ('rewind', 'head', -4, -14) if glyph == 'rewind' else ('bigglyph', 'head', -1, -19)
    return M([
        (p(dy=3, lean=6, sq=0.95, hf=(4, 2), hb=(2, 2), fx=(gfx,)), 140),
        (p(dy=2, lean=-6, flash=True), 50),
        (p(dx=-10, dy=-1, lean=-18, sq=1.06, ff=(8, 3), fb=(-8, 2), hf=(3, -3), hb=(0, -3), ghost=(6, 12, 18), fx=(gfx,)), 60),
        (p(dx=-10, dy=-2, lean=-20, sq=1.04, ff=(9, 3), fb=(-9, 3), hf=(2, -4), hb=(-1, -4), ghost=(7, 14, 21)), 70),
        (p(dx=-10, dy=-1, lean=-14, ff=(8, 2), fb=(-8, 2), hf=(3, -3), hb=(0, -3), ghost=(7, 14)), 60),
        (p(dx=-4, dy=3, lean=4, sq=0.92, fx=(('dust', 'ff', 4, 1),)), 90),
        (p(dy=1, face='g', hf=(9, -2), hb=(4, 1), fx=(gfx,)), 200)],
        cat='super', desc=desc)


def sig_raise(desc, glyph='bigsigil', **_):
    """Super: raise a giant sigil and power up.  glyph: 'bigsigil' (Codex's hand-drawn $) or 'bigglyph'."""
    gfx = ('bigsigil', 'head', -1, -19) if glyph == 'bigsigil' else ('bigglyph', 'head', -1, -21)
    return M([
        (p(dy=3, lean=6, sq=0.95, hf=(5, 3), hb=(3, 3), fist_f=4, fist_b=4), 120),
        (p(dy=4, lean=4, sq=0.93, chest=1.04, hf=(5, 4), hb=(3, 4), aura=1, fx=(('charge', 'hf', 3, -3),)), 100),
        (p(dy=1, lean=0, sq=1.06, hf=(7, -10), hb=(5, -11), aura=2, face='g', fx=(gfx,)), 110),
        (p(dy=2, lean=0, sq=1.02, chest=1.08, hf=(7, -11), hb=(5, -12), aura=3, face='g', fx=(gfx, ('spark_s', 'hf', 0, -3))), 150),
        (p(dy=3, lean=8, chest=1.10, hf=(7, -9), hb=(5, -10), aura=4, face='g', fx=(gfx,)), 140),
        (p(dy=2, lean=4, aura=1), 90), (S0, 100)],
        cat='super', desc=desc)


TEMPLATES = {'spin': sig_spin, 'pound': sig_pound, 'throw': sig_throw, 'cast': sig_cast,
             'rewind': sig_rewind, 'raise': sig_raise}


def build_moves(character):
    """character: a roster.Character or its name.  Shared move set + the character's three signature moves."""
    import roster
    ch = roster.get(character)
    body = ch.body
    mv = {}

    # ------------------------------------------------------------------ locomotion
    # idle: nothing moves more than a pixel.  The chest expands, the head bobs a frame later, the guard drifts.
    idle_keys = [  # dy, chest, head_y, lean, hand lift, ms
        (1, 1.00, 0, 10, 0, 150), (1, 1.03, 0, 11, 0, 130), (2, 1.06, 1, 12, 1, 120), (2, 1.06, 1, 12, 1, 170),
        (2, 1.03, 1, 11, 1, 130), (1, 1.00, 0, 10, 0, 130), (1, 0.98, 0, 9, 0, 150), (1, 0.98, 0, 9, 0, 170)]
    mv['idle'] = M([(p(dy=dy, chest=ch_, head=(1, hy), lean=ln, hf=(8, -1 + lift), hb=(4, 1 + lift)), ms)
                    for dy, ch_, hy, ln, lift, ms in idle_keys],
                   loop=True, cat='locomotion', desc='Guard stance: breathing chest, head bob, drifting guard.')
    mv['idle_flourish'] = M([
        (p(dy=3, lean=16, sq=0.94, hf=(5, 3), hb=(2, 3), ff=(8, 0), fb=(-7, 0)), 100),
        (p(dy=-1, lean=4, sq=1.06, hf=(9, -5), hb=(6, -6), ff=(6, 2), fb=(-5, 1), face='g'), 80),
        (p(dy=0, lean=6, hf=(10, -3), hb=(7, -4), face='g'), 100),
        (p(dy=2, lean=14, sq=0.97, hf=(5, -3), hb=(8, -1), face='g'), 110),
        (p(dy=1, lean=10, hf=(8, -3), hb=(5, -4), face='g'), 110),
        (S0, 120)], cat='locomotion', desc='Shoulder roll and hop; plays every 6-10 s while idle.')
    # walk: contact / down / passing, twice.  Head lowest on the down frames, highest on passing; arms counter the legs.
    fa = [(6, 0), (2, 0), (-2, 0), (-6, 0), (0, 3), (4, 1)]
    wdy = [1, 2, 0, 1, 2, 0]
    wsq = [1.0, 0.97, 1.03, 1.0, 0.97, 1.03]
    whead = [0, 1, -1, 0, 1, -1]
    wlean = [12, 14, 11, 12, 14, 11]
    warm = [((9, -1), (3, 1)), ((8, 0), (4, 1)), ((6, 1), (5, 0)), ((5, 1), (6, 0)), ((6, 0), (5, 1)), ((8, -1), (4, 1))]
    walk = []
    for i in range(6):
        a, b = fa[i], fa[(i + 3) % 6]
        walk.append((p(dx=4, dy=wdy[i], sq=wsq[i], head=(1, whead[i]), lean=wlean[i], hf=warm[i][0], hb=warm[i][1], ff=a, fb=b, face='f'), 100))
    mv['walk'] = M(walk, loop=True, cat='locomotion', desc='Stride-locked walk: contact, down, passing; planted foot does not slide.', stride=24)
    mv['walk_back'] = M([(replace(f, dx=-4), 110) for f, _ in reversed(walk)], loop=True, cat='locomotion',
                        desc='Retreat while facing the opponent.', stride=24)
    mv['dash'] = M([
        (p(dy=3, lean=8, sq=0.90, hf=(4, 3), hb=(0, 2), ff=(6, 0), fb=(-4, 0)), 60),
        (p(dx=10, dy=-2, lean=28, sq=1.10, hf=(10, 0), hb=(2, 1), ff=(9, 4), fb=(-6, 2), ghost=(6,)), 60),
        (p(dx=10, dy=-3, lean=26, sq=1.04, hf=(9, 0), hb=(2, 1), ff=(8, 3), fb=(-7, 3), ghost=(7, 14), fx=(('dust', 'fb', -5, 3),)), 60),
        (p(dx=6, dy=2, lean=16, sq=0.92, hf=(8, -1), hb=(3, 1), ff=(10, 0), fb=(-2, 0), fx=(('dust', 'fb', -3, 1),)), 80),
        (p(dx=2, sq=1.02), 90)], cat='locomotion', desc='Hop-step forward to close distance.')
    mv['backdash'] = M([
        (p(dy=3, lean=4, sq=0.92, hf=(4, 2), hb=(1, 2)), 50),
        (p(dx=-9, dy=-2, lean=-16, sq=1.08, hf=(3, -3), hb=(0, -3), ff=(8, 3), fb=(-8, 2), ghost=(7, 14, 21)), 60),
        (p(dx=-9, dy=-3, lean=-20, sq=1.03, hf=(2, -4), hb=(-1, -4), ff=(9, 3), fb=(-9, 3), ghost=(8, 16)), 60),
        (p(dx=-5, dy=2, lean=-8, sq=0.92, hf=(4, 0), hb=(2, 1), ff=(10, 0), fb=(-4, 0), fx=(('dust', 'ff', 4, 1),)), 70),
        (p(dx=-1, sq=1.02), 100)], cat='defense', desc='Evasive hop back with an afterimage trail.')
    mv['turn'] = M([(p(lean=0, hf=(5, 2), hb=(5, 2), ff=(2, 0), fb=(-2, 0), turn=0.7, face='back'), 60), (S0, 60)],
                   cat='locomotion', desc='Pivot to face the other way.')
    mv['crouch'] = M([(p(dy=3, lean=14, sq=0.96, hf=(7, 1), hb=(3, 2), ff=(8, 0), fb=(-7, 0)), 60),
                      (p(dy=6, lean=18, sq=0.92, hf=(7, 2), hb=(3, 3), ff=(9, 0), fb=(-8, 0)), 120),
                      (p(dy=7, lean=18, sq=0.91, hf=(7, 2), hb=(3, 3), ff=(9, 0), fb=(-8, 0)), 120)],
                     loop=True, loop_range=(1, 2), cat='locomotion', desc='Low stance.')
    mv['jump'] = M([
        (p(dy=5, lean=15, sq=0.86, hf=(2, 4), hb=(-2, 4), ff=(8, 0), fb=(-7, 0)), 90),
        (p(dy=-5, lean=5, sq=1.12, hf=(6, -6), hb=(3, -7), ff=(4, 4), fb=(-3, 3)), 50),
        (p(dy=-10, lean=2, sq=1.04, hf=(7, -9), hb=(4, -10), ff=(5, 6), fb=(-4, 5)), 90),
        (p(dy=-12, lean=0, sq=1.0, hf=(7, -9), hb=(4, -10), ff=(5, 7), fb=(-4, 6), face='w'), 140),
        (p(dy=-6, lean=2, sq=1.04, hf=(8, -3), hb=(4, -4), ff=(6, 3), fb=(-5, 3)), 70),
        (p(dy=5, lean=14, sq=0.86, hf=(6, 2), hb=(2, 2), ff=(8, 0), fb=(-7, 0), fx=(('dust', 'ff', 5, 1), ('dust', 'fb', -6, 1))), 70),
        (p(dy=2, lean=10, sq=1.02), 90)],
        cat='locomotion', desc='Neutral jump: squash, stretch, hang, squash on landing.')

    # ------------------------------------------------------------------ strikes
    mv['jab'] = M([
        (p(dy=2, lean=4, hf=(3, 2), hb=(7, -2), ff=(6, 0), fb=(-7, 0)), 70),
        (p(dy=2, lean=2, sq=0.97, hf=(2, 3), hb=(7, -2), ff=(6, 0), fb=(-7, 0)), 50),
        (p(dy=2, lean=20, hf=(12, -2), hb=(4, -1), ff=(10, 0), fb=(-8, 0), fist_f=4, dx=3, smear_f=(2, 3)), 40),
        (p(dy=2, lean=22, hf=(13, -2), hb=(4, -1), ff=(10, 0), fb=(-8, 0), fist_f=4, fx=(('spark', 'hf', 3, 0),)), 140),
        (p(dy=2, lean=24, hf=(12, -1), hb=(4, -1), ff=(10, 0), fb=(-8, 0), fist_f=4), 60),
        (p(dy=1, lean=14, hf=(9, -1), hb=(4, 1), ff=(8, 0), fb=(-6, 0)), 70),
        (S0, 100)],
        cat='strike', desc='Fast lead-hand strike. Light hit, small hit-stop.', hit_frame=3, power=1)
    mv['cross'] = M([
        (p(dy=2, lean=-4, chest=1.05, hf=(7, -2), hb=(-2, 3), fb=(-8, 0)), 90),
        (p(dy=3, lean=-6, sq=0.97, hf=(7, -2), hb=(-3, 3), ff=(8, 0), fb=(-9, 0)), 60),
        (p(dy=3, lean=24, hf=(8, -3), hb=(12, -3), ff=(11, 0), fb=(-9, 0), fist_b=4, dx=4, smear_b=(-3, 3)), 40),
        (p(dy=3, lean=28, hf=(8, -3), hb=(13, -3), ff=(11, 0), fb=(-9, 0), fist_b=4, fx=(('spark', 'hb', 3, 0),)), 160),
        (p(dy=3, lean=30, hf=(8, -3), hb=(13, -2), ff=(11, 0), fb=(-9, 0), fist_b=4), 60),
        (p(dy=2, lean=16, hf=(8, -2), hb=(8, -1), ff=(10, 0), fb=(-8, 0)), 80),
        (S0, 100)], cat='strike', desc='Rear-hand power punch. Medium hit, forces a block-stagger.', hit_frame=3, power=2)
    mv['uppercut'] = M([
        (p(dy=4, lean=12, hf=(4, 4), hb=(5, 0), ff=(8, 0), fb=(-7, 0)), 90),
        (p(dy=7, lean=16, sq=0.90, hf=(5, 8), hb=(5, -1), ff=(9, 0), fb=(-8, 0)), 70),
        (p(dy=-2, lean=2, sq=1.08, hf=(9, -12), hb=(5, -2), ff=(8, 1), fb=(-6, 0), fist_f=4, dx=2, smear_f=(5, 8)), 40),
        (p(dy=-3, lean=2, sq=1.06, hf=(9, -13), hb=(5, -2), ff=(7, 3), fb=(-5, 2), fist_f=4, fx=(('spark', 'hf', 0, -4),)), 150),
        (p(dy=-1, lean=-2, sq=1.03, hf=(8, -14), hb=(5, -2), ff=(7, 2), fb=(-5, 1), fist_f=4), 60),
        (p(dy=2, lean=8, hf=(8, -6), hb=(4, 0)), 90),
        (S0, 100)], cat='strike', desc='Rising launcher. Pops the opponent up.', hit_frame=3, power=2)
    mv['low_kick'] = M([
        (p(dy=3, lean=6, hf=(2, 3), hb=(0, 2)), 80),
        (p(dy=6, lean=-4, sq=0.95, hf=(-2, 5), hb=(-5, 3), ff=(3, 1), fb=(-9, 0)), 60),
        (p(dy=7, lean=-8, hf=(-3, 6), hb=(-7, 4), ff=(14, 0), fb=(-8, 0), dx=3, smear_ff=(3, 1)), 40),
        (p(dy=7, lean=-8, hf=(-3, 6), hb=(-7, 4), ff=(14, 0), fb=(-8, 0), fx=(('spark', 'ff', 4, -1),)), 140),
        (p(dy=7, lean=-10, hf=(-4, 6), hb=(-7, 4), ff=(15, 0), fb=(-8, 0)), 60),
        (p(dy=4, lean=0, hf=(2, 4), hb=(0, 3), ff=(10, 0), fb=(-8, 0)), 90),
        (S0, 100)], cat='strike', desc='Sweep along the ground. Trips guard-high opponents.', hit_frame=3, power=1)
    mv['roundhouse'] = M([
        (p(dy=1, lean=-2, hf=(5, 2), hb=(2, 2), ff=(6, 8), fb=(-4, 0)), 100),
        (p(dy=0, lean=-10, sq=0.96, hf=(-2, -5), hb=(-6, 0), ff=(4, 11), fb=(-3, 0)), 70),
        (p(dy=0, lean=-14, sq=1.03, hf=(-4, -6), hb=(-8, -1), ff=(15, 14), fb=(-3, 0), dx=2, ang_f=-15, smear_ff=(4, 11)), 40),
        (p(dy=0, lean=-14, hf=(-4, -6), hb=(-8, -1), ff=(15, 14), fb=(-3, 0), ang_f=-15, fx=(('spark', 'ff', 4, -1),)), 160),
        (p(dy=0, lean=-16, hf=(-5, -6), hb=(-8, -1), ff=(16, 13), fb=(-3, 0), ang_f=-18), 60),
        (p(dy=1, lean=-8, hf=(0, -2), hb=(-4, 1), ff=(12, 10), fb=(-4, 0)), 80),
        (p(dy=1, lean=4, ff=(8, 2)), 90),
        (S0, 100)], cat='strike', desc='High kick. Heavy hit, big hit-stop.', hit_frame=3, power=3)
    for role in ('strike', 'special'):                 # same row order as before: strike, special after the shared strikes
        name = ch.signature[role]
        tpl, desc, opts = ch.sig_moves[name]
        mv[name] = TEMPLATES[tpl](desc, **opts)

    # ------------------------------------------------------------------ defense
    mv['block'] = M([(p(dy=2, lean=4, hf=(4, -6), hb=(3, -5)), 60),
                     (p(dy=3, lean=2, chest=1.03, hf=(6, -7), hb=(4, -7), ff=(8, 0), fb=(-7, 0), fist_f=4), 120),
                     (p(dy=3, lean=1, chest=1.0, hf=(6, -8), hb=(4, -7), ff=(8, 0), fb=(-7, 0), fist_f=4), 120),
                     (p(dy=2, lean=6, hf=(5, -5), hb=(3, -3)), 80)],
                    loop=True, loop_range=(1, 2), cat='defense', desc='High guard.')
    mv['block_hit'] = M([(p(dy=3, lean=-4, sq=0.96, hf=(6, -7), hb=(4, -7), fist_f=4, fx=(('block', 'hf', 4, -3),), dx=-2), 50),
                         (p(dy=3, lean=-2, sq=0.98, hf=(5, -7), hb=(3, -7), fist_f=4, dx=-1), 80),
                         (p(dy=3, lean=3, hf=(6, -7), hb=(4, -7), fist_f=4), 90)],
                        cat='defense', desc='Guard absorbs a hit with a flash.')
    mv['crouch_block'] = M([(p(dy=7, lean=14, sq=0.92, hf=(8, -1), hb=(6, 0), ff=(9, 0), fb=(-8, 0), fist_f=4), 80),
                            (p(dy=8, lean=14, sq=0.91, hf=(8, -1), hb=(6, 0), ff=(9, 0), fb=(-8, 0), fist_f=4), 120)],
                           loop=True, loop_range=(0, 1), cat='defense', desc='Low guard.')
    mv['parry'] = M([(p(dy=2, lean=4, hf=(4, -6), hb=(3, 1)), 50),
                     (p(dy=2, lean=12, hf=(12, -3), hb=(4, 1), face='g', smear_f=(4, -6), fx=(('block', 'hf', 3, -1),)), 90),
                     (p(dy=2, lean=14, hf=(13, -2), hb=(4, 1), face='g'), 60),
                     (p(dy=1, lean=10, hf=(9, -2), face='g'), 100)],
                    cat='defense', desc='Swat the strike aside with a flash. Counter window.', hit_frame=1)

    # ------------------------------------------------------------------ reactions (the head leads, the arms follow)
    mv['hit'] = M([(p(flash=True, lean=-6, head=(-3, -1), hf=(8, -1), hb=(4, 1), face='h', dx=-2), 50),
                   (p(lean=-16, head=(-4, 0), hf=(7, 1), hb=(3, 2), ff=(6, 0), fb=(-8, 0), face='h', dx=-2), 70),
                   (p(lean=-12, head=(-2, 0), hf=(3, 4), hb=(0, 4), ff=(6, 0), fb=(-8, 0), face='h', dx=-1), 80),
                   (p(lean=2, head=(0, 0), hf=(6, 1), hb=(3, 1), face='h'), 70), (S0, 90)],
                  cat='reaction', desc='Head snap first, body follows, overshoots forward, settles.')
    mv['hit_heavy'] = M([(p(flash=True, lean=-12, head=(-4, -1), hf=(7, 0), hb=(3, 2), face='h', dx=-4, dy=0), 50),
                         (p(lean=-28, head=(-5, -1), sq=1.04, hf=(4, 3), hb=(1, 4), ff=(8, 2), fb=(-4, 1), face='h', dx=-5), 70),
                         (p(lean=-30, head=(-4, 0), hf=(1, 6), hb=(-2, 6), ff=(9, 1), fb=(-3, 0), face='h', dx=-4), 90),
                         (p(lean=-18, head=(-2, 0), hf=(3, 5), hb=(0, 5), ff=(9, 1), fb=(-3, 0), face='h', dx=-3), 90),
                         (p(lean=6, dy=3, sq=0.95, face='o', hf=(6, 2), hb=(3, 3)), 90), (S0, 100)],
                        cat='reaction', desc='Slides back, arms fly, wobbles forward, settles.')
    ldy = body.lie_dy                              # hips on the same row when lying, whatever the leg length
    lying = dict(lean=-90, dy=ldy, head=(-2, -2), hf=(-4, 3), hb=(-7, 1), eb_f='up', eb_b='up', ff=(12, 1), fb=(10, 0), face='x', cx=5)
    mv['knockdown'] = M([
        (p(flash=True, lean=-14, head=(-4, -1), hf=(5, 2), hb=(1, 3), face='h', dx=-4), 50),
        (p(lean=-30, dy=-3, sq=1.08, head=(-5, -1), hf=(1, 5), hb=(-2, 5), ff=(8, 3), fb=(-4, 2), face='h', dx=-5), 70),
        (p(lean=-60, dy=1, sq=1.0, head=(-3, 0), hf=(0, 6), hb=(-3, 5), ff=(10, 6), fb=(7, 5), face='h', dx=-5, cx=2), 90),
        (p(**{**lying, 'lean': -82, 'dy': ldy - 1, 'cx': 4}, sq=0.90, dx=-2, fx=(('dust', 'hip', -2, 5), ('dust', 'hip', 6, 4))), 70),
        (p(**{**lying, 'dy': ldy - 2}, sq=0.96), 60),
        (p(**lying, fx=(('dust', 'hip', -6, 4),)), 110), (p(**lying), 160)],
        cat='reaction', desc='Falls through an arc, flattens on impact, bounces once.', shake=dict(frames=3, amp=1))
    mv['getup'] = M([
        (p(**lying), 160),
        (p(**{**lying, 'lean': -80, 'dy': ldy - 1, 'hf': (-2, 6), 'face': 'o'}), 100),
        (p(lean=-50, dy=8, sq=1.05, hf=(3, 9), hb=(0, 9), ff=(10, 3), fb=(6, 2), face='o', cx=3), 90),
        (p(lean=-10, dy=7, sq=0.92, hf=(6, 8), hb=(3, 8), ff=(9, 0), fb=(-7, 0), face='f', cx=1, fx=(('dust', 'ff', 4, 1),)), 80),
        (p(lean=8, dy=2, sq=1.03, ff=(8, 0), fb=(-7, 0)), 70), (S0, 90)], cat='reaction', desc='Kip up from a knockdown.')
    stars = [(('star', 'head', -7, -9), ('star', 'head', 6, -8), ('star', 'head', 0, -11)),
             (('star', 'head', 7, -9), ('star', 'head', -6, -8), ('star', 'head', 1, -11)),
             (('star', 'head', 0, -9), ('star', 'head', 8, -10), ('star', 'head', -8, -10))]
    mv['dizzy'] = M([(p(dy=2, lean=6, head=(2, 1), tilt=8, face='x', hf=(4, 5), hb=(1, 5), fx=stars[0]), 130),
                     (p(dy=2, lean=-2, head=(0, 1), tilt=-6, face='x', hf=(4, 5), hb=(1, 5), fx=stars[1]), 130),
                     (p(dy=2, lean=8, head=(2, 1), tilt=8, face='x', hf=(4, 5), hb=(1, 5), fx=stars[2]), 130),
                     (p(dy=2, lean=0, head=(1, 1), tilt=-8, face='x', hf=(4, 5), hb=(1, 5), fx=stars[0]), 130)],
                    loop=True, cat='reaction', desc='Stagger with stars. Used when a fighter is near its limit.')
    ko_stars = [(('star', 'head', -3, -8), ('star', 'head', 4, -9), ('star', 'head', -9, -7)),
                (('star', 'head', 2, -9), ('star', 'head', -5, -8), ('star', 'head', 6, -7)),
                (('star', 'head', 5, -8), ('star', 'head', -8, -9), ('star', 'head', -2, -10))]
    mv['ko'] = M([
        (p(flash=True, lean=-14, head=(-4, -1), hf=(5, 2), hb=(1, 3), face='h', dx=-4), 50),
        (p(lean=-30, dy=-3, sq=1.08, head=(-5, -1), hf=(1, 5), hb=(-2, 5), ff=(8, 3), fb=(-4, 2), face='h', dx=-5), 70),
        (p(lean=-60, dy=1, head=(-3, 0), hf=(0, 6), hb=(-3, 5), ff=(10, 6), fb=(7, 5), face='h', dx=-5, cx=2), 90),
        (p(**{**lying, 'lean': -82, 'dy': ldy - 1, 'cx': 4}, sq=0.90, dx=-2), 80),
        (p(**lying, fx=ko_stars[0]), 200), (p(**lying, fx=ko_stars[1]), 200), (p(**lying, fx=ko_stars[2]), 200)],
        loop=True, loop_range=(4, 6), cat='reaction', desc='Knocked out; stars orbit. Shown when a plan limit is hit.')

    # ------------------------------------------------------------------ emotes / states
    mv['victory'] = M([
        (p(dy=4, lean=10, sq=0.88, hf=(5, 3), hb=(3, 3), face='w'), 120),
        (p(dy=-6, lean=0, sq=1.12, hf=(5, -12), hb=(3, 2), ff=(5, 3), fb=(-4, 2), face='w', fx=(('star', 'head', -8, -7),)), 50),
        (p(dy=-10, lean=-4, sq=1.0, hf=(6, -13), hb=(2, 3), ff=(5, 5), fb=(-4, 4), face='w', fx=(('star', 'head', -9, -6), ('star', 'head', 8, -8))), 140),
        (p(dy=-4, lean=-2, sq=1.05, hf=(6, -13), hb=(2, 3), ff=(5, 3), fb=(-4, 2), face='w'), 60),
        (p(dy=4, lean=4, sq=0.88, hf=(5, -12), hb=(3, 2), face='w', fx=(('dust', 'ff', 5, 1), ('dust', 'fb', -6, 1))), 70),
        (p(dy=0, lean=0, sq=1.03, hf=(5, -13), hb=(4, 3), face='w'), 80),
        (p(dy=1, lean=0, hf=(5, -12), hb=(4, 3), face='w'), 300)], cat='emote', desc='Fist pump. Played when a task finishes.')
    mv['victory2'] = M([(p(dy=2, lean=0, chest=1.04, hf=(5, -7), hb=(2, -7), eb_f='up', eb_b='up', face='g', fist_f=4, fist_b=4), 140),
                        (p(dy=1, lean=0, chest=1.10, hf=(5, -8), hb=(2, -8), eb_f='up', eb_b='up', face='g', fist_f=4, fist_b=4), 140),
                        (p(dy=2, lean=0, chest=1.04, hf=(5, -7), hb=(2, -7), eb_f='up', eb_b='up', face='g', fist_f=4, fist_b=4), 140),
                        (p(dy=1, lean=0, chest=1.10, hf=(5, -8), hb=(2, -8), eb_f='up', eb_b='up', face='g', fist_f=4, fist_b=4), 140)],
                       cat='emote', desc='Flex. The big-win version.')
    mv['taunt'] = M([(p(lean=6, hf=(10, -1), open_f=True, face='g'), 120), (p(lean=6, hf=(9, 0), face='g'), 120),
                     (p(lean=6, hf=(10, -1), open_f=True, face='g'), 120), (p(lean=6, hf=(9, 0), face='g'), 120),
                     (p(lean=8, head=(2, 0), tilt=-6, hf=(5, 0), face='g'), 140), (S0, 100)],
                    cat='emote', desc="Come-on beckon. Used when the other fighter's idle too long.")
    mv['bow'] = M([(p(dy=1, lean=14, hf=(3, 3), hb=(2, 3), ff=(4, 0), fb=(-3, 0), face='n'), 150),
                   (p(dy=2, lean=35, head=(3, 3), hf=(2, 5), hb=(1, 5), ff=(4, 0), fb=(-3, 0), face='z'), 200),
                   (p(dy=2, lean=36, head=(3, 3), hf=(2, 5), hb=(1, 5), ff=(4, 0), fb=(-3, 0), face='z'), 250),
                   (p(dy=1, lean=14, hf=(3, 3), hb=(2, 3), ff=(4, 0), fb=(-3, 0), face='n'), 150)],
                  cat='pair', desc='Respect bow before and after a bout.')
    mv['fistbump'] = M([(p(lean=6, hf=(4, 0), face='n'), 100), (p(lean=10, hf=(11, 0), fist_f=4, face='n', smear_f=(4, 0)), 60),
                        (p(lean=12, hf=(12, 0), fist_f=4, fx=(('spark_s', 'hf', 3, -1),), face='w'), 160),
                        (p(lean=10, hf=(7, 0), face='w'), 100)],
                       cat='pair', desc='Fist bump. Ends every bout.', hit_frame=2)
    mv['highfive'] = M([(p(dy=3, lean=10, sq=0.92, hf=(5, 2)), 100),
                        (p(dy=-3, lean=4, sq=1.08, hf=(9, -10), open_f=True, ff=(6, 3), fb=(-5, 2), face='w'), 70),
                        (p(dy=-5, lean=2, hf=(11, -11), open_f=True, ff=(6, 4), fb=(-5, 3), face='w', fx=(('spark', 'hf', 3, -2),)), 140),
                        (p(dy=2, lean=8, sq=0.94, hf=(8, -8), open_f=True, face='w'), 90), (S0, 100)],
                       cat='pair', desc='Jump high-five. Both finished at the same time.', hit_frame=2)
    mv['wave'] = M([(p(lean=2, hf=(7, -11), open_f=True, face='w'), 120), (p(lean=2, hf=(9, -12), open_f=True, face='w'), 120),
                    (p(lean=2, hf=(7, -11), open_f=True, face='w'), 120), (p(lean=2, hf=(5, -12), open_f=True, face='w'), 120)],
                   cat='emote', desc='Greeting wave.')
    mv['thumbs_up'] = M([(p(lean=4, hf=(6, -1), face='n'), 100), (p(lean=4, hf=(9, -3), face='w', fx=(('thumb', 'hf', 0, -2),)), 160),
                         (p(lean=4, hf=(9, -3), face='b', fx=(('thumb', 'hf', 0, -2),)), 120),
                         (p(lean=4, hf=(9, -3), face='w', fx=(('thumb', 'hf', 0, -2),)), 220)], cat='emote', desc='Approved.')
    mv['facepalm'] = M([(p(lean=8, hf=(6, -3), face='n'), 100), (p(lean=8, head=(1, 2), hf=(2, -9), face='b'), 120),
                        (p(lean=8, head=(1, 2), hf=(2, -9), face='b', fx=(('sweat', 'head', 7, -4),)), 140),
                        (p(lean=8, head=(1, 2), hf=(2, -9), face='b', fx=(('sweat', 'head', 7, -2),)), 200)],
                       cat='emote', desc='Something broke.')
    mv['shrug'] = M([(p(lean=2, dy=2, hf=(6, 3), hb=(2, 3), eb_f='up', eb_b='up', head=(0, 1), tilt=-6, face='n'), 120),
                     (p(lean=2, dy=1, hf=(6, 2), hb=(2, 2), eb_f='up', eb_b='up', head=(0, 0), tilt=-6, face='n', fx=(('qmark', 'head', 6, -13),)), 160),
                     (p(lean=2, dy=2, hf=(6, 3), hb=(2, 3), eb_f='up', eb_b='up', head=(0, 1), tilt=-6, face='n', fx=(('qmark', 'head', 6, -13),)), 160),
                     (S0, 100)], cat='emote', desc='Unsure.')
    mv['work'] = M([(p(dy=2, lean=14, hf=(11, -2), hb=(3, 0), ff=(8, 0), fb=(-6, 0), fist_f=4, smear_f=(6, 0)), 80),
                    (p(dy=1, lean=10, hf=(6, 0), hb=(5, -1)), 100),
                    (p(dy=2, lean=14, hf=(5, 0), hb=(11, -2), ff=(7, 0), fb=(-7, 0), fist_b=4, smear_b=(5, -1)), 80),
                    (p(dy=1, lean=10, hf=(7, -1), hb=(5, 0), ff=(8, 2), fb=(-6, 0)), 100),
                    (p(dy=2, lean=14, hf=(11, -2), hb=(3, 0), fist_f=4, smear_f=(7, -1)), 80),
                    (p(dy=1, lean=10, hf=(6, 0), hb=(5, -1)), 100)],
                   loop=True, cat='state', desc='Shadowboxing: the fighter is working.')
    mv['type'] = M([(p(dy=2, lean=14, head=(2, 2), hf=(9, 2), hb=(7, 3), face='f'), 90), (p(dy=2, lean=14, head=(2, 2), hf=(9, 4), hb=(7, 1), face='f'), 90),
                    (p(dy=2, lean=14, head=(2, 2), hf=(9, 2), hb=(7, 3), face='f'), 90), (p(dy=2, lean=14, head=(2, 3), hf=(9, 3), hb=(7, 4), face='f'), 90),
                    (p(dy=2, lean=14, head=(2, 2), hf=(9, 4), hb=(7, 1), face='f'), 90), (p(dy=2, lean=14, head=(2, 2), hf=(9, 2), hb=(7, 3), face='f'), 90)],
                   loop=True, cat='state', desc='Typing on an air keyboard. Used for long edit streaks.')
    mv['review'] = M([(p(dy=1, lean=16, head=(2, 1), hf=(3, -9), hb=(10, -3), doc='hb', face='f'), 120),
                      (p(dy=1, lean=16, head=(2, 2), hf=(3, -9), hb=(10, -3), doc='hb', face='f'), 120),
                      (p(dy=1, lean=16, head=(2, 1), hf=(3, -9), hb=(10, -3), doc='hb', face='n'), 120),
                      (p(dy=1, lean=16, head=(2, 2), hf=(3, -9), hb=(10, -2), doc='hb', face='f'), 120),
                      (p(dy=1, lean=14, head=(1, 1), hf=(4, -9), hb=(10, -3), doc='hb', face='g'), 120),
                      (p(dy=1, lean=16, head=(2, 1), hf=(3, -9), hb=(10, -3), doc='hb', face='f'), 120)],
                     loop=True, cat='state', desc='Strokes chin, reads the diff. Played when visiting a finished partner.')
    mv['wait'] = M([(p(dy=1, lean=4, hf=(-1, 9), hb=(-2, 9), eb_f='fwd', eb_b='back', face='n'), 150),
                    (p(dy=1, lean=4, hf=(-1, 9), hb=(-2, 9), eb_f='fwd', eb_b='back', ff=(7, 3), face='n'), 150),
                    (p(dy=1, lean=4, hf=(-1, 9), hb=(-2, 9), eb_f='fwd', eb_b='back', face='b'), 150),
                    (p(dy=1, lean=4, head=(0, 0), hf=(-1, 9), hb=(-2, 9), eb_f='fwd', eb_b='back', ff=(7, 3), face='n'), 150)],
                   loop=True, cat='state', desc='Foot tap, hands on hips: waiting for input or approval.')
    sdy = body.sit_dy                              # keep the hips the same height above the floor for every body
    sit = dict(dy=sdy, lean=24, head=(3, 3), tilt=10, hf=(8, 10), hb=(6, 11), ff=(8, 0), fb=(5, 0), kb_f='up', kb_b='up', face='z')
    mv['sleep'] = M([(p(**sit, chest=1.0, fx=(('zzz', 'head', 8, -9, 0),)), 600), (p(**{**sit, 'dy': sdy - 1, 'lean': 26}, chest=1.05, fx=(('zzz', 'head', 9, -11, 1),)), 600),
                     (p(**sit, chest=1.0, fx=(('zzz', 'head', 10, -13, 0),)), 600), (p(**{**sit, 'dy': sdy - 1, 'lean': 26}, chest=1.05, fx=(('zzz', 'head', 8, -10, 1),)), 600)],
                    loop=True, cat='state', desc='Sitting nap. No session in 30 minutes.')
    mv['wake'] = M([(p(**sit), 200), (p(dy=8, lean=10, sq=0.95, hf=(6, -4), hb=(3, -5), face='z'), 160),
                    (p(dy=3, lean=0, sq=1.08, chest=1.06, hf=(6, -12), hb=(3, -13), face='o', eb_f='up', eb_b='up'), 200), (S0, 140)],
                   cat='state', desc='Stretch and yawn.')
    mv['powerup'] = M([(p(dy=5 + (i % 2), lean=8, chest=1.0 + 0.04 * i, sq=0.97, hf=(4, 5), hb=(2, 5), fist_f=4, fist_b=4, face='f', aura=i + 1,
                          fx=(('charge', 'hf', 2 + i, -4 - i),)), 80) for i in range(5)],
                      loop=True, loop_range=(1, 4), cat='state', desc='Charging up. Context past 70%.')
    mv['rage'] = M([(p(dy=1 + (i % 2), lean=12, chest=1.06 + 0.03 * (i % 2), face='f', aura=i + 5, hf=(8, -2), hb=(5, 0)), 80) for i in range(4)],
                   loop=True, cat='state', desc='Aura on. Context past 85%.')

    # ------------------------------------------------------------------ supers
    name = ch.signature['super']
    tpl, desc, opts = ch.sig_moves[name]
    mv[name] = TEMPLATES[tpl](desc, **opts)

    # ------------------------------------------------------------------ paired moves
    mv['handoff_give'] = M([(p(lean=8, hf=(5, 0), hb=(5, 1), face='n'), 100),
                            (p(lean=10, hf=(11, -2), doc='hf', face='n'), 120),
                            (p(lean=10, hf=(11, -2), doc='hf', face='n'), 300),
                            (p(lean=10, hf=(11, -2), face='n'), 100),
                            (p(lean=8, hf=(7, 0), face='w'), 120), (S0, 100)],
                           cat='pair', desc='Holds out a finished diff. The writer hands work to the reviewer.', release_frame=3)
    mv['handoff_take'] = M([(S0, 100), (p(lean=10, hf=(10, -1), open_f=True, face='n'), 120),
                            (p(lean=12, hf=(11, -2), open_f=True, doc='hf', face='n'), 120),
                            (p(lean=8, hf=(6, -3), doc='hf', face='f'), 140),
                            (p(lean=14, head=(2, 1), hf=(5, -5), hb=(8, -3), doc='hf', face='f'), 200), (S0, 100)],
                           cat='pair', desc='Reaches out and takes the diff.', grab_frame=2)
    mv['console'] = M([(p(lean=8, hf=(10, -2), face='n'), 160), (p(lean=8, hf=(11, -3), face='n'), 160),
                       (p(lean=8, hf=(10, -2), face='n'), 160), (p(lean=8, hf=(11, -3), face='w'), 160)],
                      cat='pair', desc='Pats the other fighter on the shoulder after a KO.')

    # ------------------------------------------------------------------ V4 ultimate (+ support), always the LAST rows
    import ultimates
    return ultimates.add_ultimate(mv, ch)
