"""Preview a hand-authored set piece (minis_core/setpieces.py) frame by frame, played through the real Brains.

  python tools/setpiece_preview.py <piece|all> [--a claude] [--b codex] [--out DIR] [--fps 30] [--every 2] [--scale 2]

Writes <out>/setpiece-<piece>-<a>-<b>.png: every Nth frame at the real taskbar size (64 px cells on a dark taskbar mock,
scaled up by --scale for review), labelled with the time and both fighters' animations; and a .gif at real speed.
No windows, no record.json, nothing written outside --out."""
from __future__ import annotations
import argparse, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PIL import Image, ImageDraw  # noqa: E402
from minis_core import config as cfgmod, fx as fxmod, render, rounds, setpieces, sim  # noqa: E402
from minis_core.atlas import Library  # noqa: E402
from minis_core.brain import LEFT, RIGHT  # noqa: E402


def timeline(piece, a, b, lib, fx, seed=1):
    """The set piece as a timeline {slot: [(t, anim, opts)]} for slot a (left, attacker) vs slot b, plus its end time."""
    gap = max(rounds.MIN_APART, rounds.body_front(lib[a]) + rounds.body_front(lib[b]) - rounds.STAND_OVERLAP) + 8
    plan = dict(kind='match', left=LEFT, right=RIGHT, pos={LEFT: 600.0 - gap / 2, RIGHT: 600.0 + gap / 2}, t0=1000.0, seed=seed,
                chars={LEFT: a, RIGHT: b})
    bout = rounds.Bout(plan, {a: lib[a], b: lib[b]}, fx, friendly=False)
    lander = setpieces.PIECES[piece].get('lander', 'att')
    att = LEFT if lander == 'att' else RIGHT
    t_end, ko, ex = bout.exchange(att, 1000.3, 1, piece=piece)
    bout.em.finish()
    for w in bout.em.tl:
        bout.em.tl[w].sort(key=lambda e: e[0])
    return bout.em.tl, t_end + 0.6, plan


def play(piece, a, b, out, fps=30, every=2, scale=2):
    lib, fx = Library(), fxmod.default()
    if not setpieces.eligible(piece, lib[a], lib[b]) and not setpieces.eligible(piece, lib[b], lib[a]):
        print(f'{piece}: not playable for {a} vs {b}')
        return None
    tl, t_end, plan = timeline(piece, a, b, lib, fx)
    cfg = dict(cfgmod.DEFAULTS, bout_min_s=999, bout_max_s=999, clash_min_s=999, clash_max_s=999, match_min_s=999,
               match_max_s=999, scoreboard=False)
    cfg, atl, brains = sim.make(1, cfg, 999.0, chars={LEFT: a, RIGHT: b})
    tele = {w: sim.FakeTelemetry(w, [(0, 'idle', 40.0)]) for w in (LEFT, RIGHT)}
    bus = {}
    for w in (LEFT, RIGHT):
        brains[w].record = lambda *x, **k: None
        brains[w].x = brains[w].home_x = plan['pos'][w]
    sim.step(brains, tele, 999.0, bus)
    sim.step(brains, tele, 999.01, bus)
    for w in (LEFT, RIGHT):
        br = brains[w]
        br.script = dict(kind='match', plan=plan, tl=tl.get(w, []), t_end=t_end, projs=[])
        br.script_i, br.mode, br.bout = -1, 'script', 'preview'
    mid, W = 600, 220
    frames, labels = [], []
    zone0 = int(cfg['zone'][0])
    n = int((t_end - 999.9) * fps)
    for i in range(n):
        now = 999.9 + i / fps
        sim.step(brains, tele, now, bus)
        im = Image.new('RGBA', (int(cfg['zone'][1] - cfg['zone'][0] + 70), 64 + cfgmod.JUMP_HEADROOM), (0, 0, 0, 0))
        for w in (LEFT, RIGHT):
            v = brains[w].view(now)
            fr = render.compose_full(atl[w], atl[w], v, brains[w].snap, now, im.width, cfg, win_x=0, show_plate=False)
            im.alpha_composite(fr, (0, im.height - fr.height))
        x0 = mid - W // 2 - zone0 + 35
        frames.append(sim.mock_taskbar(im, (x0, x0 + W), 1, ''))
        labels.append(f"{now - 1000.0:5.2f}s {brains[LEFT].anim[:12]} / {brains[RIGHT].anim[:12]}")
    os.makedirs(out, exist_ok=True)
    stem = os.path.join(out, f'setpiece-{piece}-{a}-{b}')
    q = [f.quantize(colors=64, method=Image.Quantize.MEDIANCUT) for f in frames]
    q[0].save(stem + '.gif', save_all=True, append_images=q[1:], duration=int(1000 / fps), loop=0)
    sel = list(range(0, len(frames), max(1, every)))
    cols = 5
    cw, ch = W * scale, 64 * scale + 16
    sheet = Image.new('RGB', (cols * cw, ((len(sel) + cols - 1) // cols) * ch + 22), (12, 12, 14))
    d = ImageDraw.Draw(sheet)
    d.text((4, 4), f"{setpieces.PIECES[piece]['title']}: {a} vs {b} - {setpieces.PIECES[piece]['desc']}", fill=(235, 235, 235))
    for k, i in enumerate(sel):
        x, y = (k % cols) * cw, 22 + (k // cols) * ch
        sheet.paste(frames[i].resize((W * scale, 64 * scale), Image.NEAREST), (x, y))
        d.text((x + 3, y + 64 * scale + 2), labels[i], fill=(200, 200, 200))
    sheet.save(stem + '.png')
    print(stem + '.png', len(frames), 'frames')
    return stem


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('piece')
    ap.add_argument('--a', default='claude')
    ap.add_argument('--b', default='codex')
    ap.add_argument('--out', default=os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'Temp', 'minis-setpieces'))
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--every', type=int, default=2)
    ap.add_argument('--scale', type=int, default=2)
    o = ap.parse_args()
    for p in (setpieces.ORDER if o.piece == 'all' else [o.piece]):
        play(p, o.a, o.b, o.out, o.fps, o.every, o.scale)
