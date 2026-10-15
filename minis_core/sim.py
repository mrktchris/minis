"""Headless simulator: two Brains + scripted fake telemetry on a fake clock.  No windows, no files.
Used by the tests and to render the preview GIFs (the same logic the real windows run)."""
from __future__ import annotations
import random
from PIL import Image, ImageDraw

from . import config as cfgmod, render
from .atlas import Library
from .brain import Brain, LEFT, RIGHT

DEFAULT_CHARS = {LEFT: 'claude', RIGHT: 'codex'}
from .telemetry import Snapshot


class FakeTelemetry:
    """segments: [(t_start, state, ctx_pct)]; emits 'finished' when working ends, 'limit' when ctx crosses the limit."""

    def __init__(self, who, segments, plan=None, limit=90, done_show=8.0, t0=1000.0):
        self.who, self.segments, self.plan, self.limit, self.done_show, self.t0 = who, segments, plan, limit, done_show, t0
        self.prev = None
        self.work_start = None
        self.done_until = 0
        self.limit_seen = False

    def poll(self, now):
        cur = self.segments[0]
        for seg in self.segments:
            if seg[0] <= now - self.t0:
                cur = seg
        state, ctx = cur[1], cur[2]
        snap = Snapshot(self.who, state, ctx, self.plan[0] if self.plan else None, self.plan[1] if self.plan else '')
        if state == 'working' and self.work_start is None:
            self.work_start = now
        if self.prev == 'working' and state == 'idle':
            if self.work_start is not None and now - self.work_start >= 15:
                snap.events.append('finished')
                self.done_until = now + self.done_show
            self.work_start = None
        self.prev = state
        if ctx is not None and ctx >= self.limit:
            if not self.limit_seen:
                snap.events.append('limit')
            self.limit_seen = True
            snap.state = 'limit'
        else:
            self.limit_seen = False
            if state == 'idle' and now < self.done_until:
                snap.state = 'done'
        return snap


_LIB = Library()


def make(seed=1, cfg=None, t0=1000.0, tele=None, chars=None):
    """-> (cfg, {slot: Atlas}, {slot: Brain}).  Slots a/b wear `chars` (default claude / codex)."""
    cfg = dict(cfgmod.DEFAULTS if cfg is None else cfg)
    chars = dict(DEFAULT_CHARS, **(chars or {}))
    atl = {w: _LIB[chars[w]] for w in (LEFT, RIGHT)}
    brains = {w: Brain(w, atl[w], _LIB, cfg, random.Random(seed + (1 if w == RIGHT else 0)), t0, run=f'sim{w}', record=no_record) for w in (LEFT, RIGHT)}
    for b in brains.values():
        b.flashes = True                                         # the simulator never reads this machine's control.json
    return cfg, atl, brains


def no_record(*a, **k):
    """The simulator never writes the real record.json under %LOCALAPPDATA% (a preview match is not a real result)."""
    no_record.calls.append(a)
    return True


no_record.calls = []


def step(brains, tele, now, bus):
    for w, b in brains.items():
        snap = tele[w].poll(now)
        partner = bus.get(RIGHT if w == LEFT else LEFT)
        b.tick(now, snap, partner)
    for w, b in brains.items():
        bus[w] = b.publish()


def run(seconds, tele, seed=1, cfg_over=None, fps=10, t0=1000.0, place=None, collect=False, scale=3, crop=None, label='DEMO DATA', chars=None):
    cfg = dict(cfgmod.DEFAULTS)
    cfg.update(cfg_over or {})
    cfg, atl, brains = make(seed, cfg, t0, chars=chars)
    if place:
        for w, x in place.items():
            brains[w].x = brains[w].home_x = x
            brains[w].home = (x - 40, x + 40)
    bus = {}
    frames, times, flags = [], [], []
    z0, z1 = cfg['zone']
    zone_w = int(z1 - z0 + 70)
    n = int(seconds * fps)
    for i in range(n + 1):
        now = t0 + i / fps
        step(brains, tele, now, bus)
        if collect:
            im = Image.new('RGBA', (zone_w, 64), (0, 0, 0, 0))
            for w in (LEFT, RIGHT):
                v = brains[w].view(now)
                snap = brains[w].snap
                im.alpha_composite(render.compose_full(atl[w], atl[w], v, snap, now, zone_w, cfg, win_x=0))
            frames.append(mock_taskbar(im, crop, scale, label))
            times.append(i / fps)
            flags.append(dict(script=any(brains[w].script is not None for w in (LEFT, RIGHT)), mode={w: brains[w].mode for w in (LEFT, RIGHT)},
                              x={w: brains[w].x for w in (LEFT, RIGHT)}, anim={w: brains[w].anim for w in (LEFT, RIGHT)}))
    run.flags = flags
    return brains, frames, times


def mock_taskbar(sprites, crop, scale, label=''):
    """Sprites over a Windows-11-dark taskbar mock (bottom 48 rows) with a dark window edge above it."""
    w, h = sprites.size
    bg = Image.new('RGBA', (w, h), (24, 24, 30, 255))
    d = ImageDraw.Draw(bg)
    d.rectangle([0, 16, w, h], fill=(32, 32, 32, 255))
    d.line([(0, 16), (w, 16)], fill=(58, 58, 62, 255))
    bg.alpha_composite(sprites)
    if label:
        render.text(d, (4, 2), label, (120, 120, 135), 9, False)
        bg2 = bg
    if crop:
        bg = bg.crop((crop[0], 0, crop[1], h))
    if scale != 1:
        bg = bg.resize((bg.width * scale, bg.height * scale), Image.NEAREST)
    return bg.convert('RGB')


def save_gif(frames, times, path, fps=10, colors=48, hold_last=0.8):
    if not frames:
        return
    pal = frames[len(frames) // 2].quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    dur = [int(1000 / fps)] * len(q)
    dur[-1] = int(hold_last * 1000)
    q[0].save(path, save_all=True, append_images=q[1:], duration=dur, loop=0, optimize=False, disposal=1)

# ---------------------------------------------------------------- variety audit (V7 move-list expansion)
def audit(n=300, seed0=1, chars=None, session_s=600.0):
    """Play `n` seeded matches through rounds.make_match over every ordered roster pair and count what the fighters did.
    Pure timelines (no windows, no record.json).  -> dict with per-match rates and per-character variety:
      distinct      moves a character attacked with over the whole audit
      session12     share of 10-minute sessions (consecutive matches of one character, `session_s` of fight time) with
                    12+ distinct attack moves
      top_share     the most-used attack move's share of that character's attacks (<= 0.20 wanted)
    Rates: ultimates / supers / throws / juggles / pulls / boomerangs / dash-throughs / guard breaks per match, TIME-outs
    per round, 2-0 rate, mean round length."""
    from collections import Counter, defaultdict
    from . import rounds, choreo, fx as fxmod
    from .atlas import available
    lib = _LIB
    names = list(chars or available())
    fxd = fxmod.default()
    pairs = [(a, b) for a in names for b in names if a != b]
    per = defaultdict(Counter)
    sessions = defaultdict(list)                          # char -> [(fight seconds, Counter)] in match order
    rate = Counter()
    rounds_n = time_n = sweep = 0
    round_len = []
    for i in range(n):
        a, b = pairs[i % len(pairs)]
        plan = dict(kind='match', left='a', right='b', pos={'a': 500.0, 'b': 532.0}, t0=1000.0, seed=seed0 + i,
                    chars={'a': a, 'b': b}, mode='decided', scores={'a': 100.0, 'b': 100.0}, id=f'audit:{i}', deadline=1003.0)
        atl = {a: lib[a], b: lib[b]}
        tl, t_end, s = rounds.make_match(plan, atl, fxd)
        for slot, ch in (('a', a), ('b', b)):
            c = Counter()
            for bt in s['beats'][slot]:
                k = bt.get('kind')
                if k in choreo.ATTACK_KINDS:
                    c[bt['anim']] += 1
                    rate[k] += 1
                    if bt.get('outcome') == 'clash':
                        rate['clash'] += 1
                for flag in ('throw', 'juggle', 'pull', 'boomerang', 'through', 'guard_break', 'spike', 'string', 'armor', 'riposte'):
                    if bt.get(flag):
                        rate[flag] += 1
            per[ch].update(c)
            sessions[ch].append((t_end - 1000.0, c))
        for r in s['rounds']:
            rounds_n += 1
            time_n += 0 if r['ko'] else 1
            round_len.append(r['t1'] - r['t0'])
        sweep += 1 if min(s['wins'].values()) == 0 else 0
    out = dict(matches=n, per_match={k: round(v / float(n), 2) for k, v in sorted(rate.items())},
               time_rate=round(time_n / float(max(1, rounds_n)), 3), sweep_rate=round(sweep / float(n), 3),
               mean_round_s=round(sum(round_len) / max(1, len(round_len)), 1), chars={})
    for ch, c in per.items():
        tot = sum(c.values())
        sess, cur, cur_s = [], Counter(), 0.0
        for secs, cc in sessions[ch]:
            cur.update(cc)
            cur_s += secs
            if cur_s >= session_s:
                sess.append(len(cur))
                cur, cur_s = Counter(), 0.0
        top = c.most_common(1)[0] if c else ('-', 0)
        out['chars'][ch] = dict(distinct=len(c), top=top[0], top_share=round(top[1] / float(max(1, tot)), 3),
                                sessions=len(sess), session12=round(sum(1 for x in sess if x >= 12) / float(max(1, len(sess))), 2),
                                session_min=min(sess) if sess else len(c))
    return out


if __name__ == '__main__':
    import json, sys
    print(json.dumps(audit(int(sys.argv[1]) if len(sys.argv) > 1 else 300), indent=1))
