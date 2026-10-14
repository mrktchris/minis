"""Arena mode (docs/V4-WORKORDER.md): the two fighters leave the taskbar and fight across one whole monitor.

Everything here is pure simulation + compositing onto an abstract `surface` (write(img, x, y) / flush() / offset(dx, dy)),
so the same code runs headless in tests (Surface) and on the real monitor (minis_win.arena_window.ArenaWindow).

Stage: platforms are the TOP EDGES of visible windows' rectangles on that monitor (rectangles only - no titles are ever
read) plus the floor.  Fighters are the HD atlases drawn at 2x (~170 px tall) with DBZ-style movement: jumps, air dashes
with afterimages, hover.  Rounds / HP / winners follow rounds.py exactly (best-of-3, power*12, ultimate 40, 25 s cap,
decided vs random).  Window interaction is overlay-only: cracks where a defender is knocked into a window rect, three
cracks shatter it (shards fall, random letters spray), ultimates explode and shake the whole overlay (the window moves,
nothing else does).  With a freeze backdrop (a RAM-only image handed in by the process) shattered windows become dark holes.
"""
from __future__ import annotations
import math, random
from collections import deque
from PIL import Image, ImageDraw

from . import choreo, rounds
from .effects import EffectPlayer
from .render import font, text, TRACK, AMBER, RED

SCALE = 2                       # HD atlas (RES 2) drawn 2x -> 256 px cells, ~170 px fighters
GRAVITY = 2400.0
MAX_FALL = 2200.0
WALK = 180.0
FLY = 1100.0
JUMP_VY = -1150.0
REACH_PX = 72                   # hip-to-hip distance for a strike at this scale
HUD_H = 64
SPRITE_H = 228                  # ground_y (114) x SCALE: how far a standing fighter's cell reaches above its feet
MIN_PLATFORM_Y = HUD_H + SPRITE_H           # a window top higher than this would stand the fighter in the HUD: not a platform (still a crack target)
EXIT_W, EXIT_H, EXIT_MARGIN = 104, 36, 14
PHASES = ('entry', 'intro', 'fight', 'round_end', 'winner', 'exit', 'done')
AFTERIMAGE_S = 0.28
HOLE = (12, 12, 16, 255)


# ---------------------------------------------------------------- headless surface
class Surface:
    """RAM surface for tests / previews: `canvas` holds what the window would show."""

    def __init__(self, w, h):
        self.w, self.h = int(w), int(h)
        self.canvas = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0))
        self.writes, self.flushes, self.offsets = 0, 0, []
        self._offset = (0, 0)

    def write(self, img, x, y):
        x, y = int(x), int(y)
        x0, y0, x1, y1 = max(0, x), max(0, y), min(self.w, x + img.width), min(self.h, y + img.height)
        if x1 <= x0 or y1 <= y0:
            return
        self.canvas.paste(img.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))
        self.writes += 1

    def flush(self, full=False):
        self.flushes += 1
        return True

    def offset(self, dx, dy):
        self._offset = (dx, dy)
        self.offsets.append((dx, dy))

    def pump(self):
        return True

    def reassert_topmost(self):
        pass

    def close(self):
        pass


# ---------------------------------------------------------------- stage
class Stage:
    """Monitor-local geometry.  windows: [(id, l, t, r, b)] in SCREEN px (ids are opaque numbers kept in RAM only)."""

    def __init__(self, rect, windows=(), floor_y=None, min_size=(160, 100)):
        self.l, self.t, self.r, self.b = [int(v) for v in rect]
        self.w, self.h = self.r - self.l, self.b - self.t
        self.floor_y = int(floor_y - self.t) if floor_y is not None else self.h
        self.min_size = tuple(min_size)
        self.windows = []
        self.update(windows)

    def update(self, windows):
        out = []
        for win in windows:
            wid, l, t, r, b = win
            l, t, r, b = l - self.l, t - self.t, r - self.l, b - self.t
            l, t, r, b = max(0, l), max(0, t), min(self.w, r), min(self.h, b)
            if r - l < self.min_size[0] or b - t < self.min_size[1]:
                continue
            if t <= 2 and (r - l) >= self.w * 0.95:
                continue                                       # maximized: its top edge is the monitor's top, no platform
            if t >= self.floor_y - 10:
                continue
            out.append(dict(id=int(wid), l=l, t=t, r=r, b=b))
        self.windows = out[:16]

    def platforms(self):
        """[(x0, x1, y)]: window tops (clipped) + the floor.  A top above MIN_PLATFORM_Y would stand a fighter inside the
        HUD, so it is skipped here but the window still cracks."""
        out = [(w['l'], w['r'], w['t']) for w in self.windows if w['t'] >= MIN_PLATFORM_Y]
        out.append((0, self.w, self.floor_y))
        return out

    def window_at(self, x, y):
        """Topmost window rect containing the point (enumeration order = z-order, top first)."""
        for w in self.windows:
            if w['l'] <= x <= w['r'] and w['t'] <= y <= w['b']:
                return w
        return None

    def window_by_id(self, wid):
        for w in self.windows:
            if w['id'] == wid:
                return w
        return None


class Cracks:
    """Per-window crack state machine: 0 -> 1 -> 2 cracks, the third shatters (once)."""
    SHATTER_AT = 3

    def __init__(self):
        self.count = {}
        self.shattered = set()

    def hit(self, wid, heavy=False):
        """-> 'crack_small' | 'crack_big' | 'shatter' | None (already shattered)."""
        if wid in self.shattered:
            return None
        self.count[wid] = self.count.get(wid, 0) + (2 if heavy else 1)
        if self.count[wid] >= self.SHATTER_AT:
            self.shattered.add(wid)
            return 'shatter'
        return 'crack_big' if heavy else 'crack_small'

    def state(self, wid):
        return 'shattered' if wid in self.shattered else self.count.get(wid, 0)


# ---------------------------------------------------------------- fighters
class Body:
    def __init__(self, slot, atlas, x, y, facing):
        self.slot, self.atlas = slot, atlas
        self.x, self.y, self.vx, self.vy = float(x), float(y), 0.0, 0.0
        self.facing = facing
        self.anim, self.anim_t0, self.loop = 'idle', 0.0, True
        self.hp = rounds.HP_MAX
        self.grounded = False
        self.support = None
        self.fly_until = 0.0                 # gravity off while flying / hovering
        self.target = None                   # (x, y) the fighter moves towards, or None
        self.knocked_until = 0.0
        self.down = False                    # lying after a knockdown
        self.trail = deque(maxlen=8)         # afterimages: (t, anim, frame, facing, x, y)
        self.last_crack = 0.0
        self.hold = None                     # anim to settle into when a one-shot finishes
        self.stop = None                     # (t0, t1) hitstop: animation and motion stand still (V5)
        self.hover = False                   # stays in the air at its target while fly_until lasts (air-to-air) (V5)
        self.move_until = 0.0                # a reset step (backdash / walk_back) keeps its velocity until then (V5)
        self.getup_at = None                 # knocked down but not out: kip up at this time (V5)

    def play(self, name, now, loop=None, hold=None):
        if name not in self.atlas.anim:
            name = 'idle'
        if name == self.anim and self.loop and (loop is None or loop):
            return
        self.anim, self.anim_t0 = name, now
        self.loop = self.atlas.anim[name]['loop'] if loop is None else loop
        self.hold = hold

    def frame(self, now):
        el = now - self.anim_t0
        if self.stop is not None:
            el -= max(0.0, min(now, self.stop[1]) - max(self.stop[0], self.anim_t0))
        return self.atlas.locate(self.anim, el * 1000.0, self.loop)

    def stopped(self, now):
        return self.stop is not None and self.stop[0] <= now < self.stop[1]

    def center(self):
        return self.x, self.y - 40 * SCALE

    def sprite_rect(self):
        w, h = self.atlas.cell
        left = int(self.x - self.atlas.anchor(self.facing) * SCALE)
        top = int(self.y - self.atlas.ground_y * SCALE)
        return left, top, left + w * SCALE, top + h * SCALE


# ---------------------------------------------------------------- the arena
class Arena:
    def __init__(self, stage, atlases, fx, seed=1, mode='decided', scores=None, backdrop=None, names=None, now=0.0, record=None,
                 cfg=None, chars=None):
        """atlases: {'a': Atlas(hd), 'b': Atlas(hd)}; backdrop: RGBA image the size of the stage kept in RAM, or None."""
        self.stage, self.fx = stage, fx
        self.rng = random.Random(seed)
        self.mode = mode if mode in rounds.MODES else 'decided'
        self.scores = dict(scores or {'a': 100.0, 'b': 100.0})
        self.p_left = rounds.p_left(self.mode, self.scores, 'a', 'b')
        self.names = dict(names or {'a': atlases['a'].display, 'b': atlases['b'].display})
        self.chars = dict(chars or {s: atlases[s].character for s in 'ab'})
        self.record = record or rounds.record_result
        self.cfg = cfg or {}
        self.backdrop = backdrop                               # RAM only: never written, never logged
        self.holes = []
        self.fxp = EffectPlayer(fx, res=SCALE * 2, fps=30)    # arena px = RES 2 art at 2x -> res 4 relative to the RES 1 rig
        self.fxp.res = 4
        self.cracks = Cracks()
        self.crack_marks = {}                                  # window id -> [(x, y, kind)] drawn while the window stands
        self.letters_spawned = 0
        self.explosions = 0
        w, fy = stage.w, stage.floor_y
        self.start_x = {'a': w * 0.3, 'b': w * 0.7}
        self.f = {'a': Body('a', atlases['a'], self.start_x['a'], fy + 260, 1), 'b': Body('b', atlases['b'], self.start_x['b'], fy + 260, -1)}
        self.wins = {'a': 0, 'b': 0}
        self.round = 0
        self.rounds = []
        self.phase, self.phase_t0 = 'entry', now
        self.round_t0 = now
        self.exchange = None                                   # dict(att, dfn, state, t, move, ...)
        self.banner = None                                     # (kind, until, x)
        self.winner = None
        self.ko_loser = None
        self.paused = False
        self.exit_requested = False
        self.last_now = now
        self.events = deque(maxlen=200)                        # content-free notes (kind, t) for tests / the log
        self.used_ult = {'a': False, 'b': False}
        self.cooldown_until = now + 0.5
        self.hp_history = []
        self.pick = {s: choreo.Picker(self.rng, atlases[s]) for s in 'ab'}        # V5 choreography state
        self.meter = {'a': 0.0, 'b': 0.0}
        self.k_round = 0
        self.air_done = False
        self.last_att, self.last_hit = None, False
        for s in 'ab':
            self.f[s].vy = -1700.0                             # entry: burst out of the taskbar, upward
            self.f[s].fly_until = 0.0
        self.note('entry', now)

    # ---- bookkeeping
    def note(self, kind, t, **kw):
        self.events.append((kind, round(t, 3), kw))

    def state(self):
        return dict(phase=self.phase, round=self.round, hp={s: self.f[s].hp for s in 'ab'}, wins=dict(self.wins), winner=self.winner,
                    mode=self.mode, freeze=self.backdrop is not None, shattered=len(self.cracks.shattered), cracks=sum(self.cracks.count.values()),
                    events=[[k, t, str(kw.get('name') or kw.get('move') or '')] for k, t, kw in list(self.events)[-16:]])

    def request_exit(self, now):
        if self.phase not in ('exit', 'done'):
            self.exit_requested = True
            self._enter('exit', now)

    def exit_rect(self):
        return (self.stage.w - EXIT_MARGIN - EXIT_W, EXIT_MARGIN, self.stage.w - EXIT_MARGIN, EXIT_MARGIN + EXIT_H)

    def hit_exit(self, x, y):
        x0, y0, x1, y1 = self.exit_rect()
        return x0 <= x <= x1 and y0 <= y <= y1

    # ---- phases
    def _enter(self, phase, now):
        self.phase, self.phase_t0 = phase, now
        self.note(phase, now)
        if phase == 'intro':
            self.round += 1
            for s in 'ab':
                b = self.f[s]
                b.hp = rounds.HP_MAX
                b.down = False
                b.target = (self.start_x[s], self.stage.floor_y)
                b.fly_until = now + 2.0
                b.play('getup' if b.anim in ('ko', 'knockdown') else 'idle', now, loop=False, hold='idle')
            self.used_ult = {'a': False, 'b': False} if self.round == 1 else self.used_ult      # the ultimate is once per MATCH
            self.banner = (f'round{min(3, self.round)}', now + 1.2, None)
            self.exchange = None
            self.k_round, self.air_done = 0, False
            for p in self.pick.values():
                p.new_round()
            for s in 'ab':
                self.f[s].stop, self.f[s].hover, self.f[s].getup_at = None, False, None
        elif phase == 'fight':
            self.banner = None
            self.round_t0 = now
            self.cooldown_until = now + 0.4
        elif phase == 'winner':
            champ = self.winner
            loser = 'b' if champ == 'a' else 'a'
            self.banner = ('winner', now + 2.6, self.f[champ].x)
            self.f[champ].play('victory2' if self.wins[loser] == 0 and 'victory2' in self.f[champ].atlas.anim else 'victory', now, loop=False, hold='idle')
            if not self.f[loser].down:
                self.f[loser].play('knockdown', now, loop=False, hold='ko')
                self.f[loser].down = True
            try:
                self.record(self.chars[champ], self.chars[loser], where='arena')
            except Exception:
                pass
            self.note('record', now, winner=self.chars[champ])
        elif phase == 'exit':
            self.banner = None
            self.exchange = None
            for s in 'ab':
                b = self.f[s]
                b.target = None
                b.fly_until = 0.0
                b.vy, b.vx = -900.0, 0.0
                b.down = False
                b.play('jump', now, loop=False, hold='idle')
            self.fxp.clear()

    # ---- main step
    def tick(self, now):
        dt = max(0.0, min(0.05, now - self.last_now))
        self.last_now = now
        if self.paused or self.phase == 'done':
            return
        self.fxp.tick(now)
        if self.banner and now >= self.banner[1]:
            self.banner = None
            if self.phase == 'intro':
                if self.banner is None and now - self.phase_t0 >= 1.2 and now - self.phase_t0 < 1.3:
                    pass
        ph = self.phase
        if ph == 'entry':
            if now - self.phase_t0 >= 1.5 and all(self.f[s].grounded for s in 'ab'):
                self._enter('intro', now)
        elif ph == 'intro':
            el = now - self.phase_t0
            if 1.2 <= el < 1.9 and (self.banner is None or self.banner[0] != 'fight'):
                self.banner = ('fight', self.phase_t0 + 1.9, None)
            if el >= 2.0:
                self._enter('fight', now)
        elif ph == 'fight':
            self._fight(now)
        elif ph == 'round_end':
            if now - self.phase_t0 >= 2.4:
                if max(self.wins.values()) >= rounds.ROUNDS_TO_WIN:
                    self.winner = 'a' if self.wins['a'] > self.wins['b'] else 'b'
                    self._enter('winner', now)
                else:
                    self._enter('intro', now)
        elif ph == 'winner':
            if now - self.phase_t0 >= 3.2:
                self._enter('exit', now)
        elif ph == 'exit':
            if all(self.f[s].y > self.stage.h + 320 for s in 'ab') or now - self.phase_t0 > 4.0:
                self._enter('done', now)
        for s in 'ab':
            self._move(self.f[s], now, dt)
        if ph in ('fight', 'round_end'):
            for s in 'ab':
                self._window_collisions(self.f[s], now)
        for s in 'ab':
            b = self.f[s]
            if b.getup_at is not None and now >= b.getup_at and b.down and b.hp > 0 and self.phase in ('fight', 'round_end'):
                b.getup_at = None
                b.down = False
                b.play('getup', now, loop=False, hold='idle')
                self.note('getup', now, who=s)
            idx, done = b.frame(now)
            if done and not b.loop:
                b.play(b.hold or 'idle', now)

    # ---- choreography (V5: choreo.py plans every exchange; the arena plays its beats with physics)
    def _reach(self, slot, move):
        """Player px a move's own effect reaches from the hand (a beam), else 0."""
        name = self._main_fx(self.f[slot].atlas, move)
        return self.fxp.reach(name) if name else 0.0

    @staticmethod
    def _main_fx(atlas, move):
        sched = atlas.move_fx(move) if move else []
        for off, name, until in sched:
            if name == move:
                return name
        return sched[-1][1] if sched else None

    def _range_for(self, who, beat):
        """Hip distance the actor wants before this attack beat lands."""
        kind, move = beat['kind'], beat['anim']
        if kind == 'special':
            return max(REACH_PX * 2.5, 260.0)
        if kind == 'ultimate':
            name = self._main_fx(self.f[who].atlas, move)
            e = self.fx.get(name) if name else None
            reach = self.fxp.reach(name) if name else 0.0
            if reach > 0:
                return reach * 0.8                                 # the defender stands inside the beam, near its end
            if e is not None and e.travel:
                return 260.0
        return float(REACH_PX)

    def _new_exchange(self, now):
        a, b = self.f['a'], self.f['b']
        if self.last_att is not None and self.last_hit and self.rng.random() < 0.45:
            att = self.last_att                                    # pressure: the winner of the last exchange keeps coming
        else:
            att = 'a' if self.rng.random() < self.p_left else 'b'
        dfn = 'b' if att == 'a' else 'a'
        A = self.f[att].atlas
        k = self.k_round
        air = (not self.air_done) and ((k >= 1 and self.rng.random() < 0.35) or k >= 3)
        drama = choreo.dramatic(self.wins[att], self.f[att].hp, self.f[dfn].hp, k) and now - self.round_t0 > 4.0
        dist = abs(self.f[att].x - self.f[dfn].x)
        reach = self._reach(att, A.ultimate()) if A.ultimate() else 0.0
        sit = dict(range='far' if dist > REACH_PX * 1.6 else 'close', meter=self.meter[att], ult_ok=not self.used_ult[att], dramatic=drama,
                   friendly=False, air=air, k=k, ult_reaches=reach >= dist - 20)
        ex = choreo.plan_exchange(self.rng, self.pick[att], self.pick[dfn], sit)
        beats = [bt for bt in ex['beats'] if not (bt['kind'] == 'move' and bt['dx'] > 0)]   # openers are played by the approach
        if air:
            self.air_done = True
            y = max(float(MIN_PLATFORM_Y), min(min(a.y, b.y) - 260.0, self.stage.floor_y - 300.0))   # up in the air, under the HUD
            for s in (att, dfn):
                f = self.f[s]
                f.target, f.hover, f.fly_until = (f.x, y), True, now + 6.0
                f.play('jump', now, loop=False, hold='idle')
            self.note('air', now)
        elif self.rng.random() < 0.5:                             # DBZ: the defender takes to a window ledge first
            plats = self.stage.platforms()
            cur = [p for p in plats if abs(p[2] - self.f[dfn].y) < 2]
            choice = [p for p in plats if p not in cur] or plats
            x0, x1, y = choice[self.rng.randrange(len(choice))]
            self.f[dfn].target = (min(max(x0 + 60, self.rng.uniform(x0, x1)), x1 - 60), y)
            self.f[dfn].fly_until = now + 1.6
            self.f[dfn].play('jump', now, loop=False, hold='idle')
            self.note('fly', now, who=dfn)
        self.exchange = dict(att=att, dfn=dfn, beats=beats, i=0, state='approach', t=now, deadline=now + 6.0, air=air, kind=ex['kind'],
                             opener=ex['opener'], range_after=ex['range_after'], hit=False)
        self.k_round += 1

    def _fight(self, now):
        over = now - self.round_t0 - rounds.ROUND_CAP_S
        if over >= 0 and (self.exchange is None or self.exchange['state'] in ('approach', 'beat', 'wait') or over > 1.0):
            self._end_round(now, None)                             # time: the round is called on HP (a strike in flight gets 1 s)
            return
        ex = self.exchange
        if ex is None:
            if now < self.cooldown_until:
                return
            self._new_exchange(now)
            return
        if ex['air']:
            for s in 'ab':
                if self.f[s].hover:
                    self.f[s].fly_until = now + 2.0
        if ex['state'] == 'approach':
            self._approach(ex, now)
        elif ex['state'] == 'beat':
            self._start_beat(ex, now)
        elif ex['state'] == 'wait':
            if now >= ex['until']:
                ex['i'] += 1
                ex['state'] = 'beat'
        elif ex['state'] == 'strike':
            self._tick_strike(ex, now)

    def _first_attack(self, ex):
        for bt in ex['beats'][ex['i']:]:
            if bt['kind'] in choreo.ATTACK_KINDS:
                return bt
        return None

    def _approach(self, ex, now):
        att, dfn = self.f[ex['att']], self.f[ex['dfn']]
        first = self._first_attack(ex)
        if first is None:
            ex['state'] = 'beat'
            return
        want = self._range_for(ex['att'], first)
        dx = dfn.x - att.x
        att.facing = 1 if dx >= 0 else -1
        want_x = dfn.x - att.facing * want
        if ex['air']:
            ty = att.target[1] if att.target else att.y
            both_up = all(abs(self.f[s].y - ty) < 24 for s in 'ab')
            if not both_up and now < ex['deadline'] - 2.0:
                return
            if abs(att.x - want_x) > 24:
                att.target = (want_x, ty)
                return
            att.target = (att.x, ty)
            self.note('air_strike', now)
        else:
            far = abs(att.x - want_x) > 24 or abs(att.y - dfn.y) > 36
            if far and first['kind'] != 'special':
                att.target = (want_x, dfn.y)
                dist = math.hypot(att.x - want_x, att.y - dfn.y)
                if dist > 300 or now > ex['deadline'] - 2.0 or ex['opener'] == 'dash':
                    att.fly_until = now + 0.6                   # air dash: straight line, afterimages
                    if att.anim not in ('dash', 'jump'):
                        att.play('dash', now, loop=False, hold='idle')
                elif ex['opener'] == 'jump' and att.grounded:
                    att.vy = JUMP_VY * 0.85                     # jump-in: leave the ground towards the defender
                    att.grounded = False
                    att.play('jump', now, loop=False, hold='idle')
                elif att.grounded:
                    att.play('walk', now)
                if now < ex['deadline']:
                    return
            att.target = None
            att.vx = 0.0
        ex['state'] = 'beat'

    def _start_beat(self, ex, now):
        if ex['i'] >= len(ex['beats']):
            self._end_exchange(ex, now)
            return
        bt = ex['beats'][ex['i']]
        who = ex['att'] if bt['who'] == 'att' else ex['dfn']
        tgt = 'b' if who == 'a' else 'a'
        W, T = self.f[who], self.f[tgt]
        if bt['kind'] == 'move':                                   # a spacing reset: step or hop away
            dur = W.atlas.total_ms(bt['anim']) / 1000.0 if bt['anim'] in W.atlas.anim else 0.4
            away = -1 if T.x >= W.x else 1
            W.play(bt['anim'], now, loop=False if bt['anim'] == 'backdash' else None, hold='idle')
            W.vx = away * (560.0 if bt['anim'] == 'backdash' else WALK)
            W.move_until = now + dur
            W.target = None
            ex['until'] = now + dur
            ex['state'] = 'wait'
            self.note('reset', now, who=who, move=bt['anim'])
            return
        if bt['kind'] == 'emote':
            W.play(bt['anim'], now, loop=False, hold='idle')
            ex['until'] = now + W.atlas.total_ms(bt['anim']) / 1000.0 if bt['anim'] in W.atlas.anim else now + 0.5
            ex['state'] = 'wait'
            self.note('taunt', now, who=who)
            return
        # ---- an attack beat
        move, kind = bt['anim'], bt['kind']
        if move not in W.atlas.anim or T.down and kind != 'ultimate':
            ex['i'] += 1
            return
        if kind != 'counter' and not ex['air'] and abs(W.x - T.x) > self._range_for(who, bt) * 1.4 + 30 and now < ex['deadline']:
            ex['state'] = 'approach'                               # the defender moved (knockback, reset): close in again
            ex['att'], ex['dfn'] = who, tgt
            return
        dx = T.x - W.x
        W.facing = 1 if dx >= 0 else -1
        if not T.down:
            T.facing = -W.facing
        W.target, W.vx = None, 0.0
        t_c = now + rounds._contact_s(W.atlas, move)
        fx_list = []
        name = self._main_fx(W.atlas, move)
        dist = abs(dx)
        if kind in ('ultimate', 'super'):
            for off, fx_name, until in W.atlas.move_fx(move):
                lead = self.fxp.hit_frame_time(fx_name) if fx_name == move else 0.0
                fx_list.append([max(now, now + off - lead), fx_name, (now + until) if until else None])
            if kind == 'ultimate' and name:
                e = self.fx.get(name)
                k = self.fxp.res / float(e.res)
                spawn = [it[0] for it in fx_list if it[1] == name]
                if spawn:
                    if e.grow:
                        t_c = max(t_c, spawn[0] + e.grow['ms'] / 1000.0 * min(1.0, dist / max(1.0, e.grow['to_w'] * k)))
                    elif e.travel:
                        t_c = max(t_c, spawn[0] + max(0.0, dist - 40.0) / (e.travel['speed'] * k))
        elif kind == 'special':
            proj = f'{move}_proj'
            a = W.atlas.anim[move]
            spawn = now + W.atlas.start_ms(move, a.get('proj_frame', a.get('hit_frame', 0))) / 1000.0
            if self.fx.has_art(proj):
                e = self.fx.get(proj)
                speed = (e.travel['speed'] if e.travel else 320.0) * self.fxp.res / float(e.res)
                fx_list.append([spawn, proj, None])
                t_c = max(t_c, spawn + max(0.0, dist - 40.0) / speed)
                ex['proj'] = proj
        W.play(move, now, loop=False, hold='idle')
        hs = bt['hitstop'] / 1000.0
        ex.update(state='strike', who=who, tgt=tgt, beat=bt, contact=t_c, end=max(now + W.atlas.total_ms(move) / 1000.0, t_c + 0.25) + hs,
                  hit_done=False, fx_list=fx_list, pre_done=False, main=name)
        self.note('strike', now, who=who, move=move, move_kind=kind)
        if kind == 'ultimate':
            self.used_ult[who] = True
            self.note('ultimate', now, who=who, move=move)
        if ex['air']:
            self.note('air_exchange', now)

    def _tick_strike(self, ex, now):
        W, T = self.f[ex['who']], self.f[ex['tgt']]
        bt = ex['beat']
        for item in ex['fx_list']:
            if item[0] is not None and now >= item[0]:
                t_at, fx_name, until = item
                item[0] = None
                hand = W.atlas.hand(bt['anim'])
                inst = self.fxp.spawn(fx_name, now, W.x, W.y, W.facing, owner=ex['who'], hand=(hand[0] * SCALE, hand[1] * SCALE) if hand else None,
                                      fade_ms=(max(1.0, (until - now) * 1000.0) if until else None), tag=fx_name)
                if fx_name == ex.get('main') and bt['kind'] == 'ultimate':
                    self.note('beam', now, name=fx_name, grow=bool(inst.effect.grow))
                if ex.get('proj') == fx_name:
                    inst.vx = W.facing * abs(inst.vx or (320.0 * self.fxp.res / float(inst.effect.res)))
                    inst.fade_ms = max(1.0, (ex['contact'] - now + 0.05) * 1000.0)
        if not ex['pre_done'] and bt.get('pre') and now >= ex['contact'] - (0.15 if bt['pre'] == 'backdash' else 0.25):
            ex['pre_done'] = True
            if not T.down:
                if bt['pre'] == 'backdash':
                    T.play('backdash', now, loop=False, hold='idle')
                    T.vx = -W.facing * 640.0
                    T.move_until = now + 0.3
                    T.target = None
                else:
                    T.play(bt['pre'], now)
        if not ex['hit_done'] and now >= ex['contact']:
            ex['hit_done'] = True
            self._resolve_beat(ex, now)
            if self.phase != 'fight':
                return
        if now >= ex['end']:
            if self.exchange is ex:
                ex['i'] += 1
                ex['state'] = 'beat'
                if bt['kind'] == 'counter':
                    ex['att'], ex['dfn'] = ex['who'], ex['tgt']

    def _resolve_beat(self, ex, now):
        W, T = self.f[ex['who']], self.f[ex['tgt']]
        bt = ex['beat']
        kind, move, outcome = bt['kind'], bt['anim'], bt['outcome']
        cx, cy = T.center()
        hs = bt['hitstop'] / 1000.0
        if outcome == 'whiff' or T.down and kind != 'ultimate':
            self.note('whiff', now, who=ex['who'], move=move)
            return
        if hs:
            for f in (W, T):
                f.stop = (now, now + hs)
        if outcome in ('block', 'crouch_block', 'parry'):
            react = bt['react'] or 'block_hit'
            T.play(react, now, loop=False, hold='idle')
            self.fxp.spawn_at('block_spark', now, cx + T.facing * 24, cy)
            T.vx = W.facing * (160.0 if outcome != 'parry' else 0.0)
            self.note('block' if outcome != 'parry' else 'parry', now, who=ex['tgt'])
            return
        dmg = bt['dmg']
        T.hp = max(0, T.hp - dmg)
        self.meter[ex['who']] += dmg
        self.meter[ex['tgt']] += dmg / 2.0
        if kind == 'super':
            self.meter[ex['who']] = 0.0
        self.hp_history.append((round(now, 3), ex['tgt'], T.hp))
        heavy = dmg >= 24
        beam = kind == 'ultimate' and self._reach(ex['who'], move) > 0
        down = T.hp <= 0 or bt.get('down') or bt.get('react') == 'knockdown'
        T.hover, T.fly_until, T.target = False, 0.0, None
        T.grounded = False
        if down:
            T.play('knockdown', now, loop=False, hold='ko' if T.hp <= 0 else 'knockdown')
            T.down = True
            T.vx, T.vy = W.facing * (950.0 if beam else 820.0), (0.0 if beam else -620.0)      # a beam carries it straight along itself
            T.knocked_until = now + 1.2
            if T.hp > 0:
                T.getup_at = now + hs + T.atlas.total_ms('knockdown') / 1000.0 + 0.3
            self.note('knockdown', now, who=ex['tgt'], ko=T.hp <= 0)
        else:
            T.play('hit_heavy' if heavy else 'hit', now, loop=False, hold='idle')
            T.vx = W.facing * ((950.0 if beam else 260.0 + dmg * 14.0))
            T.vy = 0.0 if beam else (-380.0 if heavy else -120.0)
            T.knocked_until = now + (0.7 if heavy else 0.4)
        ix = cx
        if beam:                                                   # the impact burst sits at the beam's end, on the defender
            inst = next((i for i in self.fxp.active if i.tag == ex.get('main') and i.owner == ex['who']), None)
            if inst is not None:
                end = self.fxp.beam_end(inst, now)
                ix = min(cx, end) if W.facing > 0 else max(cx, end)
        self.fxp.spawn_at('hit_heavy' if heavy else 'hit_light', now, ix, cy, W.facing)
        sh = choreo.move_shake(W.atlas, move)
        if sh:
            self.fxp.add_shake(now, sh['frames'], sh['amp'] * SCALE)
        if kind == 'ultimate':
            imp = f'{move}_impact' if self.fx.has_art(f'{move}_impact') else 'explosion'
            self.fxp.spawn_at(imp, now, ix, cy, W.facing)
            if imp != 'explosion':
                self.fxp.spawn_at('explosion', now, ix, cy, W.facing)
            self.fxp.flash_at(now)
            self.explosions += 1
            self.note('explosion', now)
            self.note('flash', now)
        if ex['who'] == ex['att']:
            ex['hit'] = True
        self.note('hit', now, who=ex['tgt'], dmg=dmg, hp=T.hp, air=ex['air'])
        if T.hp <= 0:
            self._end_round(now, ex['tgt'])

    def _end_exchange(self, ex, now):
        self.exchange = None
        self.last_att, self.last_hit = ex['att'], ex['hit']
        for s in 'ab':
            f = self.f[s]
            f.hover = False
            if ex['air']:
                f.fly_until = 0.0
                f.target = None
        self.cooldown_until = now + (self.rng.uniform(0.25, 0.5) if ex['range_after'] == 'close' else self.rng.uniform(0.5, 0.9))

    def _resolve(self, ex, now):
        """Compatibility shim for the V4 tests: resolve a bare exchange dict as a landed strike beat."""
        beat = dict(who='att', kind=ex.get('kind', 'strike'), anim=ex['move'], dmg=ex.get('dmg', 12), outcome='hit', pre=None,
                    react='hit_heavy' if ex.get('dmg', 12) >= 24 else 'hit', hitstop=0, knock=0, down=False)
        ex.update(who=ex['att'], tgt=ex['dfn'], beat=beat, air=False, main=self._main_fx(self.f[ex['att']].atlas, ex['move']))
        self._resolve_beat(ex, now)

    def _end_round(self, now, ko_loser):
        if ko_loser is not None:
            winner = 'b' if ko_loser == 'a' else 'a'
            self.banner = ('ko', now + 1.5, None)
            self.fxp.spawn_at('ko_stars', now + 0.7, *self.f[ko_loser].center(), fade_ms=3200)   # gone before the next round
        else:
            ha, hb = self.f['a'].hp, self.f['b'].hp
            winner = ('a' if self.rng.random() < 0.5 else 'b') if ha == hb else ('a' if ha > hb else 'b')
        self.wins[winner] += 1
        self.rounds.append(dict(n=self.round, winner=winner, ko=ko_loser is not None, hp={s: self.f[s].hp for s in 'ab'}, dur=round(now - self.round_t0, 2)))
        self.exchange = None
        w = self.f[winner]
        w.target, w.vx = None, 0.0
        w.play('taunt', now + 0.3, loop=False, hold='idle')
        self.ko_loser = ko_loser
        self.note('round', now, n=self.round, winner=winner, ko=ko_loser is not None)
        self._enter('round_end', now)

    # ---- physics
    def _move(self, b, now, dt):
        if dt <= 0 or b.stopped(now):
            return                                                 # hitstop: the whole body stands still
        if now < b.move_until and b.target is None and not b.down:
            b.x += b.vx * dt                                       # a reset step keeps its velocity for the anim's length
            b.x = max(40.0, min(self.stage.w - 40.0, b.x))
            return
        flying = now < b.fly_until and (b.target is not None or b.hover) and not b.down
        if b.target is not None and now >= b.knocked_until and not b.down:
            tx, ty = b.target
            dx, dy = tx - b.x, ty - b.y
            dist = math.hypot(dx, dy)
            if dist < 6:
                b.x, b.vx = tx, 0.0
                if flying:
                    b.y, b.vy = ty, 0.0
                    if b.hover:
                        return                                     # stays up there (air-to-air)
                    b.grounded = ty >= self.stage.floor_y - 1 or any(x0 <= tx <= x1 and abs(y - ty) < 2 for x0, x1, y in self.stage.platforms())
                    b.fly_until = 0.0
                b.target = None
                if b.anim in ('walk', 'dash', 'jump'):
                    b.play('idle', now)
            elif flying:
                sp = FLY if dist > 200 else max(260.0, dist * 4.0)
                b.vx, b.vy = dx / dist * sp, dy / dist * sp
                b.grounded = False
                if sp > 700:
                    b.trail.append((now, b.anim, b.frame(now)[0], b.facing, b.x, b.y))
            else:
                b.vx = math.copysign(min(WALK, abs(dx) / max(dt, 1e-3)), dx) if abs(dx) > 2 else 0.0
                if dy < -40 and b.grounded:                     # the target is higher: jump
                    b.vy = JUMP_VY
                    b.grounded = False
                    b.play('jump', now, loop=False, hold='idle')
                if b.grounded and b.anim == 'idle' and abs(b.vx) > 1:
                    b.play('walk', now)
                b.facing = 1 if dx > 0 else -1 if dx < 0 else b.facing
        if not flying:
            if not b.grounded:
                b.vy = min(MAX_FALL, b.vy + GRAVITY * dt)
            elif b.target is None and now >= b.knocked_until:
                b.vx *= max(0.0, 1.0 - 8.0 * dt)
                if abs(b.vx) < 5:
                    b.vx = 0.0
        y_prev = b.y
        b.x += b.vx * dt
        b.y += b.vy * dt
        if abs(b.vx) > 650 and not flying:
            b.trail.append((now, b.anim, b.frame(now)[0], b.facing, b.x, b.y))
        # walls (and the ceiling: nobody leaves through the HUD)
        if self.phase != 'exit':
            m = 40
            if b.x < m:
                b.x, b.vx = m, abs(b.vx) * 0.3
            elif b.x > self.stage.w - m:
                b.x, b.vx = self.stage.w - m, -abs(b.vx) * 0.3
            top = float(MIN_PLATFORM_Y)
            if b.y < top:
                b.y = top
                if b.vy < 0:
                    b.vy = 0.0
                if b.target is not None and b.target[1] < top:
                    b.target = (b.target[0], top)
        # landing (falling through a platform's top edge), not while flying or exiting
        if not flying and self.phase != 'exit' and b.vy >= 0:
            best = None
            for x0, x1, y in self.stage.platforms():
                if x0 - 10 <= b.x <= x1 + 10 and y_prev <= y <= b.y + 0.001:
                    if best is None or y < best:
                        best = y
            if best is not None:
                landed_from = b.vy
                b.y, b.vy, b.grounded = best, 0.0, True
                if landed_from > 900:
                    self.fxp.spawn_at('dust', now, b.x, b.y - 8)
                if b.anim in ('jump', 'dash') and not b.down:
                    b.play('idle', now)
        elif not flying and b.grounded:
            on = any(x0 - 10 <= b.x <= x1 + 10 and abs(y - b.y) < 2 for x0, x1, y in self.stage.platforms())
            if not on:
                b.grounded = False
        while b.trail and now - b.trail[0][0] > AFTERIMAGE_S:
            b.trail.popleft()

    def _window_collisions(self, b, now):
        """A knocked-back fighter whose centre enters a window rect cracks it (overlay only)."""
        if now >= b.knocked_until or now - b.last_crack < 0.45:
            return
        cx, cy = b.center()
        win = self.stage.window_at(cx, cy)
        if win is None:
            return
        heavy = abs(b.vx) > 600 or b.down
        kind = self.cracks.hit(win['id'], heavy)
        b.last_crack = now
        b.vx *= -0.35
        if kind is None:
            return
        self.note(kind, now)
        if kind == 'shatter':
            self._shatter(win, now, cx, cy)
        else:
            self.crack_marks.setdefault(win['id'], []).append((cx, cy, kind))
            self.fxp.spawn_at(kind, now, cx, cy, fade_ms=20000)
            if kind == 'crack_big':
                self._letters(win, now, cx, cy, 5)

    def _shatter(self, win, now, cx, cy):
        self.crack_marks.pop(win['id'], None)
        self.fxp.clear(tag=None)
        e = self.fx.get('shatter')
        for i in range(len(e.frames)):
            inst = self.fxp.spawn_at('shatter', now, cx + self.rng.uniform(-60, 60), cy + self.rng.uniform(-40, 40), 1,
                                     vx=self.rng.uniform(-260, 260), vy=self.rng.uniform(-500, -100), gravity=1500.0, fade_ms=1800)
            inst.data = {'frame': i}
        self._letters(win, now, cx, cy, 9)
        if self.backdrop is not None:
            self._punch_hole(win)
        self.note('hole' if self.backdrop is not None else 'shatter_done', now)

    def _letters(self, win, now, cx, cy, n):
        e = self.fx.get('letters')
        for _ in range(n):
            inst = self.fxp.spawn_at('letters', now, cx + self.rng.uniform(-50, 50), cy + self.rng.uniform(-30, 30), 1,
                                     vx=self.rng.uniform(-420, 420), vy=self.rng.uniform(-700, -200), gravity=1700.0, fade_ms=1600)
            inst.data = {'frame': self.rng.randrange(len(e.frames))}
            self.letters_spawned += 1

    def _punch_hole(self, win):
        """Freeze mode: the shattered window becomes a dark hole in the RAM backdrop (jagged inset edge)."""
        d = ImageDraw.Draw(self.backdrop)
        l, t, r, b = win['l'], win['t'], win['r'], win['b']
        pts = []
        n = 14
        for i in range(n):
            k = i / n
            pts.append((l + (r - l) * k, t + self.rng.uniform(0, 14)))
        for i in range(n):
            k = i / n
            pts.append((r - self.rng.uniform(0, 14), t + (b - t) * k))
        for i in range(n):
            k = i / n
            pts.append((r - (r - l) * k, b - self.rng.uniform(0, 14)))
        for i in range(n):
            k = i / n
            pts.append((l + self.rng.uniform(0, 14), b - (b - t) * k))
        d.polygon(pts, fill=HOLE)
        self.holes.append((l, t, r, b))

    # ---- drawables for the compositor
    def drawables(self, now):
        """-> [(image, left, top)] in stage px, back to front."""
        out = []
        for im, lx, ty, layer, inst in self.fxp.placements(now, layer='back'):
            out.append((im, lx, ty))
        for s in 'ab':
            b = self.f[s]
            for (t, anim, fr, facing, x, y) in b.trail:
                age = (now - t) / AFTERIMAGE_S
                if age >= 1.0:
                    continue
                im = self._sprite(b.atlas, anim, fr, facing, alpha=int(110 * (1.0 - age)))
                out.append((im, int(x - b.atlas.anchor(facing) * SCALE), int(y - b.atlas.ground_y * SCALE)))
        for s in 'ab':
            b = self.f[s]
            idx, _ = b.frame(now)
            im = self._sprite(b.atlas, b.anim, idx, b.facing)
            l, t, r, bt = b.sprite_rect()
            out.append((im, l, t))
        for im, lx, ty, layer, inst in self.fxp.placements(now, layer='front'):
            out.append((im, lx, ty))
        if self.banner:
            kind, until, x = self.banner
            im = self.fx.banner(kind)
            cx = self.stage.w / 2.0 if x is None else x
            out.append((im, int(cx - im.width / 2), int(self.stage.h * 0.28 - im.height / 2)))
        if self.phase not in ('entry', 'exit', 'done'):
            hud = self._hud()
            out.append((hud, 0, 0))
        out.append((self._exit_button(), self.exit_rect()[0], self.exit_rect()[1]))
        return out

    _sprite_cache = {}

    def _sprite(self, atlas, anim, idx, facing, alpha=None):
        key = (id(atlas), anim, idx, facing >= 0, alpha)
        im = self._sprite_cache.get(key)
        if im is None:
            if len(self._sprite_cache) > 160:
                self._sprite_cache.clear()
            fr = atlas.frame_image(anim, idx, facing)
            im = fr.resize((fr.width * SCALE, fr.height * SCALE), Image.NEAREST)
            if alpha is not None:
                im = im.copy()
                im.putalpha(im.getchannel('A').point(lambda v: v * alpha // 255))
            self._sprite_cache[key] = im
        return im

    _hud_cache = {}

    def _hud(self):
        key = (self.f['a'].hp, self.f['b'].hp, self.wins['a'], self.wins['b'], self.round, self.names['a'], self.names['b'], self.stage.w)
        im = self._hud_cache.get(key)
        if im is not None:
            return im
        w = self.stage.w
        im = Image.new('RGBA', (w, HUD_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        bar_w = int(w * 0.32)
        for s, x0, flip in (('a', 24, False), ('b', w - 24 - bar_w - (EXIT_W + EXIT_MARGIN + 12), True)):   # clear of the EXIT button
            hp = max(0, min(100, int(self.f[s].hp)))
            d.rectangle([x0, 18, x0 + bar_w, 34], fill=TRACK + (230,), outline=(230, 230, 240, 255), width=2)
            fw = int((bar_w - 4) * hp / 100.0)
            col = (150, 230, 150) if hp > 50 else (AMBER if hp > 25 else RED)
            if fw:
                if flip:
                    d.rectangle([x0 + bar_w - 2 - fw, 20, x0 + bar_w - 2, 32], fill=col + (255,))
                else:
                    d.rectangle([x0 + 2, 20, x0 + 2 + fw, 32], fill=col + (255,))
            nm = str(self.names[s])[:14]
            tw = int(d.textlength(nm, font=font(16, True)))
            text(d, (x0 + bar_w - tw if flip else x0, 38), nm, (245, 245, 250), 16)
            dots = ' '.join('*' if i < self.wins[s] else 'o' for i in range(rounds.ROUNDS_TO_WIN))
            dw = int(d.textlength(dots, font=font(14, True)))
            text(d, (x0 if flip else x0 + bar_w - dw, 38), dots, (255, 226, 122), 14)
        rt = f'ROUND {self.round}'
        text(d, (w // 2 - int(d.textlength(rt, font=font(14, True))) // 2, 20), rt, (255, 236, 120), 14)
        if len(self._hud_cache) > 32:
            self._hud_cache.clear()
        self._hud_cache[key] = im
        return im

    _exit_img = None

    def _exit_button(self):
        if Arena._exit_img is None:
            im = Image.new('RGBA', (EXIT_W, EXIT_H), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle([0, 0, EXIT_W - 1, EXIT_H - 1], 6, fill=(40, 24, 26, 235), outline=(255, 120, 110, 255), width=2)
            s = 'EXIT  (Esc)'
            text(d, (EXIT_W // 2 - int(d.textlength(s, font=font(14, True))) // 2, 9), s, (255, 230, 230), 14)
            Arena._exit_img = im
        return Arena._exit_img


# ---------------------------------------------------------------- compositor
class Compositor:
    """Writes only what changed: the union of last frame's and this frame's drawable rects, re-based on the backdrop
    (or transparency) and composited.  Shake moves the surface (the window), never the pixels."""

    def __init__(self, arena, surface):
        self.arena, self.surface = arena, surface
        self.prev = []
        self.full_pending = True
        self.frames = 0
        self.flashed = False

    def _render(self, now):
        a = self.arena
        W, H = a.stage.w, a.stage.h
        items = a.drawables(now)
        rects = [(x, y, x + im.width, y + im.height) for im, x, y in items]
        if self.full_pending:                                   # first frame: the whole surface once (backdrop + everything)
            self.full_pending = False
            base = a.backdrop.copy() if a.backdrop is not None else Image.new('RGBA', (W, H), (0, 0, 0, 0))
            for im, x, y in items:
                _paste(base, im, x, y)
            self.surface.write(base, 0, 0)
            self.prev = rects
            self.surface.offset(*a.fxp.shake(now))
            self.surface.flush()
            self.frames += 1
            return [(0, 0, W, H)]
        if a.holes:
            rects += [tuple(h) for h in a.holes]
            a.holes = []
        dirty = _merge(self.prev + rects, W, H)
        for (x0, y0, x1, y1) in dirty:
            if a.backdrop is not None:
                base = a.backdrop.crop((x0, y0, x1, y1))
            else:
                base = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0))
            for im, x, y in items:
                if x < x1 and x + im.width > x0 and y < y1 and y + im.height > y0:
                    _paste(base, im, x - x0, y - y0)
            self.surface.write(base, x0, y0)
        self.prev = rects
        dx, dy = a.fxp.shake(now)
        self.surface.offset(dx, dy)
        self.surface.flush()
        self.frames += 1
        return dirty

    def render(self, now):
        a = self.arena
        flash = a.fxp.flash(now)
        if flash <= 0 and not self.flashed:
            return self._render(now)
        W, H = a.stage.w, a.stage.h          # V5: a white screen flash is one full frame (and the frame after it clears it)
        items = a.drawables(now)
        base = a.backdrop.copy() if a.backdrop is not None else Image.new('RGBA', (W, H), (0, 0, 0, 0))
        for im, x, y in items:
            _paste(base, im, x, y)
        if flash > 0:                        # the whole overlay goes white for a frame (click-through stays: it is only paint)
            base.alpha_composite(Image.new('RGBA', (W, H), (255, 255, 255, int(255 * min(1.0, flash)))))
        self.surface.write(base, 0, 0)
        self.prev = [(x, y, x + im.width, y + im.height) for im, x, y in items]
        self.flashed = flash > 0
        self.surface.offset(*a.fxp.shake(now))
        self.surface.flush()
        self.frames += 1
        return [(0, 0, W, H)]


def _paste(dst, src, x, y):
    w, h = dst.size
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(src.width, w - x), min(src.height, h - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    dst.alpha_composite(src.crop((sx0, sy0, sx1, sy1)), (max(0, x), max(0, y)))


def _merge(rects, W, H, limit=10):
    rs = []
    for x0, y0, x1, y1 in rects:
        x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(W, int(x1)), min(H, int(y1))
        if x1 > x0 and y1 > y0:
            rs.append((x0, y0, x1, y1))
    changed = True
    while changed:
        changed = False
        out = []
        while rs:
            a = rs.pop()
            i = 0
            while i < len(rs):
                b = rs[i]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    a = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                    rs.pop(i)
                    changed = True
                else:
                    i += 1
            out.append(a)
        rs = out
    while len(rs) > limit:
        best = None
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                u = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                cost = (u[2] - u[0]) * (u[3] - u[1])
                if best is None or cost < best[0]:
                    best = (cost, i, j, u)
        _, i, j, u = best
        rs = [r for k, r in enumerate(rs) if k not in (i, j)] + [u]
    return rs


def synthetic_backdrop(w, h, seed=1):
    """A test backdrop that is obviously not a screen: coloured bands (tests only)."""
    im = Image.new('RGBA', (w, h), (30, 34, 44, 255))
    d = ImageDraw.Draw(im)
    rng = random.Random(seed)
    for i in range(0, w, 160):
        d.rectangle([i, 0, i + 80, h], fill=(rng.randrange(40, 90), rng.randrange(40, 90), rng.randrange(60, 120), 255))
    return im
