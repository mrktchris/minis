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

W/L per character go to %LOCALAPPDATA%\\minis\\record.json, written atomically; only character ids, never names of
anything else.
"""
from __future__ import annotations
import json, random, time
from pathlib import Path

from . import config as cfgmod
from .bus import write_json_atomic

HP_MAX = 100
DMG_PER_POWER = 12
DMG_ULTIMATE = 40
ROUND_CAP_S = 25.0
ROUNDS_TO_WIN = 2
MODES = ('decided', 'random')
BANNER_S = {'round': 1.2, 'fight': 0.7, 'ko': 1.5, 'winner': 2.6}
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
    pool = [m for m in STRIKES if m in atlas.anim]
    s = atlas.signature()['strike']
    if s and s not in pool:
        pool.append(s)
    return pool


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


def make_match(plan, atlases, fx=None):
    """-> (timeline {slot: [(t, anim, opts)]}, t_end, summary).  Deterministic in `plan` (+ the atlases / fx on disk)."""
    left, right = plan['left'], plan['right']
    chars = plan.get('chars') or {}
    A = {s: atlases[chars.get(s, s)] for s in (left, right)}
    rng = random.Random(plan['seed'])
    mode = plan.get('mode') if plan.get('mode') in MODES else 'decided'
    pl = p_left(mode, plan.get('scores') or {}, left, right)
    tl = {left: [], right: []}
    tot = lambda w, n: A[w].total_ms(n) / 1000.0
    fx_lead = (lambda name: fx.get(name) and _fx_hit_s(fx.get(name))) if fx is not None else (lambda name: 0.0)
    other = lambda w: right if w == left else left

    def banner(t, kind, over=None):
        dur = BANNER_S.get(kind, BANNER_S['round'])
        tl[left].append((t, '@banner', {'banner': kind, 'until': t + dur, 'over': over}))

    wins = {left: 0, right: 0}
    rounds = []
    t = plan['t0']
    n_round = 0
    ko_loser = None
    while max(wins.values()) < ROUNDS_TO_WIN:
        n_round += 1
        hp = {left: HP_MAX, right: HP_MAX}
        if ko_loser is not None:                                   # the fallen fighter gets up before the next round
            tl[ko_loser].append((t - tot(ko_loser, 'getup') - 0.1, 'getup', {}))
        for w in (left, right):
            tl[w].append((t, '@hp', {'hp': dict(hp), 'round': n_round, 'wins': dict(wins)}))
            tl[w].append((t, 'idle', {}))
        banner(t, f'round{min(3, n_round)}')
        banner(t + BANNER_S['round'], 'fight')
        t_round = t + BANNER_S['round'] + BANNER_S['fight'] + 0.1
        t = t_round
        used_ult = {left: False, right: False}
        k = 0
        ko_loser = None
        while True:
            att = left if rng.random() < pl else right
            dfn = other(att)
            pool = strike_pool(A[att])
            r = rng.random()
            ult, sup = A[att].ultimate(), A[att].signature()['super']
            if ult and not used_ult[att] and k >= 2 and r < 0.18:
                move, kind = ult, 'ultimate'
                used_ult[att] = True
            elif sup and sup != ult and r < 0.30:
                move, kind = sup, 'super'
            else:
                move, kind = rng.choice(pool), 'strike'
            dmg = DMG_ULTIMATE if kind == 'ultimate' else (24 if kind == 'super' else damage_of(A[att], move))
            cont = _contact_s(A[att], move)
            blocked = kind == 'strike' and dmg <= 2 * DMG_PER_POWER and rng.random() < 0.3
            tc = t + cont
            if blocked:
                react, dmg = 'block_hit', 0
            else:
                hp[dfn] = max(0, hp[dfn] - dmg)
                react = 'knockdown' if hp[dfn] <= 0 else ('hit_heavy' if dmg >= 2 * DMG_PER_POWER else 'hit')
            exchange_len = max(tot(att, move), cont + tot(dfn, react)) + 0.35
            if t + exchange_len - t_round > ROUND_CAP_S and k > 0:
                break                                              # time: the round is called on HP
            # attacker (+ the effects its move asks for: charge glows, the beam / burst itself)
            tl[att].append((t, move, {'contact': tc, 'kind': kind, 'damage': dmg}))
            if kind in ('ultimate', 'super'):
                for off, fx_name, until in A[att].move_fx(move):
                    lead = fx_lead(fx_name) if fx_name == move else 0.0
                    tl[att].append((max(t, t + off - lead), '@fx', {'fx': fx_name, 'kind': kind, 'move': move,
                                                                    'until': (t + until) if until else None}))
            tl[att].append((t + tot(att, move), 'idle', {}))
            # defender
            if blocked:
                tl[dfn].append((max(t_round, tc - 0.2), 'block', {}))
                tl[dfn].append((tc, '@fx', {'fx': 'block_spark'}))
            else:
                tl[dfn].append((tc, '@fx', {'fx': 'hit_heavy' if react in ('hit_heavy', 'knockdown') else 'hit_light'}))
            tl[dfn].append((tc, react, {'react_to': move, 'damage': dmg, 'hp': dict(hp)}))
            if react == 'knockdown':
                tl[dfn].append((tc + 0.15, '@fx', {'fx': 'dust', 'anchor': 'ground'}))
                tl[dfn].append((tc + tot(dfn, 'knockdown'), 'ko', {}))
                tl[dfn].append((tc + tot(dfn, 'knockdown'), '@fx', {'fx': 'ko_stars'}))
            else:
                tl[dfn].append((tc + tot(dfn, react), 'idle', {}))
            t = tc + max(tot(att, move) - cont, tot(dfn, react)) + 0.35
            k += 1
            if hp[dfn] <= 0:
                ko_loser = dfn
                break
        # ---- round result
        if ko_loser is not None:
            winner = other(ko_loser)
            banner(tc, 'ko')
            tl[winner].append((tc + 0.6, 'taunt', {}))
            tl[winner].append((tc + 0.6 + tot(winner, 'taunt'), 'idle', {}))
            t_end_round = tc + 0.6 + tot(winner, 'taunt')
        else:
            if hp[left] == hp[right]:
                winner = left if rng.random() < 0.5 else right
            else:
                winner = left if hp[left] > hp[right] else right
            tl[winner].append((t, 'taunt', {}))
            tl[winner].append((t + tot(winner, 'taunt'), 'idle', {}))
            t_end_round = t + tot(winner, 'taunt')
        wins[winner] += 1
        rounds.append(dict(n=n_round, winner=winner, hp=dict(hp), ko=ko_loser is not None, t0=t_round, t1=t_end_round))
        for w in (left, right):
            tl[w].append((t_end_round, '@hp', {'hp': dict(hp), 'round': n_round, 'wins': dict(wins)}))
        t = t_end_round + 2.2
    # ---- match result
    champ = left if wins[left] > wins[right] else right
    loser = other(champ)
    t_fin = t - 2.2 + 1.6
    banner(t_fin, 'winner', over=champ)
    tl[champ].append((t_fin, 'victory2' if wins[loser] == 0 and 'victory2' in A[champ].anim else 'victory', {}))
    if ko_loser is None:                                           # lost on time: still goes down
        tl[loser].append((t_fin, 'knockdown', {}))
        tl[loser].append((t_fin + tot(loser, 'knockdown'), 'ko', {}))
    t_end = t_fin + 3.0
    tl[left].append((t_end - 0.2, '@record', {'winner': champ, 'loser': loser, 'score': dict(wins), 'chars': {s: A[s].character for s in (left, right)}}))
    for w in tl:
        tl[w].sort(key=lambda s: s[0])
    summary = dict(winner=champ, loser=loser, wins=dict(wins), rounds=rounds, mode=mode, p_left=pl)
    return tl, t_end, summary


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
