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
# V6 keying (docs/ANIMATION-NOTES.md section 6): a long, held wind-up (two keys, the second a tension hold), ONE smear
# frame where the weapon sweeps its crescent, the contact hold, then a held follow-through on the heavy ones.  `wa` puts
# the weapon where the swing needs it (back over the shoulder on the wind-up, through the target on contact).
def sig_spin(desc, **_):
    """Spinning kick: turn the back to the target, the kick is one smear, the blade trails round with it, a long hold."""
    return M([
        (p(dy=3, lean=12, sq=0.94, hf=(5, 3), wa=-120, turn=0.85), 140),
        (p(dy=2, lean=0, turn=0.6, face='back', hf=(3, -2), hb=(-3, -2), ff=(3, 0), fb=(-3, 0), wa=-150), 80),
        (p(dy=0, lean=-10, turn=0.35, face='back', hf=(-6, -4), hb=(-8, -4), ff=(2, 2), fb=(-2, 0), wa=-170), 50),
        (p(dy=-1, lean=-18, turn=0.5, face='n', sq=1.04, hf=(-6, -6), hb=(-8, -3), ff=(14, 14), fb=(-1, 0), ang_f=-10, dx=4, wa=-160,
           smear_ff=(2, 2)), 40),
        (p(dy=-1, lean=-18, turn=0.8, face='n', hf=(-6, -6), hb=(-8, -3), ff=(15, 14), fb=(-1, 0), ang_f=-10, wa=-155,
           fx=(('spark', 'ff', 4, -1),)), 160),
        (p(dy=-1, lean=-20, turn=0.9, face='n', hf=(-7, -6), hb=(-8, -3), ff=(16, 13), fb=(-1, 0), ang_f=-12, wa=-150), 260),
        (p(dy=0, lean=-8, turn=0.8, ff=(10, 8), fb=(-3, 0)), 100),
        (p(dy=2, lean=6, ff=(8, 1)), 90)],
        cat='strike', desc=desc, hit_frame=4, power=3)


def sig_pound(desc, **_):
    """Leaping slam: squash, leap with the weapon overhead, hang, smash it down in one smear, shake, hold the landing."""
    return M([
        (p(dy=4, lean=14, sq=0.90, hf=(5, 4), wa=-130), 150),
        (p(dy=-8, lean=0, sq=1.10, hf=(6, -9), eb_f='up', wa=-140, ff=(4, 6), fb=(-3, 5)), 60),
        (p(dy=-12, lean=-6, sq=1.0, hf=(5, -11), eb_f='up', wa=-150, ff=(5, 7), fb=(-4, 6)), 180),
        (p(dy=6, lean=40, sq=0.96, head=(2, 2), hf=(9, 7), wa=55, fist_f=4, ff=(9, 2), fb=(-6, 2), dx=4, smear_f=(5, -11)), 40),
        (p(dy=10, lean=45, sq=0.88, head=(2, 2), hf=(9, 7), wa=62, fist_f=4, ff=(9, 0), fb=(-6, 0),
           fx=(('shock', 'abs', 38, 56), ('dust', 'ff', 4, -1), ('dust', 'fb', -5, -1))), 160),
        (p(dy=9, lean=42, sq=0.92, head=(2, 2), hf=(9, 7), wa=64, fist_f=4, ff=(9, 0), fb=(-6, 0),
           fx=(('dust', 'ff', 6, -2), ('dust', 'fb', -7, -2))), 280),
        (p(dy=5, lean=20, hf=(7, 5)), 110), (p(dy=2, lean=12), 130)],
        cat='strike', desc=desc, hit_frame=4, power=3, shake=dict(frames=4, amp=2))


def sig_throw(desc, **_):
    """Slash wave: coil with the weapon back over the shoulder, one smear forward, the wave leaves on proj_frame."""
    return M([
        (p(dy=2, lean=-4, hf=(-1, -6), eb_f='up', wa=-150, fx=(('charge', 'hf', 2, -1),)), 140),
        (p(dy=4, lean=-10, sq=0.95, chest=1.04, hf=(-3, -8), eb_f='up', wa=-165, fx=(('charge', 'hf', 0, -2), ('charge', 'hb', -1, -3))), 110),
        (p(dy=3, lean=20, hf=(12, 1), ff=(11, 0), fb=(-9, 0), wa=22, dx=4, smear_f=(-3, -8)), 40),
        (p(dy=3, lean=24, hf=(12, 2), ff=(12, 0), fb=(-9, 0), wa=28, fx=(('spark', 'hf', 4, 0),)), 180),
        (p(dy=3, lean=26, hf=(12, 3), ff=(12, 0), fb=(-9, 0), wa=40), 230),
        (p(lean=12, hf=(9, 3)), 90), (S0, 110)],
        cat='special', desc=desc, proj_frame=3, power=2)


def sig_cast(desc, **_):
    """Thrust release: draw the weapon back level, hold, one smear thrust, the bolt leaves on proj_frame."""
    return M([
        (p(dy=2, lean=6, hf=(5, 1), wa=-20, fx=(('charge', 'hf', 4, -3),)), 120),
        (p(dy=3, lean=4, hf=(4, 0), wa=-15, fx=(('charge', 'hf', 3, -4), ('charge', 'hb', -2, -3))), 90),
        (p(dy=4, lean=-2, sq=0.96, hf=(0, 2), wa=-8), 150),
        (p(dy=3, lean=22, hf=(13, -1), ff=(12, 0), fb=(-9, 0), wa=-6, dx=4, smear_f=(0, 2)), 40),
        (p(dy=3, lean=24, hf=(13, -1), ff=(12, 0), fb=(-9, 0), wa=-5, fx=(('spark', 'hf', 4, -1),)), 180),
        (p(dy=2, lean=26, hf=(13, 0), ff=(12, 0), fb=(-9, 0), wa=4), 230), (p(lean=12, hf=(9, 2)), 90), (S0, 110)],
        cat='special', desc=desc, proj_frame=4, power=2)


def sig_rewind(desc, glyph='rewind', **_):
    """Super: snap back a second in time with an afterimage trail.  glyph: 'rewind' (<<) or 'bigglyph' (2x cap sigil)."""
    gfx = ('rewind', 'head', 7, -10) if glyph == 'rewind' else ('bigglyph', 'head', 8, -12)
    return M([
        (p(dy=3, lean=6, sq=0.95, hf=(4, 3), fx=(gfx,)), 160),
        (p(dy=2, lean=-6, flash=True), 50),
        (p(dx=-12, dy=-1, lean=-18, sq=1.06, ff=(8, 3), fb=(-8, 2), hf=(3, -2), ghost=(6, 12, 18), fx=(gfx,)), 60),
        (p(dx=-12, dy=-2, lean=-20, sq=1.04, ff=(9, 3), fb=(-9, 3), hf=(2, -3), ghost=(7, 14, 21)), 70),
        (p(dx=-10, dy=-1, lean=-14, ff=(8, 2), fb=(-8, 2), hf=(3, -2), ghost=(7, 14)), 60),
        (p(dx=-4, dy=3, lean=4, sq=0.92, fx=(('dust', 'ff', 4, 1),)), 100),
        (p(dy=1, face='g', hf=(9, 0), fx=(gfx,)), 260)],
        cat='super', desc=desc)


def sig_raise(desc, glyph='bigsigil', **_):
    """Super: raise the weapon and a giant sigil and power up."""
    gfx = ('bigsigil', 'head', 9, -11) if glyph == 'bigsigil' else ('bigglyph', 'head', 9, -12)
    return M([
        (p(dy=3, lean=6, sq=0.95, hf=(5, 4), fist_f=4), 140),
        (p(dy=4, lean=4, sq=0.93, chest=1.04, hf=(5, 5), aura=1, fx=(('charge', 'hf', 3, -3),)), 110),
        (p(dy=1, lean=0, sq=1.06, hf=(6, -8), eb_f='up', wa=-70, aura=2, face='g', fx=(gfx,)), 120),
        (p(dy=2, lean=0, sq=1.02, chest=1.08, hf=(6, -9), eb_f='up', wa=-72, aura=3, face='g', fx=(gfx, ('spark_s', 'hf', 0, -3))), 170),
        (p(dy=3, lean=8, chest=1.10, hf=(6, -7), eb_f='up', wa=-68, aura=4, face='g', fx=(gfx,)), 150),
        (p(dy=2, lean=4, aura=1), 90), (S0, 110)],
        cat='super', desc=desc)


TEMPLATES = {'spin': sig_spin, 'pound': sig_pound, 'throw': sig_throw, 'cast': sig_cast,
             'rewind': sig_rewind, 'raise': sig_raise}


# ---------------------------------------------------------------------- signature idles (V6)
# Every idle is a weight shift (breathing chest, head bob) in the character's own weapon stance, plus one personal tic
# with its weapon in the back half of the loop.  The loop closes on the stance pose.
def make_idle(stance, tic, desc):
    def k(**over):
        kw = dict(stance)
        kw.update(over)
        return kw
    hf, hb = stance.get('hf', (7, 3)), stance.get('hb', (3, 4))
    dy = stance.get('dy', 2)
    frames = [(k(), 170), (k(chest=1.03), 130),
              (k(dy=dy + 1, chest=1.06, head=(1, 1), hf=(hf[0], hf[1] + 1), hb=(hb[0], hb[1] + 1)), 150),
              (k(dy=dy + 1, chest=1.05, head=(1, 1), hf=(hf[0], hf[1] + 1), hb=(hb[0], hb[1] + 1)), 180)]
    frames += [(k(**over), ms) for over, ms in tic]
    frames.append((k(chest=0.98), 140))
    return M([(p(**kw), ms) for kw, ms in frames], loop=True, cat='locomotion', desc=desc)


IDLE_DATA = {
    'guard': (dict(dy=2, lean=10, hf=(7, 3), hb=(3, 4), ff=(8, 0), fb=(-7, 0)),
              [(dict(face='g'), 100), (dict(face='g', head=(2, 0)), 120), (dict(), 220)], 'Guard stance: breathing, weight shift.'),
    'ronin': (dict(dy=2, lean=8, hf=(7, 4), ff=(8, 0), fb=(-8, 0)),
              [(dict(wa=-20, head=(2, 0), face='g'), 100), (dict(wa=-96, face='g', tilt=-4), 80), (dict(face='g'), 240)],
              'Ronin stance: two hands on the katana, tip at the throat; flicks the blade up.'),
    'shadow': (dict(dy=4, lean=18, hf=(8, 2), hb=(1, 5), ff=(9, 0), fb=(-7, 0)),
               [(dict(wa=-30, face='g'), 70), (dict(wa=70, face='g'), 60), (dict(face='g', head=(2, 1)), 220)],
               'Ninja crouch: low, kunai reversed; spins the lead kunai.'),
    'dancer': (dict(dy=1, lean=4, hf=(8, 0), hb=(-4, 3), eb_b='back', ff=(6, 0), fb=(-7, 0)),
               [(dict(hf=(5, -3), hb=(6, -3), eb_b='down', wa=-62, wb=-118, face='g'), 90), (dict(hf=(5, -3), hb=(6, -3), eb_b='down', wa=-60,
                wb=-120, face='g', tilt=-5), 120), (dict(hf=(9, 0), hb=(-5, 2), face='g'), 200)],
               'Dancer stance: one blade forward, one back; crosses them and opens.'),
    'lancer': (dict(dy=3, lean=12, hf=(8, 3), wa=-28, ff=(9, 0), fb=(-7, 0)),
               [(dict(wa=-62, face='g'), 70), (dict(wa=-4, face='g', head=(3, 0), tilt=6), 80), (dict(face='g'), 230)],
               'Lancer stance: spear low and level; twirls the tip and snaps its head.'),
    'mountain': (dict(dy=2, lean=6, hf=(8, 3), wa=-92, ff=(8, 0), fb=(-8, 0)),
                 [(dict(hf=(8, 0), dy=1, sq=1.02), 110), (dict(hf=(8, 5), dy=3, sq=0.95, face='g', fx=(('dust', 'hip', 12, 6),)), 80),
                  (dict(face='g'), 250)], 'Mountain stance: staff planted upright; lifts it and thumps the ground.'),
    'samurai': (dict(dy=2, lean=10, hf=(5, 5), wa=150, ff=(8, 0), fb=(-8, 0)),
                [(dict(wa=166, face='g'), 90), (dict(wa=138, face='g', head=(2, 0)), 80), (dict(face='g'), 230)],
                'Samurai stance: energy blade low and back; the blade hums and flicks.'),
    'ranger': (dict(dy=1, lean=6, hf=(9, 4), wa=4, hb=(1, 6), wb=100, ff=(7, 0), fb=(-7, 0)),
               [(dict(hf=(10, 1), wa=-4, head=(2, 0), face='g'), 120), (dict(hf=(10, 1), wa=-4, head=(2, 0), face='g', tilt=4), 260), (dict(), 110)],
               'Ranger stance: bow forward, dagger low; raises the bow to sight.'),
    'fans': (dict(dy=4, lean=16, hf=(6, -6), eb_f='up', wa=-70, hb=(-4, 4), eb_b='back', ff=(9, 0), fb=(-8, 0)),
             [(dict(wa=-30, hf=(8, -4), face='g'), 90), (dict(wa=-100, hf=(6, -7), face='g', tilt=-4), 110), (dict(face='g'), 210)],
             'Kunoichi stance: one fan forward, one back; flicks the lead fan open.'),
    'knight': (dict(dy=2, lean=6, hf=(8, 5), wa=-64, ff=(8, 0), fb=(-8, 0)),
               [(dict(wa=-56, dy=3, sq=0.97), 110), (dict(wa=-74, head=(2, 0)), 90), (dict(), 240)],
               'Knight stance: greatsword held high in front, both hands low on the grip; shifts its weight.'),
    'berserk': (dict(dy=3, lean=14, hf=(8, -1), wa=-105, hb=(4, 3), fist_b=4, ff=(9, 0), fb=(-8, 0)),
                [(dict(face='o', chest=1.10, head=(2, -1)), 120), (dict(face='o', chest=1.12, head=(3, -1), wa=-90), 220), (dict(face='g'), 100)],
                'Berserker stance: axe raised, hunched; roars.'),
    'tonfa': (dict(dy=3, lean=10, hf=(7, 0), hb=(4, -1), ff=(8, 0), fb=(-7, 0)),
              [(dict(wa=-30, face='g'), 70), (dict(wa=80, face='g'), 60), (dict(face='g'), 230)],
              'Monk stance: tonfa along both forearms; spins the lead tonfa.'),
    'nomad': (dict(dy=2, lean=8, hf=(8, 1), hb=(-3, 4), eb_b='back', ff=(7, 0), fb=(-7, 0)),
              [(dict(wa=120), 70), (dict(wa=240), 80), (dict(face='g'), 230)],
              'Nomad stance: chakrams wide; spins the lead ring.'),
    'oni': (dict(dy=3, lean=16, hf=(9, 2), wa=35, ff=(9, 0), fb=(-9, 0)),
            [(dict(wa=10, hf=(9, 0), dy=2), 120), (dict(wa=48, hf=(9, 4), dy=4, sq=0.95, face='o'), 80), (dict(face='g'), 250)],
            'Oni stance: hunched, the kanabo dragged low; taps the ground.'),
}


def _idle_fn(name):
    st, tic, desc = IDLE_DATA[name]
    return lambda: make_idle(st, tic, desc)


IDLES = {name: _idle_fn(name) for name in IDLE_DATA}


# ---------------------------------------------------------------------- signature victories (V5.1)
def _vic(keys, desc):
    return M([(p(free_b=True, **kw), ms) for kw, ms in keys], cat='emote', desc=desc)


def vic_fistpump():
    return _vic([
        (dict(dy=4, lean=10, sq=0.88, hf=(5, 3), hb=(3, 3), face='w'), 120),
        (dict(dy=-6, lean=0, sq=1.12, hf=(5, -12), hb=(3, 2), ff=(5, 3), fb=(-4, 2), face='w', fx=(('star', 'head', -8, -7),)), 50),
        (dict(dy=-10, lean=-4, sq=1.0, hf=(6, -13), hb=(2, 3), ff=(5, 5), fb=(-4, 4), face='w', fx=(('star', 'head', -9, -6), ('star', 'head', 8, -8))), 140),
        (dict(dy=-4, lean=-2, sq=1.05, hf=(6, -13), hb=(2, 3), ff=(5, 3), fb=(-4, 2), face='w'), 60),
        (dict(dy=4, lean=4, sq=0.88, hf=(5, -12), hb=(3, 2), face='w', fx=(('dust', 'ff', 5, 1), ('dust', 'fb', -6, 1))), 70),
        (dict(dy=0, lean=0, sq=1.03, hf=(5, -13), hb=(4, 3), face='w'), 80),
        (dict(dy=1, lean=0, hf=(5, -12), hb=(4, 3), face='w'), 300)], 'Fist pump. Played when a task finishes.')


def vic_monk():
    """Claude: palms together, a deep bow, then up with a two-finger peace sign and a star."""
    return _vic([
        (dict(dy=2, lean=8, hf=(5, -3), hb=(5, -3), fist_f=2, fist_b=2, ff=(5, 0), fb=(-5, 0), face='n'), 160),
        (dict(dy=3, lean=32, head=(3, 3), sq=0.97, hf=(4, 0), hb=(4, 0), fist_f=2, fist_b=2, ff=(5, 0), fb=(-5, 0), face='z'), 120),
        (dict(dy=3, lean=36, head=(3, 3), sq=0.97, hf=(4, 1), hb=(4, 1), fist_f=2, fist_b=2, ff=(5, 0), fb=(-5, 0), face='z'), 320),
        (dict(dy=0, lean=-4, sq=1.06, hf=(6, -12), hb=(2, 3), eb_f='up', open_f=True, ff=(5, 0), fb=(-5, 0), face='w'), 70),
        (dict(dy=1, lean=-6, sq=1.0, tilt=-6, hf=(7, -13), hb=(2, 3), eb_f='up', open_f=True, ff=(5, 0), fb=(-5, 0), face='w',
              fx=(('star', 'head', 9, -9),)), 150),
        (dict(dy=1, lean=-6, tilt=-6, hf=(7, -13), hb=(2, 3), eb_f='up', open_f=True, ff=(5, 0), fb=(-5, 0), face='w',
              fx=(('star', 'head', -8, -10), ('star', 'head', 10, -6))), 150),
        (dict(dy=1, lean=-4, tilt=-4, hf=(7, -13), hb=(2, 3), eb_f='up', open_f=True, ff=(5, 0), fb=(-5, 0), face='w'), 300)],
        'Prayer bow, then a two-finger peace sign.')


def vic_hacker():
    """Codex: throws the hood back a notch, crosses its arms, two slow nods under the visor."""
    return _vic([
        (dict(dy=2, lean=10, hf=(2, -8), hb=(4, 2), ff=(6, 0), fb=(-6, 0), face='g'), 150),
        (dict(dy=1, lean=4, chest=1.06, sq=1.03, hf=(-2, -4), hb=(6, -4), eb_f='down', eb_b='down', fist_f=3, fist_b=3, ff=(6, 0), fb=(-6, 0), face='g'), 90),
        (dict(dy=2, lean=2, chest=1.08, hf=(-2, -4), hb=(6, -4), fist_f=3, fist_b=3, ff=(6, 0), fb=(-6, 0), face='g'), 260),
        (dict(dy=2, lean=4, chest=1.08, head=(1, 2), hf=(-2, -4), hb=(6, -4), fist_f=3, fist_b=3, ff=(6, 0), fb=(-6, 0), face='g'), 140),
        (dict(dy=2, lean=2, chest=1.08, head=(0, 0), hf=(-2, -4), hb=(6, -4), fist_f=3, fist_b=3, ff=(6, 0), fb=(-6, 0), face='g'), 180),
        (dict(dy=2, lean=4, chest=1.08, head=(1, 2), hf=(-2, -4), hb=(6, -4), fist_f=3, fist_b=3, ff=(6, 0), fb=(-6, 0), face='w',
              fx=(('spark_s', 'head', 8, -6),)), 140),
        (dict(dy=2, lean=2, chest=1.06, head=(0, 0), hf=(-2, -4), hb=(6, -4), fist_f=3, fist_b=3, ff=(6, 0), fb=(-6, 0), face='w'), 300)],
        'Hood back, arms crossed, two slow nods.')


def vic_ronin():
    """Gemini: a full spin that whips both ponytails out, landing in a one-arm-up pose with sparkles."""
    return _vic([
        (dict(dy=3, lean=10, sq=0.94, hf=(4, 2), hb=(2, 2), ff=(6, 0), fb=(-6, 0), face='w'), 110),
        (dict(dy=1, lean=0, turn=0.6, face='back', dx=1, hf=(2, -2), hb=(-3, -2), ff=(3, 0), fb=(-3, 0)), 60),
        (dict(dy=0, lean=-6, turn=0.3, face='back', dx=1, sq=1.04, hf=(-4, -6), hb=(-6, -4), ff=(2, 1), fb=(-2, 0)), 50),
        (dict(dy=0, lean=-4, turn=0.7, dx=-1, sq=1.04, hf=(6, -10), hb=(-5, 0), ff=(4, 2), fb=(-4, 0), face='w'), 60),
        (dict(dy=1, lean=-6, turn=1.0, dx=-1, hf=(7, -13), hb=(-3, 4), eb_f='up', eb_b='back', ff=(6, 0), fb=(-6, 0), face='w',
              fx=(('star', 'head', 9, -10), ('star', 'head', -9, -4))), 160),
        (dict(dy=2, lean=-4, sq=0.97, hf=(7, -13), hb=(-3, 4), eb_f='up', eb_b='back', ff=(6, 0), fb=(-6, 0), face='w',
              fx=(('star', 'head', -10, -9), ('star', 'head', 10, -4), ('star', 'head', 1, -13))), 150),
        (dict(dy=1, lean=-4, hf=(7, -13), hb=(-3, 4), eb_f='up', eb_b='back', ff=(6, 0), fb=(-6, 0), face='w'), 300)],
        'A spin that whips the ponytails, one arm up, sparkles.')


def vic_pointer():
    """Cursor: a sharp point at the beaten opponent, a click (the hand snaps), then a cool head tilt."""
    return _vic([
        (dict(dy=3, lean=10, sq=0.96, hf=(4, -2), hb=(2, 2), ff=(7, 0), fb=(-6, 0), face='g'), 120),
        (dict(dy=2, lean=22, dx=2, hf=(13, -4), hb=(1, 2), open_f=True, ff=(10, 0), fb=(-7, 0), face='g', smear_f=(4, -2)), 50),
        (dict(dy=2, lean=24, hf=(14, -4), hb=(1, 2), open_f=True, ff=(10, 0), fb=(-7, 0), face='g'), 260),
        (dict(dy=2, lean=24, hf=(13, -3), hb=(1, 2), fist_f=3, ff=(10, 0), fb=(-7, 0), face='g', fx=(('spark_s', 'hf', 3, -1),)), 70),
        (dict(dy=2, lean=24, hf=(14, -4), hb=(1, 2), open_f=True, ff=(10, 0), fb=(-7, 0), face='g', fx=(('block', 'hf', 4, -2),)), 160),
        (dict(dy=2, lean=16, head=(2, 0), tilt=8, hf=(10, -2), hb=(1, 2), ff=(9, 0), fb=(-7, 0), face='w'), 140),
        (dict(dy=2, lean=14, head=(2, 0), tilt=8, hf=(9, -1), hb=(1, 2), ff=(9, 0), fb=(-7, 0), face='w'), 300)],
        'Points at the loser, clicks, head tilt.')


def vic_brawler():
    """Ollama: a ground-shaking stomp, a double-arm flex, then a jump with both fists in the air."""
    return _vic([
        (dict(dy=-3, lean=6, sq=1.06, hf=(5, -3), hb=(3, -3), fist_f=4, fist_b=4, ff=(6, 6), fb=(-6, 0), face='g'), 110),
        (dict(dy=5, lean=10, sq=0.86, hf=(6, 2), hb=(3, 2), fist_f=4, fist_b=4, ff=(8, 0), fb=(-7, 0), face='g',
              fx=(('dust', 'ff', 5, 1), ('shock', 'abs', 38, 56))), 130),
        (dict(dy=2, lean=0, chest=1.10, hf=(6, -8), hb=(2, -8), eb_f='up', eb_b='up', fist_f=4, fist_b=4, ff=(7, 0), fb=(-7, 0), face='g'), 260),
        (dict(dy=4, lean=4, sq=0.90, chest=1.04, hf=(5, 3), hb=(2, 3), fist_f=4, fist_b=4, ff=(7, 0), fb=(-7, 0), face='w'), 90),
        (dict(dy=-9, lean=0, sq=1.12, hf=(6, -13), hb=(2, -13), eb_f='up', eb_b='up', fist_f=4, fist_b=4, ff=(5, 4), fb=(-4, 3), face='w',
              fx=(('star', 'head', -9, -8), ('star', 'head', 9, -8))), 170),
        (dict(dy=4, lean=6, sq=0.88, hf=(5, -8), hb=(2, -8), eb_f='up', eb_b='up', fist_f=4, fist_b=4, ff=(7, 0), fb=(-7, 0), face='w',
              fx=(('dust', 'ff', 5, 1), ('dust', 'fb', -6, 1))), 80),
        (dict(dy=1, lean=2, chest=1.06, hf=(6, -10), hb=(2, -10), eb_f='up', eb_b='up', fist_f=4, fist_b=4, ff=(7, 0), fb=(-7, 0), face='w'), 300)],
        'Stomp, flex, and a two-fist jump.')


def vic_agent():
    """Generic: snaps to attention, a crisp salute, holds it, then stands at ease with the hands behind the back."""
    return _vic([
        (dict(dy=2, lean=6, hf=(4, 2), hb=(1, 3), ff=(5, 0), fb=(-6, 0), face='n'), 120),
        (dict(dy=1, lean=0, chest=1.06, sq=1.03, hf=(3, -7), hb=(0, 6), ff=(2, 0), fb=(-3, 0), fist_f=3, face='n', smear_f=(4, 2)), 50),
        (dict(dy=1, lean=0, chest=1.08, hf=(3, -8), hb=(0, 6), ff=(2, 0), fb=(-3, 0), fist_f=3, face='n'), 300),
        (dict(dy=1, lean=0, chest=1.08, hf=(3, -8), hb=(0, 6), ff=(2, 0), fb=(-3, 0), fist_f=3, face='w', fx=(('star', 'head', 9, -8),)), 160),
        (dict(dy=1, lean=2, chest=1.04, hf=(4, -2), hb=(0, 6), ff=(2, 0), fb=(-3, 0), face='w'), 90),
        (dict(dy=1, lean=2, hf=(-3, 5), hb=(-3, 5), eb_f='back', eb_b='back', ff=(5, 0), fb=(-6, 0), face='w'), 140),
        (dict(dy=1, lean=2, chest=1.03, hf=(-3, 5), hb=(-3, 5), eb_f='back', eb_b='back', ff=(5, 0), fb=(-6, 0), face='w'), 300)],
        'Attention, salute, at ease.')


VICTORIES = {'fistpump': vic_fistpump, 'monk': vic_monk, 'hacker': vic_hacker, 'ronin': vic_ronin, 'pointer': vic_pointer,
             'brawler': vic_brawler, 'agent': vic_agent}


def build_moves(character):
    """character: a roster.Character or its name.  Shared move set + the character's three signature moves."""
    import roster
    ch = roster.get(character)
    body = ch.body
    mv = {}

    # ------------------------------------------------------------------ locomotion
    # idle: the character's signature stance (weight shift + personal tic); 'guard' is the shared default
    mv['idle'] = IDLES[ch.style.get('idle', 'guard')]()
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
    warm = [((8, 2), (2, 4)), ((7, 3), (3, 4)), ((6, 4), (4, 3)), ((5, 4), (5, 3)), ((6, 3), (4, 4)), ((7, 2), (3, 4))]
    walk = []
    for i in range(6):
        a, b = fa[i], fa[(i + 3) % 6]
        walk.append((p(dx=4, dy=wdy[i], sq=wsq[i], head=(1, whead[i]), lean=wlean[i], hf=warm[i][0], hb=warm[i][1], ff=a, fb=b, face='f', fk=1.0), 100))
    mv['walk'] = M(walk, loop=True, cat='locomotion', desc='Stride-locked walk: contact, down, passing; planted foot does not slide.', stride=24)
    mv['walk_back'] = M([(replace(f, dx=-4), 110) for f, _ in reversed(walk)], loop=True, cat='locomotion',
                        desc='Retreat while facing the opponent.', stride=24)
    mv['dash'] = M([
        (p(dy=3, lean=8, sq=0.90, hf=(4, 3), hb=(0, 2), ff=(6, 0), fb=(-4, 0)), 60),
        (p(dx=14, dy=-2, lean=30, sq=1.10, hf=(10, 2), wa=-10, ff=(9, 4), fb=(-6, 2), ghost=(6,)), 50),
        (p(dx=14, dy=-3, lean=28, sq=1.04, hf=(9, 2), wa=-10, ff=(8, 3), fb=(-7, 3), ghost=(7, 14), fx=(('dust', 'fb', -5, 3), ('speedlines', 'hip', -10, -6))), 60),
        (p(dx=8, dy=3, lean=18, sq=0.90, hf=(8, 2), ff=(11, 0), fb=(-2, 0), fx=(('dust', 'fb', -3, 1),)), 80),
        (p(dx=2, sq=1.02), 110)], cat='locomotion', desc='Low dash forward that covers real ground, with dust and speed lines.')
    mv['backdash'] = M([
        (p(dy=3, lean=4, sq=0.92, hf=(4, 2), hb=(1, 2)), 50),
        (p(dx=-12, dy=-2, lean=-16, sq=1.08, hf=(4, 0), ff=(8, 3), fb=(-8, 2), ghost=(7, 14, 21)), 60),
        (p(dx=-12, dy=-3, lean=-20, sq=1.03, hf=(3, -1), ff=(9, 3), fb=(-9, 3), ghost=(8, 16)), 50),
        (p(dx=-6, dy=3, lean=-8, sq=0.90, hf=(5, 2), ff=(10, 0), fb=(-4, 0), fx=(('dust', 'ff', 4, 1),)), 80),
        (p(dx=-1, sq=1.02), 110)], cat='defense', desc='Evasive hop back with an afterimage trail.')
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

    # ------------------------------------------------------------------ strikes (V6: weapon swings, section-6 timing)
    # wind-up held over two keys -> one smear (the crescent) -> contact hold (hitstop) -> held follow-through -> settle
    mv['jab'] = M([
        (p(dy=3, lean=2, sq=0.96, turn=0.9, hf=(2, 4), wa=-12, ff=(6, 0), fb=(-8, 0)), 110),
        (p(dy=4, lean=0, sq=0.95, turn=0.9, hf=(1, 4), wa=-10, ff=(6, 0), fb=(-8, 0)), 70),
        (p(dy=2, lean=24, hf=(8, 1), wa=-4, ff=(12, 0), fb=(-9, 0), fist_f=4, dx=5, smear_f=(1, 4)), 40),
        (p(dy=2, lean=26, hf=(8, 1), wa=-3, ff=(12, 0), fb=(-9, 0), fist_f=4, fx=(('spark', 'hf', 3, 0),)), 140),
        (p(dy=2, lean=28, hf=(8, 2), wa=6, ff=(12, 0), fb=(-9, 0), fist_f=4), 70),
        (p(dy=1, lean=14, hf=(9, 2), ff=(9, 0), fb=(-7, 0)), 120),
        (S0, 90)],
        cat='strike', desc='Fast lead-hand thrust. Light hit, small hit-stop.', hit_frame=3, power=1)
    mv['cross'] = M([
        (p(dy=2, lean=-6, chest=1.05, turn=0.85, hf=(-2, -8), eb_f='up', wa=-150, ff=(7, 0), fb=(-8, 0)), 130),
        (p(dy=3, lean=-10, sq=0.96, turn=0.85, hf=(-4, -9), eb_f='up', wa=-160, ff=(7, 0), fb=(-9, 0)), 90),
        (p(dy=3, lean=24, hf=(12, 3), wa=38, ff=(12, 0), fb=(-9, 0), fist_f=4, dx=5, smear_f=(-4, -9)), 40),
        (p(dy=3, lean=28, hf=(12, 4), wa=42, ff=(12, 0), fb=(-9, 0), fist_f=4, fx=(('spark', 'hf', 3, 0),)), 160),
        (p(dy=3, lean=30, hf=(11, 6), wa=58, ff=(12, 0), fb=(-9, 0), fist_f=4), 230),
        (p(dy=2, lean=14, hf=(8, 4), ff=(9, 0), fb=(-8, 0)), 100),
        (S0, 80)], cat='strike', desc='Big diagonal power slash. Medium hit, forces a block-stagger.', hit_frame=3, power=2)
    mv['uppercut'] = M([
        (p(dy=4, lean=14, hf=(3, 8), wa=130, ff=(8, 0), fb=(-7, 0)), 120),
        (p(dy=7, lean=18, sq=0.90, hf=(4, 9), wa=140, ff=(9, 0), fb=(-8, 0)), 80),
        (p(dy=-2, lean=0, sq=1.08, hf=(6, -12), wa=-92, ff=(8, 1), fb=(-6, 0), fist_f=4, dx=2, smear_f=(4, 9)), 40),
        (p(dy=-3, lean=0, sq=1.06, hf=(6, -13), wa=-94, ff=(7, 3), fb=(-5, 2), fist_f=4, fx=(('spark', 'hf', 0, -4),)), 150),
        (p(dy=-1, lean=-4, sq=1.03, hf=(5, -14), wa=-104, ff=(7, 2), fb=(-5, 1), fist_f=4), 220),
        (p(dy=2, lean=8, hf=(7, -2)), 100),
        (S0, 90)], cat='strike', desc='Rising launcher slash. Pops the opponent up.', hit_frame=3, power=2)
    mv['low_kick'] = M([
        (p(dy=3, lean=6, hf=(2, 3), wa=-120), 110),
        (p(dy=7, lean=-6, sq=0.94, turn=0.7, hf=(-3, 4), wa=-140, ff=(3, 1), fb=(-9, 0)), 70),
        (p(dy=8, lean=-10, turn=0.6, hf=(-4, 5), wa=-150, ff=(15, 0), fb=(-8, 0), dx=4, smear_ff=(3, 1)), 40),
        (p(dy=8, lean=-10, turn=0.7, hf=(-4, 5), wa=-150, ff=(15, 0), fb=(-8, 0), fx=(('spark', 'ff', 4, -1),)), 140),
        (p(dy=8, lean=-12, turn=0.75, hf=(-5, 5), wa=-150, ff=(16, 0), fb=(-8, 0)), 180),
        (p(dy=4, lean=0, hf=(2, 4), ff=(10, 0), fb=(-8, 0)), 90),
        (S0, 100)], cat='strike', desc='Sweep along the ground with a hip turn. Trips guard-high opponents.', hit_frame=3, power=1)
    mv['roundhouse'] = M([
        (p(dy=1, lean=-2, turn=0.8, hf=(4, 2), wa=-110, ff=(6, 9), fb=(-4, 0)), 140),
        (p(dy=0, lean=-14, sq=0.96, turn=0.55, hf=(-3, -4), wa=-150, ff=(3, 12), fb=(-3, 0)), 90),
        (p(dy=0, lean=-18, sq=1.03, turn=0.7, hf=(-5, -5), wa=-160, ff=(16, 14), fb=(-3, 0), dx=4, ang_f=-15, smear_ff=(3, 12)), 40),
        (p(dy=0, lean=-18, turn=0.8, hf=(-5, -5), wa=-160, ff=(16, 14), fb=(-3, 0), ang_f=-15, fx=(('spark', 'ff', 4, -1),)), 160),
        (p(dy=0, lean=-20, turn=0.9, hf=(-6, -5), wa=-158, ff=(17, 13), fb=(-3, 0), ang_f=-18), 260),
        (p(dy=1, lean=-8, hf=(0, 0), ff=(11, 8), fb=(-4, 0)), 110),
        (p(dy=1, lean=4, ff=(8, 1)), 90),
        (S0, 120)], cat='strike', desc='High kick with a full hip turn. Heavy hit, big hit-stop, held follow-through.', hit_frame=3, power=3)
    for role in ('strike', 'special'):                 # same row order as before: strike, special after the shared strikes
        name = ch.signature[role]
        tpl, desc, opts = ch.sig_moves[name]
        mv[name] = TEMPLATES[tpl](desc, **opts)

    # ------------------------------------------------------------------ defense
    mv['block'] = M([(p(dy=2, lean=4, hf=(5, -2), hb=(3, -1), wa=-96, wb=-100), 60),
                     (p(dy=3, lean=2, chest=1.03, hf=(7, -3), hb=(5, -3), wa=-100, wb=-104, ff=(8, 0), fb=(-7, 0), fist_f=4), 120),
                     (p(dy=3, lean=1, chest=1.0, hf=(7, -4), hb=(5, -3), wa=-100, wb=-104, ff=(8, 0), fb=(-7, 0), fist_f=4), 110),
                     (p(dy=2, lean=6, hf=(6, -1), hb=(3, 1), wa=-80), 80)],
                    loop=True, loop_range=(1, 2), cat='defense', desc='High guard.')
    mv['block_hit'] = M([(p(dy=3, lean=-6, sq=0.96, hf=(6, -3), hb=(4, -3), wa=-108, wb=-110, fist_f=4, fx=(('block', 'hf', 4, -3),), dx=-3), 50),
                         (p(dy=3, lean=-3, sq=0.98, hf=(5, -3), hb=(3, -3), wa=-104, wb=-106, fist_f=4, dx=-1), 80),
                         (p(dy=3, lean=3, hf=(7, -3), hb=(5, -3), wa=-100, wb=-104, fist_f=4), 100)],
                        cat='defense', desc='Guard absorbs a hit with a flash.')
    mv['crouch_block'] = M([(p(dy=7, lean=14, sq=0.92, hf=(8, 1), hb=(6, 2), wa=-60, wb=-70, ff=(9, 0), fb=(-8, 0), fist_f=4), 80),
                            (p(dy=8, lean=14, sq=0.91, hf=(8, 1), hb=(6, 2), wa=-60, wb=-70, ff=(9, 0), fb=(-8, 0), fist_f=4), 120)],
                           loop=True, loop_range=(0, 1), cat='defense', desc='Low guard.')
    mv['parry'] = M([(p(dy=2, lean=4, hf=(4, -4), wa=-110), 70),
                     (p(dy=2, lean=12, hf=(12, 0), wa=10, face='g', smear_f=(4, -4), fx=(('block', 'hf', 3, -1),)), 90),
                     (p(dy=2, lean=14, hf=(13, 1), wa=18, face='g'), 160),
                     (p(dy=1, lean=10, hf=(9, 2), face='g'), 100)],
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
    mv['victory'] = VICTORIES[ch.style.get('victory', 'fistpump')]()        # the character's own win pose
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
