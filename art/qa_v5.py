"""V5.1 QA renders from the built assets (no screen capture: only images this script draws).

python art/qa_v5.py roster  -> qa/v5/roster-redesign.png   all 7: idle + victory + ultimate release, HD, both facings
python art/qa_v5.py beams   -> qa/v5/beams.gif             every beam / wave / burst at 4x over dark, real timings
python art/qa_v5.py idles   -> qa/v5/<char>-idle.gif        each character's signature idle at 4x (64 px build)
python art/qa_v5.py all

Composition follows the fx.json placement contract (art/fx.py): a frame is centred on anchor + offset, where
ground = (anchor_x, ground_y), center = ground - (0, 24*res), hand = ground + anim[move].hand.
"""
from __future__ import annotations
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
QA = os.path.join(ROOT, 'qa', 'v5')
BG = (28, 28, 36)
ORDER = ['claude', 'codex', 'gemini', 'cursor', 'ollama', 'lmstudio', 'generic']
BEAMS = [('claude', 'radiant_beam'), ('gemini', 'crescent_fang'), ('ollama', 'gale_rend'), ('generic', 'star_core'),
         ('lmstudio', 'awakening_aura'), ('codex', 'spiral_orb_burst'), ('cursor', 'grapple_slash'), ('cursor', 'grapple_lines'),
         ('claude', 'slash_wave_proj'), ('codex', 'deploy_proj'), ('gemini', 'star_shot_proj'), ('cursor', 'tab_bolt_proj'),
         ('ollama', 'pull_shot_proj'), ('lmstudio', 'load_wave_proj'), ('generic', 'energy_bolt_proj'),
         ('claude', 'radiant_beam_charge'), ('generic', 'star_core_orb'), ('gemini', 'crescent_fang_impact')]


def font(sz):
    for n in ('segoeuib.ttf', 'arialbd.ttf'):
        try:
            return ImageFont.truetype(n, sz)
        except Exception:
            pass
    return ImageFont.load_default()


class Char:
    def __init__(self, root, name):
        d = os.path.join(root, name)
        self.name = name
        self.meta = json.load(open(os.path.join(d, 'anim.json'), encoding='utf-8'))
        self.res = int(self.meta.get('res', 1))
        self.cell = tuple(self.meta['cell'])
        self.sr = Image.open(os.path.join(d, 'sheet.png')).convert('RGBA')
        self.sl = Image.open(os.path.join(d, 'sheet_l.png')).convert('RGBA')
        self.fx = json.load(open(os.path.join(d, 'fx.json'), encoding='utf-8'))
        self.fxs = Image.open(os.path.join(d, self.fx.get('sheet', 'fx.png'))).convert('RGBA')

    def frame(self, move, i, facing=1):
        w, h = self.cell
        r = self.meta['anims'][move]['row']
        return (self.sr if facing >= 0 else self.sl).crop((i * w, r * h, (i + 1) * w, (r + 1) * h))

    def fx_frames(self, name):
        e = self.fx['effects'][name]
        return [(self.fxs.crop((f['x'], f['y'], f['x'] + f['w'], f['y'] + f['h'])), f['ms']) for f in e['frames']], e

    def anchor_pt(self, move, kind, facing):
        ax = self.meta['anchor']['R' if facing >= 0 else 'L']
        gy = self.meta['ground_y']
        if kind == 'ground':
            return ax, gy
        if kind == 'center':
            return ax, gy - 24 * self.res
        hand = self.meta['anims'][move].get('hand') or [0, 0]
        return ax + facing * hand[0], gy + hand[1]


def composite(ch, move, i, facing, pad, fx_at=None):
    """The fighter frame with the named effects composited (fx_at = [(name, frame index)]), `pad` px round the cell."""
    w, h = ch.cell
    cv = Image.new('RGBA', (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    fr = ch.frame(move, i, facing)
    layers = {'back': [], 'front': []}
    for name, k in (fx_at or []):
        frames, e = ch.fx_frames(name)
        im = frames[k][0]
        if facing < 0:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        ax, ay = ch.anchor_pt(move, e['anchor'], facing)
        ox, oy = e['offset']
        px, py = ax + facing * ox, ay + oy
        layers[e.get('layer', 'front')].append((im, pad + px - im.width // 2, pad + py - im.height // 2))
    for im, x, y in layers['back']:
        cv.alpha_composite(im, (x, y))
    cv.alpha_composite(fr, (pad, pad))
    for im, x, y in layers['front']:
        cv.alpha_composite(im, (x, y))
    return cv


def roster_sheet(root, out, scale=2):
    """Per character: idle frames 0 / 4 / 5, victory frames 2 and 6, and the ultimate's release frame with its effect,
    right-facing then left-facing.  HD, 2x.  Only the ultimate cells carry room for the effect (cropped to the side
    the effect goes), so the fighters themselves stay big."""
    chars = [Char(root, n) for n in ORDER]
    res = chars[0].res
    pad_s, pad_u = 6 * res, 72 * res
    f, fs = font(16), font(12)
    cell = chars[0].cell[0]
    w_s = cell + 2 * pad_s
    w_u = cell + pad_u + 40 * res
    label_w = 150
    width = label_w + (10 * (w_s * scale + 2) + 2 * (w_u * scale + 2))
    row_h = (cell + 2 * pad_u) * scale + 4
    img = Image.new('RGB', (width, len(chars) * row_h), BG)
    d = ImageDraw.Draw(img)
    for r, ch in enumerate(chars):
        y0 = r * row_h
        ult = ch.meta['signature']['ultimate']
        a = ch.meta['anims'][ult]
        rel = a['proj_frame']
        main = next((s_['name'] for s_ in a['fx'] if s_.get('at') == rel), ult)
        cells = []
        for facing in (1, -1):
            cells += [('idle', 0, facing, None), ('idle', 4, facing, None), ('idle', 5, facing, None),
                      ('victory', 2, facing, None), ('victory', 6, facing, None), (ult, rel, facing, [(main, 0)])]
        d.text((6, y0 + 8), ch.meta['display'], fill=(255, 255, 255), font=f)
        d.text((6, y0 + 30), f"{ch.meta['tag']}  {ch.meta['colors']} col", fill=(200, 200, 215), font=fs)
        d.text((6, y0 + 46), f"idle 0/4/5 · victory 2/6 · {ult}", fill=(160, 160, 180), font=fs)
        d.text((6, y0 + 62), "R then L", fill=(160, 160, 180), font=fs)
        gy = pad_u + ch.meta['ground_y']
        d.line([(label_w, y0 + gy * scale), (width, y0 + gy * scale)], fill=(56, 56, 68))
        x = label_w
        for mv, k, facing, fxa in cells:
            if fxa:
                cv = composite(ch, mv, k, facing, pad_u, fxa)
                if facing > 0:
                    cv = cv.crop((pad_u - 40 * res, 0, cv.width, cv.height))
                else:
                    cv = cv.crop((0, 0, pad_u + cell + 40 * res, cv.height))
                w_ = w_u
            else:
                cv = composite(ch, mv, k, facing, pad_s, None)
                top = Image.new('RGBA', (cv.width, cv.height + 2 * (pad_u - pad_s)), (0, 0, 0, 0))
                top.alpha_composite(cv, (0, pad_u - pad_s))
                cv = top
                w_ = w_s
            cv = cv.resize((cv.width * scale, cv.height * scale), Image.NEAREST)
            img.paste(cv, (x, y0), cv)
            d.text((x + 4, y0 + row_h - 20), f"{mv} {k}{' L' if facing < 0 else ''}", fill=(140, 140, 160), font=fs)
            x += w_ * scale + 2
    img.save(out)
    return out


def beams_gif(root, out, scale=4):
    """Every beam / wave / burst / projectile of the HD build at `scale` over dark, at its real frame timings."""
    chars = {n: Char(root, n) for n in ORDER}
    f = font(18)
    W = H = 0
    seqs = []
    for who, eff in BEAMS:
        frames, e = chars[who].fx_frames(eff)
        seqs.append((who, eff, frames, e))
        W = max(W, max(im.width for im, _ in frames) * scale)
        H = max(H, max(im.height for im, _ in frames) * scale)
    W, H = W + 20, H + 50
    out_frames, durs = [], []
    for who, eff, frames, e in seqs:
        reps = 3 if e['loop'] else 2
        for rep in range(reps):
            for i, (im, ms) in enumerate(frames):
                img = Image.new('RGB', (W, H), (18, 18, 24))
                d = ImageDraw.Draw(img)
                tag = f"{who}  {eff}  frame {i}/{len(frames) - 1}  {ms} ms"
                if e.get('flash') and i == 0:
                    tag += '  FLASH'
                if e.get('hit_frame') == i:
                    tag += '  HIT'
                d.text((10, 8), tag, fill=(255, 255, 255), font=f)
                big = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
                x = (W - big.width) // 2 if e['anchor'] != 'hand' or eff.endswith('_proj') else 10
                y = 40 + (H - 50 - big.height) // 2
                img.paste(big, (x, y), big)
                out_frames.append(img)
                durs.append(max(40, ms))
            if rep == reps - 1:
                durs[-1] += 400
    pal = out_frames[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in out_frames]
    q[0].save(out, save_all=True, append_images=q[1:], duration=durs, loop=0, optimize=False, disposal=1)
    return out, len(out_frames)


def idle_gif(root, who, out, scale=4, loops=3):
    ch = Char(root, who)
    a = ch.meta['anims']['idle']
    cw = ch.cell[0]
    f = font(14)
    frames, durs = [], []
    for _ in range(loops):
        for i in range(len(a['frames'])):
            img = Image.new('RGB', (cw * scale + 8, cw * scale + 30), (24, 24, 30))
            d = ImageDraw.Draw(img)
            d.text((6, 4), f"{who}  idle  {a['desc'][:40]}", fill=(255, 255, 255), font=f)
            fr = ch.frame('idle', i).resize((cw * scale, cw * scale), Image.NEAREST)
            d.line([(4, 30 + (ch.meta['ground_y'] + 1) * scale), (4 + cw * scale, 30 + (ch.meta['ground_y'] + 1) * scale)], fill=(60, 60, 72))
            img.paste(fr, (4, 30), fr)
            frames.append(img)
            durs.append(max(40, a['frames'][i]['ms']))
    pal = frames[0].quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in frames]
    q[0].save(out, save_all=True, append_images=q[1:], duration=durs, loop=0, optimize=False, disposal=1)
    return out


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    os.makedirs(QA, exist_ok=True)
    hd = os.path.join(ROOT, 'assets_hd')
    lo = os.path.join(ROOT, 'assets')
    if cmd in ('roster', 'all'):
        print(roster_sheet(hd, os.path.join(QA, 'roster-redesign.png')))
    if cmd in ('beams', 'all'):
        print(beams_gif(hd, os.path.join(QA, 'beams.gif')))
    if cmd in ('idles', 'all'):
        for n in ORDER:
            print(idle_gif(lo, n, os.path.join(QA, f'{n}-idle.gif')))
