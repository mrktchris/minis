"""Build every preview into one folder.  python tools/make_previews.py <out_dir> [--quick]
Contact sheets + move reels come from the real sprite sheets (every character on disk); interaction GIFs come from the real
planner (headless, DEMO DATA, fake clock) with characters in both slots; plates are drawn by the real renderer.
V4: 13-hd-ultimates.png (every character's ultimate at HD with its effects, both facings), 14-match.gif (a best-of-3
match on the taskbar with HP, texts and effects) and 15-arena.png (a headless arena frame on a synthetic backdrop).
--quick skips the long reels.  --match-gif <path> renders ONLY the match GIF (V5 choreography) to that path."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'art'))
from PIL import Image
import previews
from minis_core import sim, render
from minis_core.atlas import Library, available
from minis_core.brain import LEFT, RIGHT
from minis_core.telemetry import Snapshot

args = [a for a in sys.argv[1:] if not a.startswith('--')]
quick = '--quick' in sys.argv
match_gif = sys.argv[sys.argv.index('--match-gif') + 1] if '--match-gif' in sys.argv else None
if match_gif:
    args = [a for a in args if a != match_gif]
out = args[0] if args else os.path.join(ROOT, 'qa', 'previews')
os.makedirs(out, exist_ok=True)
P = lambda n: os.path.join(out, n)
ORDER = ['claude', 'codex', 'gemini', 'cursor', 'ollama', 'lmstudio', 'generic']
CHARS = [c for c in ORDER if c in available()] + [c for c in available() if c not in ORDER]
LIB = Library()
PL = {LEFT: 380, RIGHT: 560}
crop = (190, 770)           # 580 logical px wide window around the fighting area


def segment(frames, flags, pad_before=3.0, pad_after=1.5, fps=10):
    idx = [i for i, f in enumerate(flags) if f['script']]
    if not idx:
        return frames
    a, b = max(0, idx[0] - int(pad_before * fps)), min(len(frames) - 1, idx[-1] + int(pad_after * fps))
    return frames[a:b + 1]


def idle():
    return {LEFT: sim.FakeTelemetry(LEFT, [(0, 'idle', 38.0)]), RIGHT: sim.FakeTelemetry(RIGHT, [(0, 'idle', 24.0)], plan=(1.0, 'wk'))}


def render_match_gif(path, seed=7, chars=None, fps=5):
    """A best-of-3 match on the taskbar through the real planner (headless, DEMO DATA): HP, texts, effects, V5 choreography."""
    chars = chars or {LEFT: 'claude', RIGHT: 'codex'}
    brains, fr, ts = sim.run(50, idle(), seed=seed, cfg_over={'bout_min_s': 999, 'bout_max_s': 999, 'clash_min_s': 999, 'clash_max_s': 999,
                                                            'match_min_s': 2, 'match_max_s': 3, 'scoreboard': False}, place=PL, collect=True, crop=crop,
                             scale=3, chars=chars)
    seg = segment(fr, sim.run.flags, pad_before=1.0, pad_after=1.0)
    sim.save_gif(seg[::2], None, path, fps=fps)
    summary = brains[LEFT].last_match or {}
    return len(seg), summary


if match_gif:
    n, summary = render_match_gif(match_gif)
    beats = summary.get('beats') or {}
    import collections
    picks = {s: collections.Counter(b['anim'] for b in v if b['kind'] in ('strike', 'special', 'super', 'ultimate', 'counter')).most_common(4) for s, v in beats.items()}
    print('match gif', match_gif, n, 'frames; winner', summary.get('winner'), 'rounds', len(summary.get('rounds') or []), 'air', summary.get('air'), 'picks', picks)
    sys.exit(0)

# ---- 1. roster overview + contact sheets
print(previews.roster_contact(P('01-roster.png'), CHARS))
print(previews.contact(CHARS, ['locomotion', 'strike'], P('02-moves-locomotion-strikes.png'))[0])
print(previews.contact(CHARS, ['defense', 'reaction'], P('03-moves-defense-reactions.png'))[0])
print(previews.contact(CHARS, ['emote', 'state', 'pair'], P('04-moves-emotes-states-pairs.png'))[0])

# ---- 2. move reels (shared moves, every character side by side)
if not quick:
    core = ['idle', 'idle_flourish', 'walk', 'walk_back', 'jab', 'cross', 'uppercut', 'low_kick', 'roundhouse']
    react = ['block', 'block_hit', 'hit', 'hit_heavy', 'getup', 'dizzy', 'ko', 'victory', 'taunt', 'bow', 'fistbump', 'highfive', 'wave',
             'thumbs_up', 'shrug', 'work', 'type', 'review', 'wait', 'sleep', 'wake', 'powerup', 'rage', 'handoff_give', 'handoff_take', 'console']
    print(previews.reel(CHARS, core, P('05-reel-moves-core.gif'), scale=3, repeat=2))
    print(previews.reel(CHARS, react, P('06-reel-moves-reactions-emotes.gif'), scale=3, repeat=1))


# ---- 3. interaction GIFs from the real planner
pick = lambda i: CHARS[i % len(CHARS)]
working = lambda: {LEFT: sim.FakeTelemetry(LEFT, [(0, 'working', 41.0)]), RIGHT: sim.FakeTelemetry(RIGHT, [(0, 'working', 52.0)])}

for name, tele, over, seed, secs, chars in (
        ('07-sim-spar', idle, {'bout_min_s': 5, 'bout_max_s': 6, 'bout_kinds': ['spar']}, 3, 40, {LEFT: 'claude', RIGHT: 'codex'}),
        ('08-sim-ranged-duel', idle, {'bout_min_s': 5, 'bout_max_s': 6, 'bout_kinds': ['ranged']}, 4, 40, {LEFT: pick(2), RIGHT: pick(3)}),
        ('09-sim-clash-both-working', working, {'bout_min_s': 999, 'bout_max_s': 999, 'clash_min_s': 4, 'clash_max_s': 5}, 5, 30, {LEFT: pick(4), RIGHT: pick(5)})):
    brains, fr, ts = sim.run(secs, tele(), seed=seed, cfg_over=over, place=PL, collect=True, crop=crop, scale=3, chars=chars)
    seg = segment(fr, sim.run.flags)
    sim.save_gif(seg, None, P(name + '.gif'))
    print(name, chars, len(seg), 'frames')

tele = {LEFT: sim.FakeTelemetry(LEFT, [(0, 'idle', 38.0)]),
        RIGHT: sim.FakeTelemetry(RIGHT, [(0, 'idle', 24.0), (2, 'working', 31.0), (20, 'idle', 33.0)], plan=(1.0, 'wk'))}
brains, fr, ts = sim.run(52, tele, seed=5, cfg_over={'bout_min_s': 999, 'bout_max_s': 999, 'clash_min_s': 999, 'clash_max_s': 999}, place=PL,
                         collect=True, crop=crop, scale=3, chars={LEFT: 'claude', RIGHT: pick(6)})
seg = segment(fr, sim.run.flags, pad_before=14.0, pad_after=1.5)
sim.save_gif(seg, None, P('10-sim-handoff-b-finishes.gif'))
print('10-sim-handoff', len(seg))

tele = {LEFT: sim.FakeTelemetry(LEFT, [(0, 'idle', 55.0), (3, 'idle', 93.0)]), RIGHT: sim.FakeTelemetry(RIGHT, [(0, 'idle', 24.0)])}
brains, fr, ts = sim.run(30, tele, seed=5, cfg_over={'bout_min_s': 999, 'bout_max_s': 999}, place=PL, collect=True, crop=crop, scale=3,
                         chars={LEFT: 'codex', RIGHT: 'claude'})
sim.save_gif(fr[:int(26 * 10)], None, P('11-sim-limit-ko-and-console.gif'))
print('11-sim-ko', min(len(fr), 260))

# ---- 4. HUD plates: every state for every character
states = [('idle', 23.0, 1.0, 'wk'), ('working', 48.0, 12.0, 'wk'), ('waiting', 61.0, None, ''), ('done', 33.0, 5.0, 'wk'),
          ('sleeping', None, None, ''), ('working', 93.0, None, ''), ('limit', 94.0, 91.0, 'wk')]
W = len(CHARS) * 140 + 10
img = Image.new('RGBA', (W, 34 * len(states) + 6), (32, 32, 32, 255))
for i, (st, c, p, lab) in enumerate(states):
    for k, ch in enumerate(CHARS):
        img.alpha_composite(render.plate(LIB[ch], Snapshot(ch, st, c, p, lab), 0.0), (6 + k * 140, 4 + i * 34))
img.resize((W * 3, img.height * 3), Image.NEAREST).convert('RGB').save(P('12-hud-plates-every-state.png'))
print('done ->', out)


# ---- 5. V4: HD ultimates with their effects (both facings), a match GIF, an arena frame
from PIL import ImageDraw
from minis_core import fx as fxmod, arena as AR
from minis_core.effects import EffectPlayer
HD = Library(hd=True)
FX = fxmod.default()


def _blit(canvas, im, lx, ty):
    w, h = canvas.size
    if lx < w and ty < h and lx + im.width > 0 and ty + im.height > 0:
        canvas.alpha_composite(im.crop((max(0, -lx), max(0, -ty), min(im.width, w - lx), min(im.height, h - ty))), (max(0, lx), max(0, ty)))


rows = []
for ch in CHARS:
    a = HD[ch]
    ult = a.ultimate()
    n = len(a.anim[ult]['frames'])                        # read from the atlas, never hard-coded
    cell = a.cell[0]
    strip = Image.new('RGBA', (cell * n * 2 + 8, cell + 40), (28, 28, 34, 255))
    for facing, x_off in ((1, 0), (-1, cell * n + 8)):
        p = EffectPlayer(FX, res=a.res, fps=30)
        hand = a.hand(ult)
        sched = a.move_fx(ult)
        for i in range(n):
            t = a.start_ms(ult, i) / 1000.0 + 0.001
            for off, name, until in sched:
                if off <= t and not any(inst.tag == name for inst in p.active):
                    p.spawn(name, off, cell // 2, a.ground_y, facing, tag=name, hand=hand, fade_ms=((until - off) * 1000.0 if until else None))
            p.tick(t)
            canvas = Image.new('RGBA', (cell, cell + 40), (0, 0, 0, 0))
            for im, lx, ty, layer, inst in p.placements(t, layer='back'):
                _blit(canvas, im, lx, ty)
            canvas.alpha_composite(a.frame_image(ult, i, facing), (cell // 2 - a.anchor(facing), 0))
            for im, lx, ty, layer, inst in p.placements(t, layer='front'):
                _blit(canvas, im, lx, ty)
            strip.alpha_composite(canvas, (x_off + i * cell, 0))
    rows.append((ch, ult, strip))
W2 = max(r[2].width for r in rows) + 8
sheet = Image.new('RGBA', (W2, sum(r[2].height + 16 for r in rows) + 8), (20, 20, 24, 255))
d = ImageDraw.Draw(sheet)
y = 4
for ch, ult, strip in rows:
    render.text(d, (6, y), f'{HD[ch].display}: {ult}  (facing right | facing left; effects from fx.json)', (230, 230, 240), 10)
    sheet.alpha_composite(strip, (4, y + 14))
    y += strip.height + 16
sheet.convert('RGB').save(P('13-hd-ultimates.png'))
print('13-hd-ultimates', [r[1] for r in rows])

n_match, _ = render_match_gif(P('14-match.gif'))
print('14-match', n_match)

st = AR.Stage((0, 0, 1920, 1080), [(1, 300, 200, 1200, 800), (2, 1300, 300, 1800, 900)], floor_y=1032)
ar = AR.Arena(st, {'a': HD['claude'], 'b': HD['codex']}, FX, seed=5, backdrop=AR.synthetic_backdrop(st.w, st.h), now=0.0, record=lambda *a, **k: None)
surf = AR.Surface(st.w, st.h)
comp = AR.Compositor(ar, surf)
now, shot = 0.0, None
while ar.phase != 'done' and now < 60:
    now += 1 / 30.0
    ar.tick(now)
    comp.render(now)
    if shot is None and ar.phase == 'fight' and now > 6 and any(i.effect.name not in ('crack_small', 'crack_big') for i in ar.fxp.active):
        shot = surf.canvas.convert('RGB')
(shot or surf.canvas.convert('RGB')).save(P('15-arena.png'))
print('15-arena', ar.state())
