"""Rounds, HP and winners (docs/V4-WORKORDER.md "Rounds and winners").

A *match* is best-of-3 rounds.  Both fighters start a round at 100 HP; damage per landed move = power (1/2/3) * 12,
the ultimate does 40; a round ends at 0 HP or after ROUND_CAP_S (higher HP wins, a tie is drawn from the seed).
Who attacks each exchange is drawn from the plan's seed.  In `decided` mode the draw is weighted by each side's
health score = (100 - ctx%) + (20 if not at its limit) + (10 if working); unknown context counts as 50%.  In `random`
mode both sides are even.  The whole match is one deterministic timeline built from the plan, so the two fighter
processes (or the arena) agree on every contact, every HP value and the winner without talking.

Timeline entries are (t, anim, opts) like every other bout; entries whose "anim" starts with '@' are directives:
  @hp      {'hp': {slot: hp}, 'round': n, 'wins': {slot: n}}        publish HP (both sides)
  @fx      {'fx': name, 'anchor': optional}                           spawn an effect on this fighter
  @banner  {'banner': round1|round2|round3|fight|ko|winner, 'until': t, 'over': slot|None}   (left side only)
  @record  {'winner': slot, 'loser': slot, 'score': {slot: n}}        write record.json (left side only)
  @shake   {'frames': n, 'amp': px}                                   the move's own screen shake on its hit frame (V5)
  @flash   {'alpha': a, 'ms': n}                                      white flash (an ultimate landing) (V5; V6 >= 100 ms)
  @impact  {'ms': n, 'on': slot}                                      V6 impact frames on a heavy hit / ultimate / KO (fx `impact` on the
                                                                      struck fighter, a strong flash when that art is missing; nothing
                                                                      at all when control.json `flashes` is off)
  @whiff   {'react_to': move}                                         the attack missed: logged like a reaction, nothing plays (V5)
Move entries may carry 'to' + 'slide_ms' (the fighter slides to that x while the move plays: dash-ins, backdashes,
knockback; V6: the slide pauses during hitstop), 'hitstop' (ms both fighters freeze from the contact instant),
'slow' [t0, t1, k] (V6 slow motion: the animation clock runs at k between t0 and t1) and 'hold' (a one-shot keeps its
last frame instead of returning to idle: a brace, a slump).

V5 choreography (choreo.py): a seeded no-repeat picker weighted by category and situation; openers (dash-in jab, jump-in
kick, sweep), defender answers (block, crouch block vs highs, parry -> counter, backdash whiff, getting hit), combos with
hitstop, pressure vs spacing resets, specials at range (projectiles), a super when the hit meter fills, the ultimate once
per match at a dramatic moment (round point / low HP) with flash + shake, knockdown -> getup on big hits, a taunt after a
whiffed ultimate, and one air-to-air exchange per round.

W/L per character go to %LOCALAPPDATA%\\minis\\record.json, written atomically; only character ids, never names of
anything else.
"""
from __future__ import annotations
import json, random, time
from pathlib import Path

from . import choreo, config as cfgmod
from .bus import write_json_atomic
from .effects import EffectPlayer

HP_MAX = 100
DMG_PER_POWER = 12
DMG_ULTIMATE = 40
ROUND_CAP_S = 25.0
ROUNDS_TO_WIN = 2
MODES = ('decided', 'random')
BANNER_S = {'round': 1.2, 'fight': 0.7, 'ko': 1.5, 'winner': 2.6, 'time': 1.2}
NEEDS = ('block', 'block_hit', 'hit', 'hit_heavy', 'knockdown', 'ko', 'getup', 'taunt', 'victory', 'idle')
STRIKES = ('jab', 'cross', 'uppercut', 'low_kick', 'roundhouse')


# ---------------------------------------------------------------- health score
def health_score(state, ctx_pct) -> float:
    """(100 - ctx%) + 20 if not at the limit + 10 if working.  Unknown context counts as 50%."""
    ctx = 50.0 if ctx_pct is None else max(0.0, min(100.0, float(ctx_pct)))
    return (100.0 - ctx) + (0.0 if state == 'limit' else 20.0) + (10.0 if state == 'working' else 0.0)


def score_of_snapshot(snap) -> float:
    return health_score(getattr(snap, 'state', None), getattr(snap, 'ctx_pct', None)) if snap is not None else health_score(None, None)


def score_of_bus(payload) -> float:
    p = payload or {}
    return health_score(p.get('state'), p.get('ctx'))


def p_left(mode, scores, left, right) -> float:
    """Probability that the left fighter attacks a given exchange."""
    if mode != 'decided':
        return 0.5
    a, b = float(scores.get(left, 0.0)), float(scores.get(right, 0.0))
    if a + b <= 0 or abs(a - b) < 1e-9:
        return 0.5
    return a / (a + b)


def damage_of(atlas, move) -> int:
    if move == atlas.ultimate() and move not in STRIKES:
        return DMG_ULTIMATE
    return int(atlas.power(move, 1)) * DMG_PER_POWER


# ---------------------------------------------------------------- the match timeline
def strike_pool(atlas):
    return choreo.strike_pool(atlas)


def possible(atlases_by_slot) -> bool:
    for a in atlases_by_slot.values():
        if any(n not in a.anim for n in NEEDS) or not strike_pool(a):
            return False
    return True


def _contact_s(atlas, move):
    a = atlas.anim[move]
    if 'hit_frame' in a:
        return atlas.contact_ms(move) / 1000.0
    return atlas.total_ms(move) * 0.6 / 1000.0            # a charge-then-release super / ultimate without hit_frame metadata


# ---------------------------------------------------------------- shared bout machinery (V5: choreo.py drives both the match and spar / clash)
CLOSE_EXTRA, FAR_EXTRA = 14, 40       # hip distance beyond gap_px that counts as "far"; where a spacing reset puts them
KNOCK_SLIDE_MS = 180
KNOCK_SLIDE_MS_BIG = 300              # V6: a heavy hit / knockdown slides further, so it takes longer (skid + dust)
SPAN_PX = 110                         # a bout never drifts further than this from its centre (the zone is not in the plan)
MIN_APART = 22                        # V6: hips closer than this overlap the bodies (idle sprites are ~24 px wide; was 12)
BODY_FRONT = 9                        # V6: px from a defender's hip to the front of its body: a strike stands at reach + this
LUNGE_FRAC = 0.85                     # a lunge slides in over this share of the move's wind-up
IMPACT_MS = 130                       # V6 impact frames (heavy hits, ultimates, KOs): 100-160 ms
FLASH_MS = 120                        # V6 white flash on an ultimate landing (was 60 ms: shorter than one redraw)
KO_HITSTOP_MS = 280                   # the match-deciding blow freezes longer...
SLOW_S, SLOW_K = 0.55, 0.35           # ...then plays the fall in slow motion: SLOW_S wall seconds at SLOW_K speed
POST_KO_S = 3.4                       # final KO contact -> end of the match (finisher beat: freeze, fall, dust, pose, slump up)
POST_KO_MAX_S = 3.5
GETUP_SLOW_K = 0.6                    # the beaten fighter's get-up after the final KO plays at this speed (a slump, not a kip-up)
SLUMP = ('facepalm', 'shrug', 'dizzy')    # a fighter that lost on time slumps instead of falling over
BRACE_MIN_S = 0.45                    # a wind-up at least this long gets a guard / worried pose from the defender
WORRIED_HP = 30
STAND_OVERLAP = 8                     # two idle silhouettes (weapons included) may overlap by this much, never more


def body_front(atlas):
    """px (RES 1) from the hip to the front edge of the idle silhouette, weapon included: how much room a fighter takes up
    toward its opponent.  Read from the art, so a redrawn or new character spaces itself."""
    key = '_v6_front'
    v = getattr(atlas, key, None)
    if v is None:
        try:
            bb = atlas.frame_image('idle', 0, 1).getbbox()
            v = max(8.0, (bb[2] - atlas.anchor(1)) / float(max(1, atlas.res))) if bb else 14.0
        except Exception:
            v = 14.0
        try:
            setattr(atlas, key, v)
        except Exception:
            pass
    return v


class _Emitter:
    """Per-slot timeline entries with a LAZY return to idle: a chained move (combo, counter) starting before the previous
    move's return cancels that return, so the sorted timeline never idles a fighter mid-combo."""

    def __init__(self, slots, t0):
        self.tl = {s: [] for s in slots}
        self.pending = {s: None for s in slots}
        self.free = {s: t0 for s in slots}

    def play(self, slot, t, anim, opts, dur, then='idle'):
        p = self.pending[slot]
        if p is not None and p[0] < t - 1e-6:                   # a return that would start with the next move is dropped
            self.tl[slot].append((p[0], p[1], {}))
        self.pending[slot] = (t + dur, then) if then else None
        self.tl[slot].append((t, anim, opts))
        self.free[slot] = t + dur

    def directive(self, slot, t, name, opts):
        self.tl[slot].append((t, name, opts))

    def mark(self):
        return {s: len(v) for s, v in self.tl.items()}, dict(self.pending), dict(self.free)

    def rollback(self, m):
        lens, pend, free = m
        for s in self.tl:
            del self.tl[s][lens[s]:]
        self.pending, self.free = dict(pend), dict(free)

    def finish(self):
        for s, p in self.pending.items():
            if p is not None:
                self.tl[s].append((p[0], p[1], {}))
            self.pending[s] = None


class Bout:
    """Plays choreo beats into an _Emitter with positions, HP, hit meters, projectiles and effects.  `friendly` (spar /
    clash) has no HP, no supers / ultimates / knockdowns.  Deterministic in (plan, atlases, fx)."""

    def __init__(self, plan, atlases, fx=None, friendly=False):
        self.left, self.right = plan['left'], plan['right']
        chars = plan.get('chars') or {}
        self.A = {s: atlases[chars.get(s, s)] for s in (self.left, self.right)}
        self.rng = random.Random(plan['seed'])
        self.fx = fx
        self.friendly = friendly
        self.pos = {s: float(plan['pos'][s]) for s in (self.left, self.right)}
        self.mid = (self.pos[self.left] + self.pos[self.right]) / 2.0
        # V6: the pair's own room: idle silhouettes (weapons included) overlap by at most STAND_OVERLAP
        self.apart = max(MIN_APART, body_front(self.A[self.left]) + body_front(self.A[self.right]) - STAND_OVERLAP)
        self.gap = max(self.apart, abs(self.pos[self.right] - self.pos[self.left])) or 24.0
        self.span = float(plan.get('span', SPAN_PX))
        self.facing = {self.left: 1, self.right: -1}
        self.pick = {s: choreo.Picker(self.rng, self.A[s]) for s in (self.left, self.right)}
        self.em = _Emitter((self.left, self.right), plan['t0'])
        self.hp = {self.left: HP_MAX, self.right: HP_MAX}
        self.meter = {self.left: 0.0, self.right: 0.0}
        self.used_ult = {self.left: False, self.right: False}
        self.ult_used = False                               # V6: one ultimate per MATCH between both fighters
        self.boost = [s for s in (plan.get('boost') or []) if s in (self.left, self.right)]     # finished a task: super first
        self.final = False                                  # set by make_match: a KO in this exchange ends the match
        self.ko_info = None                                 # (tc, hitstop s, slow window) of the last KO hit
        self.down_until = {}                                # slot -> when its get-up ends (no hits on a fighter on the floor)
        self.wins = {self.left: 0, self.right: 0}
        self.projs = []
        self.beats = {self.left: [], self.right: []}        # every beat played, by the fighter that played it (tests, previews)
        self.n_air = 0
        self.last_att = None
        self.last_hit = False

    # ---- helpers
    def other(self, s):
        return self.right if s == self.left else self.left

    def tot(self, s, n):
        return self.A[s].total_ms(n) / 1000.0 if n in self.A[s].anim else 0.0

    def dist(self):
        return abs(self.pos[self.right] - self.pos[self.left])

    def range(self):
        return 'far' if self.dist() > self.gap + CLOSE_EXTRA else 'close'

    def clamp(self, s, x):
        lo, hi = self.mid - self.span, self.mid + self.span
        x = max(lo, min(hi, x))
        o = self.other(s)
        if s == self.left:
            x = min(x, self.pos[o] - self.apart)
        else:
            x = max(x, self.pos[o] + self.apart)
        return x

    def fx_reach(self, name):
        if self.fx is None:
            return 0.0
        return EffectPlayer(self.fx, res=self.A[self.left].res).reach(name)

    def fx_lead(self, name):
        return _fx_hit_s(self.fx.get(name)) if self.fx is not None else 0.0

    def main_fx(self, s, move):
        """The move's own effect (named after it) from its `fx` list, else its last listed effect."""
        sched = self.A[s].move_fx(move)
        for off, name, until in sched:
            if name == move:
                return name
        return sched[-1][1] if sched else None

    # ---- one exchange
    def exchange(self, att, t, k, dramatic=False, air=False, comeback=False, boost=False, ult_sure=False):
        """Plays one exchange starting at `t`.  -> (t_next, ko_loser, played) ; `played` False when nothing fits."""
        dfn = self.other(att)
        A, D = self.A[att], self.A[dfn]
        ult = A.ultimate()
        reach = self.fx_reach(self.main_fx(att, ult)) if ult else 0.0
        edge = 0.0 if self.friendly else choreo.edge_for(self.hp[att], self.hp[dfn], self.wins[att], self.wins[dfn])
        sit = dict(range=self.range(), meter=self.meter[att], ult_ok=(not self.friendly and not self.ult_used), dramatic=dramatic,
                   friendly=self.friendly, air=air and not boost, k=k, ult_reaches=reach >= self.dist() - 10, edge=edge,
                   comeback=comeback and not self.friendly, boost=boost, ult_sure=ult_sure)
        air = sit['air']
        ex = choreo.plan_exchange(self.rng, self.pick[att], self.pick[dfn], sit)
        if air:
            self.n_air += 1
        em, tot = self.em, self.tot
        t = max(t, em.free[att], em.free[dfn])
        ko = None
        if air and 'jump' in D.anim:                          # air-to-air: the defender is up there too
            em.play(dfn, t, 'jump', {}, tot(dfn, 'jump'))
        for b in ex['beats']:
            who = att if b['who'] == 'att' else dfn
            tgt = self.other(who)
            if b['kind'] == 'move':
                t = max(t, em.free[who])
                dur = tot(who, b['anim'])
                if b['dx'] > 0:
                    x = self.pos[tgt] - self.facing[who] * self.gap
                elif b['dx'] == 0:                             # a juggle jump: straight up after the launched defender
                    x = self.pos[who]
                else:
                    x = self.pos[who] - self.facing[who] * (FAR_EXTRA if b['anim'] == 'backdash' else FAR_EXTRA * 0.75)
                x = self.clamp(who, x)
                em.play(who, t, b['anim'], {'to': x, 'slide_ms': int(dur * 1000)}, dur)
                self.pos[who] = x
                if b['anim'] in ('dash', 'backdash') and self.fx is not None:
                    em.directive(who, t, '@fx', {'fx': 'dust', 'anchor': 'ground'})
                t = t + dur * (0.45 if b['anim'] == 'jump' else 1.0) + 0.03     # a jump-in kick leaves the apex, not the landing
                self.beats[who].append(b)
                continue
            if b['kind'] == 'emote':
                t = max(t, em.free[who]) + 0.1
                em.play(who, t, b['anim'], {}, tot(who, b['anim']))
                self.beats[who].append(b)
                continue
            # ---- an attack beat (strike / special / super / ultimate / counter)
            kind, move = b['kind'], b['anim']
            t = max(t, em.free[who])
            if self.down_until.get(tgt, 0.0) > t:
                t = self.down_until[tgt]                       # never hit a fighter who is still on the floor / getting up
            if kind == 'special' and not choreo.has_projectile(self.A[who], move):
                continue
            # finish KOs with a signature move: a plain strike that would empty the bar becomes the signature strike
            sig_strike = self.A[who].signature()['strike']
            if (b['outcome'] == 'hit' and not self.friendly and kind in ('strike', 'counter') and self.hp[tgt] - b['dmg'] <= 0
                    and sig_strike and move != sig_strike and not b.get('juggle') and self.pick[who].used[sig_strike] < choreo.MAX_PER_ROUND):
                move = sig_strike
                b = dict(b, anim=move, dmg=max(b['dmg'], choreo.damage_of(self.A[who], move, 'strike')),
                         hitstop=choreo.hitstop_ms(self.A[who], move, 'strike'), finisher=True)
                self.pick[who].note(move)
            lunge = bool(b.get('lunge')) and kind == 'strike' and not air
            if (not lunge and self.dist() > self.gap + CLOSE_EXTRA and kind in ('strike', 'counter', 'super')
                    and 'dash' in self.A[who].anim and not air and not b.get('juggle')):
                dur = tot(who, 'dash')                         # never swing at the air: close in first
                x = self.clamp(who, self.pos[tgt] - self.facing[who] * self.gap)
                em.play(who, t, 'dash', {'to': x, 'slide_ms': int(dur * 1000)}, dur)
                self.pos[who] = x
                t += dur + 0.03
            cont = _contact_s(self.A[who], move)
            tc = t + cont
            step = None                                        # V6: stand at the move's own reach (no overlap, no air swings)
            if kind in ('strike', 'counter') and not air and not b.get('juggle'):
                want = max(self.apart, choreo.reach_of(self.A[who], move) + BODY_FRONT)
                if lunge or abs(self.dist() - want) > 3:
                    x = self.clamp(who, self.pos[tgt] - self.facing[who] * want)
                    if abs(x - self.pos[who]) > 1:
                        step = {'to': x, 'slide_ms': int(max(60, cont * (LUNGE_FRAC if lunge else 0.6)) * 1000)}
                        self.pos[who] = x
            proj = None
            if kind == 'special':
                a = self.A[who].anim[move]
                spawn = t + self.A[who].start_ms(move, a['proj_frame']) / 1000.0
                speed = float(self.A[who].meta['projectile']['speed'])
                arrive = spawn + max(0.0, self.dist() - 12) / speed
                tc = max(tc, arrive)
                proj = dict(owner=who, spawn=spawn, arrive=arrive, dir=self.facing[who], x0=self.pos[who], speed=speed, move=move)
            elif kind == 'ultimate' and self.fx is not None:
                name = self.main_fx(who, move)
                if name:
                    e = self.fx.get(name)
                    k_px = self.A[who].res / float(e.res)
                    spawn = max(t, t + [off for off, n, u in self.A[who].move_fx(move) if n == name][0] - self.fx_lead(name))
                    if e.grow:
                        tc = max(tc, spawn + e.grow['ms'] / 1000.0 * min(1.0, self.dist() / max(1.0, e.grow['to_w'] * k_px)))
                    elif e.travel:
                        tc = max(tc, spawn + max(0.0, self.dist() - 16) / (e.travel['speed'] * k_px))
            dmg = b['dmg']
            outcome = b['outcome']
            if outcome == 'hit' and not self.friendly:
                self.hp[tgt] = max(0, self.hp[tgt] - dmg)
                self.meter[who] += dmg
                self.meter[tgt] += dmg / 2.0
            if kind == 'super':
                self.meter[who] = 0.0
            if kind == 'ultimate':
                self.used_ult[who] = True
                self.ult_used = True
            react = b['react']
            if outcome == 'hit' and not self.friendly and self.hp[tgt] <= 0:
                react, ko = 'knockdown', tgt
            hitstop = b['hitstop']
            slow = None
            final_ko = ko is not None and self.final and self.wins[who] + 1 >= ROUNDS_TO_WIN
            if final_ko:                                       # the finisher: a long freeze, then the fall in slow motion
                hitstop = max(hitstop, KO_HITSTOP_MS)
                ts = tc + hitstop / 1000.0
                slow = [round(ts, 4), round(ts + SLOW_S, 4), SLOW_K]
            hs = hitstop / 1000.0
            slow_extra = (SLOW_S * (1.0 - SLOW_K)) if slow else 0.0
            opts = {'contact': tc, 'kind': kind, 'damage': dmg, 'hitstop': hitstop, 'outcome': outcome}
            if step:
                opts.update(step)
            if slow:
                opts['slow'] = slow
            em.play(who, t, move, opts, tot(who, move) + hs + slow_extra)
            if lunge and self.fx is not None:
                em.directive(who, t, '@fx', {'fx': 'dust', 'anchor': 'ground'})
            if kind in ('ultimate', 'super') or (kind == 'special' and self.fx is not None):
                for off, fx_name, until in self.A[who].move_fx(move):
                    if kind == 'special' and fx_name == move:
                        continue                              # the projectile sprite is the special's own effect on the taskbar
                    lead = self.fx_lead(fx_name) if fx_name == move else 0.0
                    em.directive(who, max(t, t + off - lead), '@fx', {'fx': fx_name, 'kind': kind, 'move': move, 'until': (t + until) if until else None})
            if proj is not None:
                self.projs.append(proj)
            # the defender: a long wind-up (super, ultimate, charged special) gets a guard pose, or a worried one on low HP
            charged = kind in ('super', 'ultimate', 'special') and cont >= BRACE_MIN_S
            if charged and b.get('pre') != 'block':
                low = (not self.friendly) and self.hp[tgt] + (dmg if outcome == 'hit' else 0) < WORRIED_HP
                brace = 'crouch_block' if low and 'crouch_block' in self.A[tgt].anim else ('block' if 'block' in self.A[tgt].anim else None)
                tb = max(em.free[tgt], t + 0.12)
                t_brace_end = tc - (0.15 if b.get('pre') == 'backdash' else 0.0)
                if brace and t_brace_end - tb > 0.1:
                    em.play(tgt, tb, brace, {'hold': True, 'brace': True}, t_brace_end - tb, then=None)
            if b.get('pre'):
                if b['pre'] == 'backdash':                     # whiff: gone before the hit frame
                    x = self.clamp(tgt, self.pos[tgt] - self.facing[tgt] * FAR_EXTRA)
                    dur = tot(tgt, 'backdash')
                    em.play(tgt, max(em.free[tgt], tc - 0.15), 'backdash', {'to': x, 'slide_ms': int(dur * 1000)}, dur)
                    self.pos[tgt] = x
                else:
                    tp = min(max(em.free[tgt], tc - 0.25), tc) if not charged else min(max(em.free[tgt], t + 0.12), tc)
                    em.play(tgt, tp, b['pre'], {'hold': True}, max(0.0, tc - tp), then=None)
            sh = choreo.move_shake(self.A[who], move)
            if react is None:
                em.directive(tgt, tc, '@whiff', {'react_to': move})
            else:
                ropts = {'react_to': move, 'damage': dmg, 'hitstop': hitstop, 'outcome': outcome}
                if slow:
                    ropts['slow'] = slow
                if not self.friendly:
                    ropts['hp'] = dict(self.hp)
                knock = b['knock']
                if react == 'knockdown' and ko:
                    knock = max(knock, choreo.KNOCK_PX['knockdown'])
                if knock:
                    x = self.clamp(tgt, self.pos[tgt] + self.facing[who] * knock)
                    big = react in ('hit_heavy', 'knockdown')
                    ropts.update(to=x, slide_ms=KNOCK_SLIDE_MS_BIG if big else KNOCK_SLIDE_MS)    # clock time: waits out hitstop, slows in slow-mo
                    self.pos[tgt] = x
                rdur = tot(tgt, react) + hs + slow_extra
                # a knockdown that is not a KO stays on the floor (no return to idle) until the get-up starts
                then = ('ko' if ko else None) if react == 'knockdown' else 'idle'
                em.play(tgt, tc, react, ropts, rdur, then=then)
                if outcome in ('block', 'crouch_block', 'parry'):
                    em.directive(tgt, tc, '@fx', {'fx': 'block_spark'})
                elif outcome == 'hit':
                    em.directive(tgt, tc, '@fx', {'fx': 'hit_heavy' if react in ('hit_heavy', 'knockdown') else 'hit_light'})
                    if react == 'hit_heavy':
                        em.directive(tgt, tc + 0.05, '@fx', {'fx': 'dust', 'anchor': 'ground'})       # the skid
                    if kind == 'ultimate':
                        name = self.main_fx(who, move)
                        imp = f'{move}_impact' if self.fx is not None and self.fx.has_art(f'{move}_impact') else 'explosion'
                        em.directive(tgt, tc, '@fx', {'fx': imp, 'kind': kind, 'impact': True})
                        for s in (who, tgt):
                            em.directive(s, tc, '@flash', {'alpha': 0.7, 'ms': FLASH_MS})
                    if kind in ('ultimate', 'super') or ko is not None or dmg >= 3 * choreo.DMG_PER_POWER:
                        for s in (who, tgt):                   # impact frames: heavy hits, ultimates and KOs only, never every hit
                            em.directive(s, tc, '@impact', {'ms': IMPACT_MS, 'on': tgt})
                if sh and outcome == 'hit':
                    for s in (who, tgt):
                        em.directive(s, tc, '@shake', dict(sh))
                if react == 'knockdown':
                    em.directive(tgt, tc + 0.15, '@fx', {'fx': 'dust', 'anchor': 'ground'})
                    if ko:
                        t_stars = tc + rdur
                        em.directive(tgt, t_stars, '@fx', {'fx': 'ko_stars', 'until': t_stars + (1.8 if final_ko else 2.4)})
                        em.directive(tgt, t_stars - 0.05, '@fx', {'fx': 'dust', 'anchor': 'ground'})       # lands
                        self.ko_info = dict(tc=tc, hs=hs, slow=slow, down=tc + rdur)
                    elif 'getup' in self.A[tgt].anim:
                        em.play(tgt, tc + rdur, 'getup', {}, tot(tgt, 'getup'))      # springs up the moment the fall ends
                        self.down_until[tgt] = tc + rdur + tot(tgt, 'getup')
            self.beats[who].append(dict(b, react=react))
            t = tc + hs + 0.12 if kind != 'counter' else em.free[who]
            if ko:
                break
            if b['kind'] == 'counter':
                t = max(em.free[who], em.free[tgt])
        if ex['beats'] and ex['beats'][-1]['kind'] == 'move':
            pass
        t_next = max(em.free[att], em.free[dfn]) + (0.25 if ex['range_after'] == 'close' else 0.5)
        self.last_att = att
        self.last_hit = any(b.get('outcome') == 'hit' and b['who'] == 'att' for b in ex['beats'])
        return t_next, ko, ex


def _fx_player_res(atlas):
    return atlas.res


def make_match(plan, atlases, fx=None):
    """-> (timeline {slot: [(t, anim, opts)]}, t_end, summary).  Deterministic in `plan` (+ the atlases / fx on disk).
    summary carries winner, loser, wins, rounds, mode, p_left, projs (projectiles for the brain), beats (per slot).
    V6 story: the trailing fighter's odds tilt up (choreo.edge_for), whoever lost a round gets one comeback exchange
    in the next, a slot in plan['boost'] (its agent just finished a task) opens with its signature super, and the
    match-deciding KO plays a finisher beat (freeze + impact, slow-motion fall, dust, the winner's pose under the name
    banner, the loser slumping up) inside POST_KO_S.  A round that runs out of time shows TIME and the loser slumps."""
    bout = Bout(plan, atlases, fx, friendly=False)
    bout.final = True
    left, right = bout.left, bout.right
    A, rng, em, tot = bout.A, bout.rng, bout.em, bout.tot
    mode = plan.get('mode') if plan.get('mode') in MODES else 'decided'
    pl = p_left(mode, plan.get('scores') or {}, left, right)
    other = bout.other
    tl = em.tl

    def banner(t, kind, over=None, until=None, **kw):
        dur = BANNER_S.get(kind, BANNER_S['round'])
        em.directive(left, t, '@banner', dict({'banner': kind, 'until': until if until is not None else t + dur, 'over': over}, **kw))

    def slump_of(s):
        return next((n for n in SLUMP if n in A[s].anim), None)

    wins = bout.wins
    rounds = []
    t = plan['t0']
    n_round = 0
    ko_loser = None
    comeback_for = None
    story = dict(comebacks=0, boosts=0)
    ult_rolled = False
    while max(wins.values()) < ROUNDS_TO_WIN:
        n_round += 1
        bout.hp = hp = {left: HP_MAX, right: HP_MAX}
        for p in bout.pick.values():
            p.new_round()
        if ko_loser is not None:                                   # the fallen fighter gets up before the next round
            em.play(ko_loser, t - tot(ko_loser, 'getup') - 0.1, 'getup', {}, tot(ko_loser, 'getup'))
        for w in (left, right):
            em.directive(w, t, '@hp', {'hp': dict(hp), 'round': n_round, 'wins': dict(wins)})
            em.play(w, t, 'idle', {}, 0.0, then=None)
        banner(t, f'round{min(3, n_round)}')
        banner(t + BANNER_S['round'], 'fight')
        t_round = t + BANNER_S['round'] + BANNER_S['fight'] + 0.1
        t = t_round
        k = 0
        ko_loser = None
        bout.ko_info = None
        air_done = False
        comeback_due = comeback_for
        while True:
            boost = comeback = False
            if bout.boost and k < 2:
                att, boost = bout.boost[0], True                   # its agent just finished a task: the signature super opens
            elif comeback_due is not None and k == 1:
                att, comeback = comeback_due, True                 # lost the last round: one exchange where everything lands
            elif bout.last_att is not None and bout.last_hit and rng.random() < 0.45:
                att = bout.last_att                                # pressure: the winner of the last exchange keeps coming
            else:
                att = left if rng.random() < pl else right
            dfn = other(att)
            air = (not air_done and k >= 1 and rng.random() < 0.3) or (not air_done and k >= 4)
            air = air and not (boost or comeback)
            drama = choreo.dramatic(wins[att], hp[att], hp[dfn], k) and not bout.ult_used and not ult_rolled and not (boost or comeback)
            if drama:                                              # ONE roll per match, the first time anyone qualifies (~0.35 / match)
                ult_rolled = True
                drama = rng.random() < choreo.ULT_CHANCE
            mark = em.mark()
            saved = (dict(bout.pos), dict(bout.meter), dict(bout.used_ult), dict(hp), list(bout.projs), {s: list(v) for s, v in bout.beats.items()},
                     bout.n_air, bout.ult_used, dict((s, (p.last, dict(p.used), dict(p.counts))) for s, p in bout.pick.items()))
            t_next, ko, ex = bout.exchange(att, t, k, dramatic=drama, air=air, comeback=comeback, boost=boost, ult_sure=drama)
            if t_next - t_round > ROUND_CAP_S and k > 0:
                em.rollback(mark)                                  # time: the round is called on HP
                bout.pos, bout.meter, bout.used_ult, hp, bout.projs, bout.beats, bout.n_air, bout.ult_used = saved[:8]
                for s, (last, used, counts) in saved[8].items():
                    p = bout.pick[s]
                    p.last, p.used, p.counts = last, choreo.Counter(used), choreo.Counter(counts)
                bout.hp = hp
                break
            if boost:
                bout.boost.pop(0)
                story['boosts'] += 1
            if comeback:
                comeback_due = None
                story['comebacks'] += 1
            if air:
                air_done = True
            t = t_next
            k += 1
            if ko is not None:
                ko_loser = ko
                break
        # ---- round result
        if ko_loser is not None:
            winner = other(ko_loser)
            ki = bout.ko_info
            banner(ki['tc'], 'ko')
            if wins[winner] + 1 >= ROUNDS_TO_WIN:
                t_end_round = ki['tc']                             # the finisher beat below takes over
            else:
                em.play(winner, max(em.free[winner], ki['down'] + 0.1), 'taunt', {}, tot(winner, 'taunt'))
                t_end_round = em.free[winner]
        else:
            if hp[left] == hp[right]:
                winner = left if rng.random() < 0.5 else right
            else:
                winner = left if hp[left] > hp[right] else right
            tw = max(em.free[left], em.free[right])
            banner(tw, 'time')                                     # called on time: say so, and nobody falls over unprovoked
            loser_r = other(winner)
            sl = slump_of(loser_r)
            if sl:
                em.play(loser_r, tw + 0.3, sl, {'hold': True}, tot(loser_r, sl), then=None)
            if wins[winner] + 1 >= ROUNDS_TO_WIN:
                t_end_round = tw + 0.3
            else:
                em.play(winner, tw + 0.3, 'taunt', {}, tot(winner, 'taunt'))
                t_end_round = max(em.free[winner], em.free[loser_r])
        wins[winner] += 1
        rounds.append(dict(n=n_round, winner=winner, hp=dict(hp), ko=ko_loser is not None, t0=t_round, t1=t_end_round, exchanges=k))
        for w in (left, right):
            em.directive(w, t_end_round, '@hp', {'hp': dict(hp), 'round': n_round, 'wins': dict(wins)})
        comeback_for = other(winner)
        t = t_end_round + 1.4
    # ---- match result
    champ = left if wins[left] > wins[right] else right
    loser = other(champ)
    vic = 'victory2' if wins[loser] == 0 and 'victory2' in A[champ].anim else 'victory'
    name = getattr(A[champ], 'display', None) or A[champ].character
    if ko_loser is not None and bout.ko_info:
        ki = bout.ko_info
        tc = ki['tc']
        t_end = tc + POST_KO_S
        tv = max(em.free[champ], tc + ki['hs'] + 0.45)             # the winner turns to its pose while the loser still falls
        em.play(champ, tv, vic, {'hold': True}, tot(champ, vic), then=None)
        tt = tv + tot(champ, vic) + 0.05
        if 'taunt' in A[champ].anim and tt + tot(champ, 'taunt') <= t_end - 0.1:
            em.play(champ, tt, 'taunt', {}, tot(champ, 'taunt'))
        banner(max(tv, tc + 1.0), 'winner', over=champ, until=t_end, name=name)
        if 'getup' in A[loser].anim:                              # stays down, then slumps up (a slowed, heavy get-up)
            gu = tot(loser, 'getup') / GETUP_SLOW_K
            tg = max(ki['down'] + 0.6, t_end - 0.1 - gu)
            em.play(loser, tg, 'getup', {'slow': [round(tg, 4), round(tg + gu, 4), GETUP_SLOW_K]}, gu)
            t_end = min(tc + POST_KO_MAX_S, max(t_end, tg + gu + 0.1))
    else:
        t_fin = max(em.free[left], em.free[right], t - 1.4)
        banner(t_fin, 'winner', over=champ, name=name)
        em.play(champ, t_fin, vic, {'hold': True}, tot(champ, vic), then=None)
        t_end = t_fin + max(2.4, tot(champ, vic) + 0.5)
    em.finish()
    em.directive(left, t_end - 0.2, '@record', {'winner': champ, 'loser': loser, 'score': dict(wins), 'chars': {s: A[s].character for s in (left, right)}})
    for w in tl:
        tl[w].sort(key=lambda s: s[0])
    summary = dict(winner=champ, loser=loser, wins=dict(wins), rounds=rounds, mode=mode, p_left=pl, projs=bout.projs, beats=bout.beats, air=bout.n_air,
                   story=story, final_ko=bout.ko_info if ko_loser is not None else None)
    return tl, t_end, summary


def make_friendly(plan, atlases, fx=None, exchanges=4):
    """Spar / clash exchanges (no HP, no finishers) through the same choreography: -> (timeline, t_end, summary).
    The caller (brain.make_timeline) wraps them in bows and the closing fist bump."""
    bout = Bout(plan, atlases, fx, friendly=True)
    left, right = bout.left, bout.right
    rng, em = bout.rng, bout.em
    t = plan['t0']
    for p in bout.pick.values():
        p.new_round()
    for k in range(exchanges):
        boost = bool(bout.boost)
        if boost:
            att = bout.boost.pop(0)                                # its agent just finished a task: the signature super opens
        elif bout.last_att is not None and bout.last_hit and rng.random() < 0.4:
            att = bout.last_att
        else:
            att = (left, right)[k % 2] if k < 2 else (left if rng.random() < 0.5 else right)
        air = k == exchanges - 1 and rng.random() < 0.35 and not boost
        t, ko, ex = bout.exchange(att, t, k, dramatic=False, air=air, boost=boost)
    em.finish()
    t_end = max(em.free.values()) + 0.2
    for w in em.tl:
        em.tl[w].sort(key=lambda s: s[0])
    return em.tl, t_end, dict(projs=bout.projs, beats=bout.beats, air=bout.n_air, pos=dict(bout.pos))


def _fx_hit_s(effect):
    if effect is None or effect.hit_frame is None:
        return 0.0
    return sum(ms for _, ms in effect.frames[:effect.hit_frame]) / 1000.0


def hp_trace(tl):
    """[(t, {slot: hp})] from a timeline (tests, previews): every HP value in time order."""
    out = []
    for w, steps in tl.items():
        for t, name, opts in steps:
            if 'hp' in opts and isinstance(opts['hp'], dict):
                out.append((t, dict(opts['hp'])))
    out.sort(key=lambda s: s[0])
    return out


# ---------------------------------------------------------------- record.json
def record_path() -> Path:
    return cfgmod.data_dir() / 'record.json'


def read_record(path=None) -> dict:
    p = Path(path) if path else record_path()
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def record_for(rec, character) -> tuple:
    """-> (wins, losses) of a character in a record dict."""
    v = (rec or {}).get('characters', {}).get(character) or {}
    try:
        return int(v.get('w', 0)), int(v.get('l', 0))
    except (TypeError, ValueError):
        return 0, 0


def record_result(winner_char, loser_char, path=None, now=None, where='taskbar') -> bool:
    """W/L per character, written atomically (temp file + replace).  Returns False instead of raising on disk trouble."""
    p = Path(path) if path else record_path()
    rec = read_record(p)
    if not isinstance(rec.get('characters'), dict):
        rec['characters'] = {}
    chars = rec['characters']
    for c, key in ((winner_char, 'w'), (loser_char, 'l')):
        e = chars.setdefault(str(c), {'w': 0, 'l': 0})
        e[key] = int(e.get(key, 0)) + 1
    rec['matches'] = int(rec.get('matches', 0) or 0) + 1
    rec['last'] = dict(winner=str(winner_char), loser=str(loser_char), ts=time.time() if now is None else now, where=where)
    return write_json_atomic(p, rec)
