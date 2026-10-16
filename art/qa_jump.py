"""V8 air QA: every airborne row as the engine will play it (the frames carry the pose, anim.json `air` the trajectory).

  python art/qa_jump.py strips <character|all> [--res 1|2] [--out DIR]
      4x (RES 1) / 2x (RES 2) contact strips of every row that has `air`: each frame with its ms, the lift at the frame's
      middle, HIT / smear labels, the black silhouette under it, and the h(t) curve of the row with the frame boundaries.
  python art/qa_jump.py gifs <character|all> [--res 1|2] [--scale 1|2] [--seq name,...] [--out DIR] [--film]
      30 fps GIFs at real timing (hitstop freezes both fighters) with the engine's air_lift applied and the horizontal
      travel (linear across air_window for a jump-in, the rows' dx root motion otherwise), on a dark taskbar mock with the
      JUMP_HEADROOM window above the cell.  Sequences: neutral, jumpin, juggle (uppercut -> air_slash -> spike against
      launched -> air_hit -> spiked), vault, leapshot, throw, pound.  --film also writes every 30 fps tick as a PNG grid.

Renders straight from the rig (no build needed).  Default output: qa/jump/ (GIFs under qa/jump/gif/, which is
git-ignored: regenerate them, never commit them).
"""
from __future__ import annotations
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import rig  # noqa: E402
import roster  # noqa: E402
import build_fighters as BF  # noqa: E402
import moves as MV  # noqa: E402

try:                                              # the engine's own curve (brain re-exports it if it moves to choreo)
    from minis_core.brain import air_lift, air_window  # noqa: E402
except Exception:                                 # noqa: BLE001
    try:
        from minis_core.choreo import air_lift, air_window  # noqa: E402
    except Exception:                             # noqa: BLE001
        air_lift, air_window = None, None
try:
    from minis_core.config import JUMP_HEADROOM  # noqa: E402
except Exception:                                 # noqa: BLE001
    JUMP_HEADROOM = 30

if air_lift is None:
    def air_lift(anim, el_ms):
        return MV.air_at((anim or {}).get('air'), el_ms)

    def air_window(anim):
        keys = (anim or {}).get('air')
        if not keys:
            return None, None
        up = down = None
        for i, k in enumerate(keys):
            if up is None and k[1] <= 0 and i + 1 < len(keys) and keys[i + 1][1] > 0:
                up = float(k[0])
            elif up is not None and k[1] <= 0:
                down = float(k[0])
                break
        if up is None and keys[0][1] > 0:
            up = float(keys[0][0])
        return up, down

OUT = os.path.join(ROOT, 'qa', 'jump')
BG = (32, 32, 32)
DESK = (46, 58, 82)
BAR = (20, 22, 28)
TASKBAR = 48                                      # RES 1 px; the 64 px cell is bottom-aligned on it
FPS = 30
AIR_ROWS = ('jump', 'air_slash', 'spike', 'vault_kick', 'pole_vault', 'leap_shot', 'launched', 'air_hit', 'spiked', 'thrown')


def font(sz):
    for f in ('segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


_cache = {}


def rows(name, res):
    """{move: dict(anim=<anim.json-like entry>, R=[frames], L=[frames])} rendered from the rig at `res`."""
    key = (name, res)
    if key in _cache:
        return _cache[key]
    ch = roster.get(name)
    rig.set_res(res)
    mv = MV.build_moves(ch)
    out = {}
    try:
        idle_pts = BF.idle_scarf(ch) if ch.body.has_tail else None
        for n, m in mv.items():
            if 'air' not in m and n not in ('idle', 'uppercut', 'throw', 'getup', 'hit'):
                continue
            fr = BF.render_move(ch, n, m, None if n == 'idle' else idle_pts)
            anim = {k: v for k, v in m.items() if k != 'frames'}
            anim['frames'] = [dict(i=i, ms=f['ms'], dx=f['pose'].dx * res) for i, f in enumerate(fr)]
            out[n] = dict(anim=anim, R=[f['r'] for f in fr], L=[f['l'] for f in fr], poses=[f['pose'] for f in fr])
    finally:
        rig.set_res(1)
    _cache[key] = out
    return out


def air_names(ch_name):
    m = MV.build_moves(ch_name)
    return [n for n, v in m.items() if 'air' in v]


# ---------------------------------------------------------------- strips
def strip(name, res=1):
    ch = roster.get(name)
    R = rows(name, res)
    sc = 4 if res == 1 else 2
    cell = 64 * res * sc
    lab, gap, graph = 120, 30, 70
    names = air_names(name)
    rh = cell * 2 + gap + graph + 26
    im = Image.new('RGB', (lab + 8 * (cell + 4), len(names) * rh), BG)
    d = ImageDraw.Draw(im)
    f, fs = font(14), font(12)
    for r, n in enumerate(names):
        a = R[n]['anim']
        keys = a['air']
        ms = [x['ms'] for x in a['frames']]
        st = [sum(ms[:i]) for i in range(len(ms))]
        tot = sum(ms)
        y0 = r * rh
        d.text((6, y0 + 8), n, fill=(240, 240, 240), font=f)
        d.text((6, y0 + 28), f'{len(ms)} fr, {tot} ms', fill=(170, 170, 170), font=fs)
        up, down = air_window(a)
        d.text((6, y0 + 46), f'air {up}-{down}', fill=(170, 170, 170), font=fs)
        d.text((6, y0 + 64), f'max h {max(k[1] for k in keys)}', fill=(170, 170, 170), font=fs)
        if 'hit_frame' in a:
            d.text((6, y0 + 82), f'hit {a["hit_frame"]} h={air_lift(a, st[a["hit_frame"]]):.1f}', fill=(255, 200, 90), font=fs)
        for i, fim in enumerate(R[n]['R']):
            x = lab + i * (cell + 4)
            big = fim.resize((cell, cell), Image.NEAREST)
            im.paste(big, (x, y0), big)
            sil = Image.new('RGB', (cell, cell), BG)
            sil.paste((0, 0, 0), (0, 0), big.getchannel('A'))
            im.paste(sil, (x, y0 + cell + gap))
            h = air_lift(a, st[i] + ms[i] / 2.0)
            hit = a.get('hit_frame') == i
            sm = i in (a.get('smear_frames') or [])
            tag = f'#{i} {ms[i]}ms h{h:.1f}' + (' HIT' if hit else '') + (' sm' if sm else '')
            d.text((x + 3, y0 + cell + 6), tag, fill=(255, 200, 90) if hit else (200, 200, 200), font=fs)
        # h(t) curve across the row width, with frame boundaries
        gy, gx0, gw = y0 + cell * 2 + gap + 8, lab, 8 * (cell + 4) - 4
        d.rectangle([gx0, gy, gx0 + gw, gy + graph], outline=(70, 70, 70))
        for s in st[1:]:
            xx = gx0 + gw * s / tot
            d.line([(xx, gy), (xx, gy + graph)], fill=(60, 60, 60))
        pts = [(gx0 + gw * t / tot, gy + graph - graph * air_lift(a, t) / 26.0) for t in range(0, tot + 1, 5)]
        d.line(pts, fill=(120, 200, 255), width=2)
        for k in keys:
            xx = gx0 + gw * k[0] / tot
            yy = gy + graph - graph * k[1] / 26.0
            d.ellipse([xx - 3, yy - 3, xx + 3, yy + 3], fill=(255, 120, 80))
            d.text((xx + 4, yy - 14), f'{k[1]}{k[2] if len(k) > 2 else ""}', fill=(255, 160, 120), font=fs)
    return im


# ---------------------------------------------------------------- playback
class Track:
    """One fighter: a list of (start_ms, row, slide) plays; holds the last frame (and its lift) of a finished row."""

    def __init__(self, name, R, x, facing):
        self.name, self.R, self.x0, self.facing = name, R, x, facing
        self.plays = []

    def play(self, t, row, slide=0.0, hold=None):
        self.plays.append(dict(t=t, row=row, slide=slide, hold=hold))
        return t

    def length(self, row):
        return sum(f['ms'] for f in self.R[row]['anim']['frames'])

    def contact(self, row):
        a = self.R[row]['anim']
        return sum(f['ms'] for f in a['frames'][:a['hit_frame']])


def clock(t, start, freezes):
    """Row clock at world time t for a row started at `start`: hitstop freezes stand the clock still."""
    el = t - start
    for f0, dur in freezes:                       # the overlap of each freeze with [start, t]
        el -= max(0.0, min(t, f0 + dur) - max(start, f0))
    return max(0.0, el)


def _moved(a, pl, el, res):
    ms = [f['ms'] for f in a['frames']]
    tot = sum(ms)
    if pl['slide']:                               # a jump-in: the engine slides linearly across the air window
        up, down = air_window(a)
        if up is not None:
            down_ = down if down is not None else tot
            return pl['slide'] * min(1.0, max(0.0, (el - up) / max(1.0, down_ - up)))
        return pl['slide'] * min(1.0, el / max(1.0, tot))
    moved, acc = 0.0, 0                           # dx root motion, spread linearly within each frame
    for f, m in zip(a['frames'], ms):
        if el >= acc + m:
            moved += f['dx'] / res
        elif el > acc:
            moved += f['dx'] / res * (el - acc) / m
        acc += m
    return moved


def state(tr, t, freezes):
    """-> (row, frame index, lift, x) of a track at world time t (x in design px)."""
    x, cur = tr.x0, None
    for k, pl in enumerate(tr.plays):
        if pl['t'] > t:
            break
        a = tr.R[pl['row']]['anim']
        nxt = tr.plays[k + 1]['t'] if k + 1 < len(tr.plays) and tr.plays[k + 1]['t'] <= t else None
        el = clock(nxt if nxt is not None else t, pl['t'], freezes)
        moved = _moved(a, pl, el, tr.res)
        if nxt is not None:
            x += moved * tr.facing
            continue
        ms = [f['ms'] for f in a['frames']]
        tot = sum(ms)
        acc, idx = 0, len(ms) - 1
        for i, m in enumerate(ms):
            if el < acc + m:
                idx = i
                break
            acc += m
        if el >= tot and pl.get('hold'):
            cur = (pl['hold'], 0, 0.0, x + moved * tr.facing)
        else:
            cur = (pl['row'], idx, air_lift(a, min(el, tot)), x + moved * tr.facing)
    return cur


def render_seq(tracks, freezes, total_ms, res, scale, label=''):
    hr = int(round(JUMP_HEADROOM * res))
    cw = 64 * res
    W_ = 260 * res
    H_ = hr + cw
    bar_y = hr + (64 - TASKBAR) * res
    frames = []
    n = int(total_ms / (1000.0 / FPS)) + 1
    f = font(9 * scale)
    for k in range(n):
        t = k * 1000.0 / FPS
        im = Image.new('RGBA', (W_, H_), DESK + (255,))
        d = ImageDraw.Draw(im)
        d.rectangle([0, bar_y, W_, H_], fill=BAR + (255,))
        d.line([(0, hr), (W_, hr)], fill=(70, 84, 110, 255))      # the cell top (the headroom is above it)
        frozen = any(f0 <= t < f0 + dur for f0, dur in freezes)
        for tr in tracks:
            s = state(tr, t, freezes)
            if s is None:
                continue
            row, i, lift, x = s
            spr = tr.R[row]['R' if tr.facing > 0 else 'L'][i]
            ax = BF.rig.HIP_X * res if tr.facing > 0 else cw - 1 - BF.rig.HIP_X * res
            px = int(round(x * res - ax))
            py = hr - int(round(lift * res))
            im.alpha_composite(spr, (max(0, min(W_ - cw, px)), py))
        im = im.convert('RGB')
        if scale != 1:
            im = im.resize((W_ * scale, H_ * scale), Image.NEAREST)
        ImageDraw.Draw(im).text((4, 2), f'{label}  {int(t)} ms' + ('  HITSTOP' if frozen else ''), fill=(220, 220, 220), font=f)
        frames.append(im)
    return frames


def save_gif(frames, path):
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(round(1000 / FPS)), loop=0, disposal=1)


def film(frames, path, cols=8):
    """Every tick side by side, cropped to the columns where anything moved (so the fighters read at 2x)."""
    from PIL import ImageChops
    box = None
    for fr in frames[1:]:
        bb = ImageChops.difference(fr, frames[0]).getbbox()
        if bb:
            box = bb if box is None else (min(box[0], bb[0]), 0, max(box[2], bb[2]), fr.height)
    if box:
        x0, x1 = max(0, box[0] - 20), min(frames[0].width, box[2] + 20)
        frames = [fr.crop((x0, 0, x1, fr.height)) for fr in frames]
    w, h = frames[0].size
    rows_ = (len(frames) + cols - 1) // cols
    im = Image.new('RGB', (cols * (w + 2), rows_ * (h + 2)), (0, 0, 0))
    for i, fr in enumerate(frames):
        im.paste(fr, ((i % cols) * (w + 2), (i // cols) * (h + 2)))
    im.save(path)


def partner(name):
    names = list(roster.NAMES)
    return names[(names.index(name) + 1) % len(names)]


def sequences(name, res):
    """name -> list of (seq, tracks, freezes, total_ms)."""
    R = rows(name, res)
    out = []

    def tk(nm, x, facing):
        t = Track(nm, rows(nm, res), x, facing)
        t.res = res
        return t
    # neutral jump
    a = tk(name, 80, 1)
    a.play(0, 'idle')
    a.play(300, 'jump', hold='idle')
    out.append(('neutral', [a], [], 300 + a.length('jump') + 500))
    # jump-in toward an idle opponent (the engine slides across the air window)
    a, b = tk(name, 60, 1), tk(partner(name), 190, -1)
    a.play(0, 'idle')
    b.play(0, 'idle')
    a.play(300, 'jump', slide=70, hold='idle')
    out.append(('jumpin', [a, b], [], 300 + a.length('jump') + 500))
    # juggle: uppercut launches, air_slash meets the hanging defender, spike slams it down
    pn = partner(name)
    a, b = tk(name, 100, 1), tk(pn, 136, -1)
    a.play(0, 'idle')
    b.play(0, 'idle')
    freezes = []
    t0 = 200
    a.play(t0, 'uppercut', hold='idle')
    c1 = t0 + a.contact('uppercut')
    hs = R['uppercut']['anim'].get('hitstop_ms', 150)
    freezes.append((c1, hs))
    b.play(c1, 'launched')
    t1 = c1 + hs + (a.length('uppercut') - a.contact('uppercut')) - 120
    a.play(t1, 'air_slash', hold='idle')
    c2 = t1 + a.contact('air_slash')
    freezes.append((c2, R['air_slash']['anim']['hitstop_ms']))
    b.play(c2 + 0.01, 'air_hit')
    t2 = c2 + R['air_slash']['anim']['hitstop_ms'] + a.length('air_slash') - a.contact('air_slash')
    a.play(t2, 'spike', hold='idle')
    c3 = t2 + a.contact('spike')
    freezes.append((c3, R['spike']['anim']['hitstop_ms']))
    b.play(c3 + 0.01, 'spiked')
    tb = c3 + R['spike']['anim']['hitstop_ms'] + b.length('spiked')
    b.play(tb, 'getup', hold='idle')
    out.append(('juggle', [b, a], freezes, tb + b.length('getup') + 300))
    # vault kick / pole vault
    vn = next((n for n in ('vault_kick', 'pole_vault') if n in R), None)
    if vn:
        a, b = tk(name, 60, 1), tk(pn, 170, -1)
        a.play(0, 'idle')
        b.play(0, 'idle')
        a.play(250, vn, hold='idle')
        c = 250 + a.contact(vn)
        freezes = [(c, R[vn]['anim']['hitstop_ms'])]
        b.play(c, 'hit', hold='idle')
        out.append(('vault', [b, a], freezes, 250 + a.length(vn) + freezes[0][1] + 500))
    if 'leap_shot' in R:
        a, b = tk(name, 120, 1), tk(pn, 200, -1)
        a.play(0, 'idle')
        b.play(0, 'idle')
        a.play(250, 'leap_shot', hold='idle')
        c = 250 + a.contact('leap_shot')
        freezes = [(c, R['leap_shot']['anim']['hitstop_ms'])]
        b.play(c, 'hit', hold='idle')
        out.append(('leapshot', [b, a], freezes, 250 + a.length('leap_shot') + freezes[0][1] + 500))
    # throw + thrown on the shared clock
    a, b = tk(name, 100, 1), tk(pn, 126, -1)
    a.play(0, 'idle')
    b.play(0, 'idle')
    a.play(200, 'throw', hold='idle')
    ta = R['throw']['anim']
    g = 200 + sum(f['ms'] for f in ta['frames'][:ta['grab_frame']])
    b.play(g, 'thrown')
    c = 200 + a.contact('throw')
    freezes = [(c, ta['hitstop_ms'])]
    b.play(g + b.length('thrown') + ta['hitstop_ms'], 'getup', hold='idle')
    out.append(('throw', [b, a], freezes, g + b.length('thrown') + ta['hitstop_ms'] + b.length('getup') + 300))
    # the leaping slam signature
    pd = next((n for n in R if R[n]['anim'].get('cat') == 'strike' and 'air' in R[n]['anim']
               and n not in ('air_slash', 'spike', 'vault_kick', 'pole_vault', 'leap_shot')), None)
    if pd:
        a, b = tk(name, 80, 1), tk(pn, 160, -1)
        a.play(0, 'idle')
        b.play(0, 'idle')
        a.play(200, pd, hold='idle')
        c = 200 + a.contact(pd)
        freezes = [(c, R[pd]['anim']['hitstop_ms'])]
        b.play(c, 'hit', hold='idle')
        out.append(('pound', [b, a], freezes, 200 + a.length(pd) + freezes[0][1] + 500))
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('strips', 'gifs'))
    ap.add_argument('who', nargs='?', default='all')
    ap.add_argument('--res', type=int, default=0, help='1 or 2 (default: both)')
    ap.add_argument('--scale', type=int, default=0, help='1 or 2 (default: both)')
    ap.add_argument('--seq', default='')
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--film', action='store_true')
    a = ap.parse_args()
    who = roster.NAMES if a.who == 'all' else a.who.split(',')
    ress = (a.res,) if a.res else (1, 2)
    os.makedirs(a.out, exist_ok=True)
    for w in who:
        for res in ress:
            if a.cmd == 'strips':
                p = os.path.join(a.out, f'{w}-strips-res{res}.png')
                strip(w, res).save(p)
                print(p)
                continue
            gd = os.path.join(a.out, 'gif')
            os.makedirs(gd, exist_ok=True)
            want = set(a.seq.split(',')) if a.seq else None
            for seq, tracks, freezes, tot in sequences(w, res):
                if want and seq not in want:
                    continue
                for sc in ((a.scale,) if a.scale else (1, 2)):
                    fr = render_seq(tracks, freezes, tot, res, sc, f'{w} {seq} RES{res} x{sc}')
                    p = os.path.join(gd, f'{w}-{seq}-res{res}-x{sc}.gif')
                    save_gif(fr, p)
                    if a.film:
                        film(fr, p[:-4] + '-film.png')
                    print(p)
