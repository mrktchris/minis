"""Fight choreography shared by the taskbar timeline (rounds.py, brain.py spar / clash) and the arena (arena.py).

Why: the V4 planner picked every attack with `rng.choice(strikes)`, so a match was the same six strikes in a row and the
defence, locomotion, specials, supers and the ultimate almost never appeared ("same moves over and over").  Everything
here is a pure function of one `random.Random` and the two atlases, so the two fighter processes (and the preview
simulator) derive the identical exchange from the shared seed without talking.

Vocabulary
  Picker        seeded no-repeat move picker: never the same move twice in a row, no move more than MAX_PER_ROUND times
                per round (relaxed only when nothing else is left), weighted by category and situation.
  plan_exchange one exchange as a list of *beats* the caller plays in order:
    {'who': 'att'|'dfn', 'kind': 'move',    'anim': dash|jump|backdash|walk_back, 'dx': +1 toward / -1 away}
    {'who': 'att'|'dfn', 'kind': 'strike'|'special'|'super'|'ultimate'|'counter', 'anim': move, 'dmg': n,
       'outcome': 'hit'|'block'|'crouch_block'|'parry'|'whiff', 'pre': defender anim before contact or None,
       'react': defender anim at contact or None, 'hitstop': ms, 'knock': px (RES 1, along the attacker's facing),
       'down': bool (big hit: knockdown then getup, not a KO)}
    {'who': 'dfn', 'kind': 'emote', 'anim': 'taunt'}                 after a whiffed ultimate
  The caller owns HP: a `hit` whose damage empties the bar becomes a knockdown / KO and the rest of the exchange is dropped.
  Every move name is read from the atlases (`signature`, `anims`), never assumed.
"""
from __future__ import annotations
from collections import Counter

STRIKES = ('jab', 'cross', 'uppercut', 'low_kick', 'roundhouse')
STRIKE_W = {'jab': 1.2, 'cross': 1.0, 'uppercut': 0.9, 'low_kick': 0.9, 'roundhouse': 0.7}
HIGHS = ('uppercut', 'roundhouse', 'spin_kick', 'ground_pound', 'cross')      # a crouch block slips under these
KICKS = ('low_kick', 'roundhouse', 'spin_kick')
COMBOS = (('jab', 'cross', 'uppercut'), ('jab', 'jab', 'roundhouse'), ('low_kick', 'cross'), ('jab', 'cross'),
          ('cross', 'uppercut'), ('jab', 'low_kick', 'roundhouse'), ('low_kick', 'uppercut'))
MAX_PER_ROUND = 2
METER_SUPER = 250                     # hit meter (damage dealt + half the damage taken) that unlocks a super (V6: was 72 -> 3 per match)
SUPER_CHANCE = 0.4
ULT_HP = 30                           # V6: the ultimate is a desperation move: only an attacker below this HP may fire it
ULT_CHANCE = 0.35                     # ... and then only this often per exchange; one per MATCH between both fighters (rounds.Bout)
HITSTOP_FLOOR_MS = 100                # V6: below ~100 ms the freeze falls between two taskbar redraws and is never seen
BLOCK_HITSTOP_K = 0.7
EDGE_MAX = 0.25                       # story: how far HP / round score may tilt hit-vs-defence odds toward the trailing fighter
DMG_PER_POWER = 12
DMG_SUPER = 24
DMG_ULTIMATE = 40
HITSTOP_K = {'strike': 0.5, 'counter': 0.5, 'special': 0.6, 'super': 1.0, 'ultimate': 1.0}   # the art already holds its hit frame
DEFAULT_HITSTOP = {'strike': 150, 'counter': 150, 'special': 150, 'super': 220, 'ultimate': 300}
KNOCK_PX = {'hit': 6, 'hit_heavy': 18, 'knockdown': 42, 'block_hit': 3, 'parry': 0}     # V6: real travel on the strip (was 4 / 10 / 18)
ATTACK_KINDS = ('strike', 'special', 'super', 'ultimate', 'counter')


def strike_pool(atlas):
    pool = [m for m in STRIKES if m in atlas.anim]
    s = atlas.signature()['strike']
    if s and s not in pool:
        pool.append(s)
    return pool


def has_projectile(atlas, move):
    a = atlas.anim.get(move) or {}
    return bool(move) and 'proj_frame' in a and getattr(atlas, 'proj', None) is not None


def damage_of(atlas, move, kind):
    if kind == 'ultimate':
        return DMG_ULTIMATE
    if kind == 'super':
        return DMG_SUPER
    return int(atlas.power(move, 1)) * DMG_PER_POWER


def hitstop_ms(atlas, move, kind):
    """Engine freeze on contact: the move's `hitstop_ms` (or a default per kind) scaled by HITSTOP_K, because the sheets
    already hold the hit frame for most of that time (docs/ANIMATION-NOTES.md)."""
    a = atlas.anim.get(move) or {}
    base = a.get('hitstop_ms') or DEFAULT_HITSTOP.get(kind, 150)
    return max(HITSTOP_FLOOR_MS, int(round(float(base) * HITSTOP_K.get(kind, 0.5))))


def block_hitstop(hs):
    """A blocked hit freezes shorter than a landed one, but still long enough to be drawn."""
    return max(int(HITSTOP_FLOOR_MS * BLOCK_HITSTOP_K), int(hs * BLOCK_HITSTOP_K))


def reach_of(atlas, move, default=20):
    """How far (RES 1 px from the hip) the move's hit frame reaches: anim.json `reach`, else a typical strike."""
    try:
        return float((atlas.anim.get(move) or {}).get('reach') or default) / max(1, getattr(atlas, 'res', 1))
    except (TypeError, ValueError):
        return float(default)


def move_shake(atlas, move):
    """{'frames', 'amp'} the move itself asks for on its hit frame (anim.json `shake`), or None."""
    sh = (atlas.anim.get(move) or {}).get('shake')
    if isinstance(sh, dict) and sh.get('frames'):
        return dict(frames=int(sh['frames']), amp=float(sh.get('amp', 0)))
    return None


def weighted(rng, items):
    """Deterministic weighted choice from [(item, weight)] with the caller's rng."""
    total = sum(max(0.0, w) for _, w in items)
    if total <= 0:
        return items[0][0]
    r = rng.random() * total
    acc = 0.0
    for it, w in items:
        acc += max(0.0, w)
        if r < acc:
            return it
    return items[-1][0]


class Picker:
    """One fighter's move picker.  `counts` is the per-match tally (tests, previews)."""

    def __init__(self, rng, atlas):
        self.rng, self.atlas = rng, atlas
        self.sig = atlas.signature()
        self.last = None
        self.used = Counter()
        self.counts = Counter()

    def new_round(self):
        self.used = Counter()

    def strikes(self):
        pool = strike_pool(self.atlas)
        sig = self.sig['strike']
        return [(m, STRIKE_W.get(m, 0.8 if m == sig else 0.8)) for m in pool]

    def pick(self, cands, prefer=None):
        """cands: [(move, weight)].  Never the last move again, never a third use in a round, while anything else is
        available; `prefer` (a list of names) multiplies those weights."""
        if not cands:
            return None
        if prefer:
            cands = [(m, w * (2.5 if m in prefer else 1.0)) for m, w in cands]
        ok = [(m, w) for m, w in cands if m != self.last and self.used[m] < MAX_PER_ROUND and w > 0]
        if not ok:
            ok = [(m, w) for m, w in cands if m != self.last and w > 0]
        if not ok:
            ok = [(m, w) for m, w in cands if w > 0] or [(m, 1.0) for m, _ in cands]
        m = weighted(self.rng, ok)
        self.note(m)
        return m

    def note(self, move):
        self.last = move
        self.used[move] += 1
        self.counts[move] += 1


# ---------------------------------------------------------------- the exchange grammar
def plan_exchange(rng, att, dfn, sit):
    """-> dict(kind, beats, range_after, air, opener).  `att` / `dfn` are Pickers; `sit` describes the moment:
         range     'close' | 'far'
         meter     the attacker's hit meter (unlocks a super at METER_SUPER)
         ult_ok    the attacker still has its once-per-match ultimate
         dramatic  the attacker is below ULT_HP (dramatic()): when the ultimate is allowed
         ult_sure  the caller already rolled ULT_CHANCE (rounds.make_match rolls once per match): no second roll
         edge      story tilt in [-EDGE_MAX, EDGE_MAX] (edge_for): + lands more often, - gets defended more
         comeback  the round's comeback exchange: a strike that lands, then a full combo
         boost     the attacker's agent just finished a task: its signature super lands (signature strike without one)
         friendly  spar / clash: no supers, no ultimates, no knockdowns, nothing that empties a bar
         air       an air-to-air exchange (jump-in kicks; the arena hovers both)
         k         exchange index within the round
       Every random draw goes through `rng`; same inputs -> same beats on both sides."""
    A, D = att.atlas, dfn.atlas
    far = sit.get('range') == 'far'
    friendly = bool(sit.get('friendly'))
    air = bool(sit.get('air'))
    sig = att.sig
    beats = []
    kind = 'strike'
    fresh = lambda m: bool(m) and m != att.last and att.used[m] < MAX_PER_ROUND      # the no-repeat rule binds specials and supers too
    boost = bool(sit.get('boost'))                                       # V6: the agent just finished a task: its signature super lands
    comeback = bool(sit.get('comeback')) and not boost
    sup_ok = bool(sig['super']) and sig['super'] != A.ultimate()
    if boost and sup_ok:
        kind = 'super'
    elif boost or comeback:
        kind = 'strike'
    elif not friendly:
        if sit.get('ult_ok') and sit.get('dramatic') and A.ultimate() and (sit.get('ult_sure') or rng.random() < ULT_CHANCE):
            kind = 'ultimate'
        elif sup_ok and fresh(sig['super']) and sit.get('meter', 0) >= METER_SUPER and rng.random() < SUPER_CHANCE:
            kind = 'super'
        elif has_projectile(A, sig['special']) and fresh(sig['special']) and rng.random() < (0.4 if far else 0.08):
            kind = 'special'
    elif far and has_projectile(A, sig['special']) and fresh(sig['special']) and rng.random() < 0.3:
        kind = 'special'
    opener = None
    if air:
        opener = 'jump'
    elif far:
        if kind == 'strike':
            opener = weighted(rng, [('dash', 0.4), ('jump', 0.3), ('lunge', 0.3)])   # dash-in jab / jump-in kick / long sliding lunge
        elif kind == 'super' or (kind == 'ultimate' and not sit.get('ult_reaches')):
            opener = 'dash'                                                  # melee finishers close the gap first
    elif kind == 'strike':
        opener = weighted(rng, [(None, 0.6), ('jump', 0.15), ('sweep', 0.25)])
    if opener in ('dash', 'jump'):
        if opener in A.anim:
            beats.append(dict(who='att', kind='move', anim=opener, dx=1))
        else:
            opener = None
    # ---- the first attack
    if kind == 'strike':
        if boost and sig['strike']:
            move = sig['strike']
            att.note(move)
        elif opener == 'sweep':                                         # through the picker: a sweep prefers the low kick, never forces it
            move = att.pick(att.strikes(), prefer=['low_kick'] if 'low_kick' in A.anim else None)
        elif opener == 'lunge':                                         # one long sliding strike from range (rounds.py slides it in)
            move = att.pick(att.strikes(), prefer=['roundhouse', 'low_kick'])  # a sliding kick (cross is already favoured by dash-ins, counters, combos)
        elif comeback:
            move = att.pick(att.strikes(), prefer=['uppercut', 'roundhouse'])
        elif opener == 'jump':
            move = att.pick(att.strikes(), prefer=[k for k in KICKS if k in A.anim])
        elif opener == 'dash':
            move = att.pick(att.strikes(), prefer=['jab', 'cross'])
        else:
            move = att.pick(att.strikes())
    elif kind == 'special':
        move = sig['special']
        att.note(move)
    elif kind == 'super':
        move = sig['super']
        att.note(move)
    else:
        move = A.ultimate()
        att.note(move)
    dmg = damage_of(A, move, kind)
    first = _resolve(rng, A, D, move, kind, dmg, friendly, edge=float(sit.get('edge') or 0.0), force_hit=boost or comeback)
    if opener == 'lunge':
        first['lunge'] = True
    if boost:
        first['boost'] = True
    beats.append(first)
    # ---- what follows the first attack
    if first['outcome'] == 'parry' and not air:
        counter = dfn.pick(dfn.strikes(), prefer=['cross', 'uppercut'])
        cdmg = damage_of(D, counter, 'strike')
        react = 'hit_heavy' if cdmg >= 2 * DMG_PER_POWER else 'hit'
        beats.append(dict(who='dfn', kind='counter', anim=counter, dmg=cdmg, outcome='hit', pre=None, react=react,
                          hitstop=hitstop_ms(D, counter, 'counter'), knock=KNOCK_PX[react], down=False))
    elif first['outcome'] == 'whiff' and kind == 'ultimate' and 'taunt' in D.anim:
        beats.append(dict(who='dfn', kind='emote', anim='taunt'))
    elif first['outcome'] == 'hit' and kind == 'strike' and not air and not boost and not first['down'] and (comeback or rng.random() < 0.55):
        chain = _combo(rng, att, move)
        for i, m in enumerate(chain):
            d = damage_of(A, m, 'strike')
            if comeback or rng.random() < 0.85:
                last = i == len(chain) - 1
                big = d >= 3 * DMG_PER_POWER or (last and len(chain) >= 2 and d >= 2 * DMG_PER_POWER)
                down = (not friendly) and last and big and rng.random() < 0.6
                react = 'knockdown' if down else ('hit_heavy' if d >= 2 * DMG_PER_POWER else 'hit')
                beats.append(dict(who='att', kind='strike', anim=m, dmg=d, outcome='hit', pre=None, react=react,
                                  hitstop=hitstop_ms(A, m, 'strike'), knock=KNOCK_PX[react], down=down))
                if last and m == 'uppercut' and not down and 'jump' in A.anim and rng.random() < 0.5:
                    _juggle(rng, att, beats, friendly)                   # the launcher pops them up: jump after them, kick
            else:
                pre = 'block' if 'block' in D.anim else None
                beats.append(dict(who='att', kind='strike', anim=m, dmg=0, outcome='block', pre=pre, react='block_hit' if 'block_hit' in D.anim else None,
                                  hitstop=block_hitstop(hitstop_ms(A, m, 'strike')), knock=KNOCK_PX['block_hit'], down=False))
                break
    # ---- pressure or a spacing reset
    range_after = 'close'
    if air:
        range_after = 'close'
    elif rng.random() < 0.35:
        loser = 'dfn' if beats[-1].get('outcome') == 'hit' and beats[-1]['who'] == 'att' else 'att'
        anim = weighted(rng, [('backdash', 0.5), ('walk_back', 0.5)])
        who = loser if anim == 'backdash' else 'att'
        actor = A if who == 'att' else D
        if anim in actor.anim:
            beats.append(dict(who=who, kind='move', anim=anim, dx=-1))
            range_after = 'far'
    elif beats[-1].get('down'):
        range_after = 'far'
    return dict(kind=kind, beats=beats, range_after=range_after, air=air, opener=opener, boost=boost, comeback=comeback)


def _juggle(rng, att, beats, friendly):
    """Air juggle after a landed launcher: the attacker jumps in place and meets the airborne defender with a kick."""
    A = att.atlas
    m = att.pick([(k, 1.0) for k in KICKS if k in A.anim] or att.strikes())
    if not m:
        return
    d = damage_of(A, m, 'strike')
    down = not friendly
    react = 'knockdown' if down else 'hit_heavy'
    beats.append(dict(who='att', kind='move', anim='jump', dx=0, juggle=True))
    beats.append(dict(who='att', kind='strike', anim=m, dmg=d, outcome='hit', pre=None, react=react, juggle=True,
                      hitstop=hitstop_ms(A, m, 'strike'), knock=KNOCK_PX[react], down=down))


def edge_for(hp_att, hp_dfn, wins_att=0, wins_dfn=0):
    """Story tilt for one exchange, in [-EDGE_MAX, EDGE_MAX]; positive favours the attacker.  The fighter behind on HP or
    on rounds lands a little more often and the leader gets defended a little more, so matches swing instead of snowballing."""
    e = (float(hp_dfn) - float(hp_att)) / 100.0 * 0.5 + 0.12 * (int(wins_dfn) - int(wins_att))
    return max(-EDGE_MAX, min(EDGE_MAX, e))


def _resolve(rng, A, D, move, kind, dmg, friendly, edge=0.0, force_hit=False):
    """The defender's answer to the first attack, as a strike beat.  `edge` tilts hit vs defence (edge_for); `force_hit`
    (a comeback exchange, a boost super) skips the defender's choice."""
    has = lambda n: n in D.anim
    if force_hit:
        outcome = 'hit'
    elif kind == 'ultimate':
        outcome = weighted(rng, [('hit', 0.8), ('whiff', 0.2 if has('backdash') else 0.0)])
    elif kind == 'super':
        outcome = weighted(rng, [('hit', 0.78), ('whiff', 0.14 if has('backdash') else 0.0), ('parry', 0.08 if has('parry') else 0.0)])
    elif kind == 'special':
        outcome = weighted(rng, [('hit', 0.45), ('block', 0.55 if has('block') else 0.0)])
    elif dmg >= 3 * DMG_PER_POWER:
        outcome = weighted(rng, [('hit', 0.6), ('whiff', 0.14 if has('backdash') else 0.0), ('parry', 0.12 if has('parry') else 0.0),
                                 ('crouch_block', 0.14 if has('crouch_block') and move in HIGHS else 0.0)])
    else:
        outcome = weighted(rng, [('hit', 0.46), ('block', 0.2 if has('block') else 0.0), ('parry', 0.11 if has('parry') else 0.0),
                                 ('whiff', 0.09 if has('backdash') else 0.0), ('crouch_block', 0.14 if has('crouch_block') and move in HIGHS else 0.0)])
    if edge and not force_hit and kind != 'ultimate':
        r = rng.random()                                     # always one extra draw, so both processes stay in step
        if outcome == 'hit' and edge < 0 and r < -edge and (has('block') or has('parry')):
            outcome = 'block' if has('block') else 'parry'
        elif outcome != 'hit' and edge > 0 and r < edge:
            outcome = 'hit'
    pre = react = None
    knock = 0
    down = False
    hs = hitstop_ms(A, move, kind)
    if outcome == 'hit':
        heavy = dmg >= 2 * DMG_PER_POWER
        down = (not friendly) and (kind in ('ultimate', 'super') or dmg >= 3 * DMG_PER_POWER) and rng.random() < (0.9 if kind == 'ultimate' else 0.5)
        react = 'knockdown' if down else ('hit_heavy' if heavy else 'hit')
        knock = KNOCK_PX[react] * (2 if kind == 'ultimate' else 1)
    elif outcome == 'block':
        pre, react, knock, dmg, hs = 'block', ('block_hit' if has('block_hit') else 'block'), KNOCK_PX['block_hit'], 0, block_hitstop(hs)
    elif outcome == 'crouch_block':
        pre, react, knock, dmg, hs = 'crouch_block', ('block_hit' if has('block_hit') else 'crouch_block'), 2, 0, block_hitstop(hs)
    elif outcome == 'parry':
        pre, react, dmg = None, 'parry', 0
    else:                                                    # whiff: the defender is already gone when the hit frame lands
        pre, react, dmg, hs = 'backdash', None, 0, 0
    return dict(who='att', kind=kind, anim=move, dmg=dmg, outcome=outcome, pre=pre, react=react, hitstop=hs, knock=knock, down=down)


def _combo(rng, att, first):
    """Follow-ups after a landed opener: a known chain that starts with it (or a short improvised one), picked without repeats."""
    A = att.atlas
    chains = [c[1:] for c in COMBOS if c[0] == first and all(m in A.anim for m in c)]
    if chains and rng.random() < 0.8:
        chain = list(chains[rng.randrange(len(chains))])
        for m in chain:
            att.note(m)
        return chain
    n = 1 + (rng.random() < 0.4)
    out = []
    for _ in range(n):
        m = att.pick(att.strikes(), prefer=['cross', 'uppercut', 'roundhouse'])
        if m:
            out.append(m)
    return out


def dramatic(wins_att, hp_att, hp_dfn, k, rounds_to_win=2):
    """When an ultimate may come out (V6): only as a desperation move of an attacker below ULT_HP, never in the first two
    exchanges of a round.  (V5 allowed it to anyone up a round, 70% per exchange: 1.7 ultimates per match.)  The caller
    still rolls ULT_CHANCE (plan_exchange) and allows one ultimate per match between both fighters."""
    return k >= 2 and hp_att < ULT_HP


def tally(beats_by_slot):
    """{slot: Counter(move)} of attack picks (strike / special / super / ultimate / counter) from played beats; tests + previews."""
    out = {}
    for slot, beats in beats_by_slot.items():
        c = Counter()
        for b in beats:
            if b.get('kind') in ATTACK_KINDS:
                c[b['anim']] += 1
        out[slot] = c
    return out
