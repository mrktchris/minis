"""V4 QA renders from the built assets (no screen capture: only images this script draws).

python art/qa_v4.py effects  [root]  -> qa/v4-effects.png      every effect of one character's sheet, frame by frame
python art/qa_v4.py ults     [root]  -> qa/v4-ultimates.png    all 8 ultimates, HD, both facings, effects composited
python art/qa_v4.py gifs     [root]  -> qa/ult-<name>.gif      one reel per ultimate at 2x over a dark background
python art/qa_v4.py all

Composition follows the fx.json placement contract in art/fx.py: a frame is centred on anchor + offset, where
ground = (anchor_x, ground_y), center = ground - (0, 24*res), hand = ground + anim[move].hand.
"""
from __future__ import annotations
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QA = os.path.join(ROOT, 'qa')
BG = (30, 30, 38)
ORDER = ['claude', 'codex', 'gemini', 'cursor', 'ollama', 'lmstudio', 'generic']


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
        """Anchor point in cell px for a fighter drawn at cell origin (0, 0)."""
        ax = self.meta['anchor']['R' if facing >= 0 else 'L']
        gy = self.meta['ground_y']
        if kind == 'ground':
            return ax, gy
        if kind == 'center':
            return ax, gy - 24 * self.res
        hand = self.meta['anims'][move].get('hand') or [0, 0]
        return ax + facing * hand[0], gy + hand[1]


def active_fx(ch, move, i):
    """Effects listed on the anim entry that are showing on frame i -> [(name, fx frame index)]."""
    out = []
    for spec in ch.meta['anims'][move].get('fx', []):
        if 'at' in spec:
            if i == spec['at']:
                out.append((spec['name'], 0))
            elif i > spec['at']:
                frames, e = ch.fx_frames(spec['name'])
                if e['loop'] or e.get('travel'):
                    continue                              # travelling / looping effects leave the fighter cell
                k = i - spec['at']
                if k < len(frames):
                    out.append((spec['name'], k))
        else:
            if spec['from'] <= i <= spec['to']:
                frames, e = ch.fx_frames(spec['name'])
                k = i - spec['from']
                out.append((spec['name'], k % len(frames) if e['loop'] else min(k, len(frames) - 1)))
    return out


def composite(ch, move, i, facing, pad):
    """The fighter frame with its active effects composited, on a canvas with `pad` px around the cell."""
    w, h = ch.cell
    cv = Image.new('RGBA', (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    fr = ch.frame(move, i, facing)
    layers = {'back': [], 'front': []}
    for name, k in active_fx(ch, move, i):
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


def effects_sheet(root, out, who='generic', scale=2):
    ch = Char(root, who)
    names = [n for n in ch.fx['effects'] if n not in ('round_1', 'round_2', 'round_3', 'fight', 'winner', 'ko')]
    f = font(12)
    rows = []
    for n in names:
        frames, e = ch.fx_frames(n)
        strip_w = sum(im.width * scale + 4 for im, _ in frames)
        strip_h = max(im.height * scale for im, _ in frames)
        rows.append((n, frames, e, strip_w, strip_h))
    label_w = 170
    width = label_w + max(r[3] for r in rows) + 8
    width = min(width, 1900)
    y = 4
    plan = []
    for n, frames, e, sw, sh in rows:
        per_row = max(1, (width - label_w - 8) // (frames[0][0].width * scale + 4)) if frames else 1
        nrows = (len(frames) + per_row - 1) // per_row
        plan.append((n, frames, e, per_row, y))
        y += nrows * (sh + 6) + 8
    img = Image.new('RGB', (width, y + 4), BG)
    d = ImageDraw.Draw(img)
    for n, frames, e, per_row, y0 in plan:
        d.text((6, y0), n, fill=(255, 255, 255), font=f)
        d.text((6, y0 + 15), f"{e['anchor']} {e['offset']} {e['layer']}{' loop' if e['loop'] else ''}", fill=(160, 160, 180), font=font(10))
        if e.get('travel') or e.get('shake') or e.get('hit_frame') is not None:
            d.text((6, y0 + 28), f"hit {e.get('hit_frame')} travel {e.get('travel')} shake {e.get('shake')}"[:34], fill=(160, 160, 180), font=font(9))
        sh = max(im.height * scale for im, _ in frames)
        x, yy = label_w, y0
        for j, (im, ms) in enumerate(frames):
            if j and j % per_row == 0:
                x, yy = label_w, yy + sh + 6
            big = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
            d.rectangle([x - 1, yy - 1, x + big.width, yy + big.height], outline=(55, 55, 66))
            img.paste(big, (x, yy), big)
            x += big.width + 4
    img.save(out)
    return out


def ultimates_sheet(root, out, scale=1):
    chars = [Char(root, n) for n in ORDER]
    pad = 80 * chars[0].res
    f = font(14)
    cells = []
    for ch in chars:
        ult = ch.meta['signature']['ultimate']
        moves = [ult] + ([ch.meta['anims'][ult]['support']] if ch.meta['anims'][ult].get('support') else [])
        for mv in moves:
            for facing in (1, -1):
                n = len(ch.meta['anims'][mv]['frames'])
                cells.append((ch, mv, facing, [composite(ch, mv, i, facing, pad) for i in range(n)]))
    cw = chars[0].cell[0] + 2 * pad
    label_w = 150
    width = label_w + 8 * (cw * scale + 2)
    height = len(cells) * (cw * scale + 4)
    img = Image.new('RGB', (width, height), BG)
    d = ImageDraw.Draw(img)
    for r, (ch, mv, facing, frames) in enumerate(cells):
        y0 = r * (cw * scale + 4)
        d.text((6, y0 + 8), f'{ch.name}', fill=(255, 255, 255), font=f)
        d.text((6, y0 + 28), f"{mv}  {'R' if facing > 0 else 'L'}", fill=(200, 200, 215), font=font(12))
        a = ch.meta['anims'][mv]
        d.text((6, y0 + 46), f"proj {a.get('proj_frame')} hit {a.get('hit_frame')}", fill=(160, 160, 180), font=font(10))
        gy = pad + ch.meta['ground_y']
        d.line([(label_w, y0 + gy * scale), (width, y0 + gy * scale)], fill=(60, 60, 72))
        for i, cv in enumerate(frames):
            x = label_w + i * (cw * scale + 2)
            if scale != 1:
                cv = cv.resize((cv.width * scale, cv.height * scale), Image.NEAREST)
            img.paste(cv, (x, y0), cv)
            d.text((x + 4, y0 + cw * scale - 16), str(i), fill=(140, 140, 160), font=font(10))
    img.save(out)
    return out


def ult_gif(root, who, out, scale=2):
    ch = Char(root, who)
    ult = ch.meta['signature']['ultimate']
    pad = 80 * ch.res
    cw = ch.cell[0] + 2 * pad
    frames, durs = [], []
    seq = [ult] + ([ch.meta['anims'][ult]['support']] if ch.meta['anims'][ult].get('support') else [])
    f = font(18)
    for mv in seq:
        n = len(ch.meta['anims'][mv]['frames'])
        for rep in range(2):
            for i in range(n):
                img = Image.new('RGB', (2 * cw * scale + 16, cw * scale + 40), (22, 22, 28))
                d = ImageDraw.Draw(img)
                d.text((10, 8), f'{who}  {mv}  frame {i}', fill=(255, 255, 255), font=f)
                for k, facing in enumerate((1, -1)):
                    cv = composite(ch, mv, i, facing, pad)
                    cv = cv.resize((cv.width * scale, cv.height * scale), Image.NEAREST)
                    x0 = k * (cw * scale + 16)
                    gy = 40 + (pad + ch.meta['ground_y']) * scale
                    d.line([(x0, gy + 1), (x0 + cw * scale, gy + 1)], fill=(70, 70, 84))
                    img.paste(cv, (x0, 40), cv)
                frames.append(img)
                durs.append(max(40, ch.meta['anims'][mv]['frames'][i]['ms']))
            durs[-1] += 300
    pal = frames[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in frames]
    q[0].save(out, save_all=True, append_images=q[1:], duration=durs, loop=0, optimize=False, disposal=1)
    return out


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    root = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'assets_hd')
    os.makedirs(QA, exist_ok=True)
    if cmd in ('effects', 'all'):
        print(effects_sheet(root, os.path.join(QA, 'v4-effects.png')))
    if cmd in ('ults', 'all'):
        print(ultimates_sheet(root, os.path.join(QA, 'v4-ultimates.png')))
    if cmd in ('gifs', 'all'):
        for n in ORDER:
            ch = Char(root, n)
            print(ult_gif(root, n, os.path.join(QA, f"ult-{ch.meta['signature']['ultimate']}.gif")))
