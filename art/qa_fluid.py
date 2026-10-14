"""Fluidity QA: contact strips and 4x GIF reels from any assets root, so new frames can be judged by eye.

python art/qa_fluid.py strip <char> <move,move,...> <out.png> [--root assets] [--scale 4]
python art/qa_fluid.py reel  <char> <move,move,...> <out.gif> [--root assets] [--scale 4]
python art/qa_fluid.py reels <char> <out_dir> [--root assets]          one GIF per category into out_dir
python art/qa_fluid.py before-after <old_root> <new_root> <char> <move,...> <out.png>

Strips crop every frame to the row's union bbox and print the frame index + ms under it, so timing reads with the
drawing.  Reels play at the real frame durations (a 40 ms smear stays a 40 ms smear) with a short beat per move.
"""
from __future__ import annotations
import argparse, json, os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BG = (40, 40, 48)
GRID = (62, 62, 74)


def load(ch, root='assets'):
    d = os.path.join(ROOT, root, ch) if not os.path.isabs(root) else os.path.join(root, ch)
    meta = json.load(open(os.path.join(d, 'anim.json'), encoding='utf-8'))
    return meta, Image.open(os.path.join(d, 'sheet.png')).convert('RGBA'), Image.open(os.path.join(d, 'sheet_l.png')).convert('RGBA')


def font(sz):
    for n in ('segoeui.ttf', 'arial.ttf'):
        try:
            return ImageFont.truetype(n, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def frames_of(meta, sheet, name):
    c = meta['cell'][0]
    r = meta['anims'][name]['row']
    return [sheet.crop((i * c, r * c, (i + 1) * c, (r + 1) * c)) for i in range(len(meta['anims'][name]['frames']))]


def strip(ch, names, out, root='assets', scale=4, metas=None):
    """One labelled row per move; every frame upscaled NEAREST; smear / hit frames flagged."""
    meta, sr, _ = metas or load(ch, root)
    c = meta['cell'][0]
    f, fs = font(13), font(11)
    rows = []
    for n in names:
        if n not in meta['anims']:
            continue
        a = meta['anims'][n]
        fr = frames_of(meta, sr, n)
        rows.append((n, a, fr))
    cell = c * scale
    label_w = 120
    width = label_w + 8 * (cell + 6)
    img = Image.new('RGB', (width, len(rows) * (cell + 26) + 4), BG)
    d = ImageDraw.Draw(img)
    for r, (n, a, fr) in enumerate(rows):
        y0 = r * (cell + 26)
        d.text((6, y0 + 6), n, fill=(255, 255, 255), font=f)
        d.text((6, y0 + 24), f"{a['cat']} · {len(fr)}f · {sum(x['ms'] for x in a['frames'])} ms", fill=(170, 170, 190), font=fs)
        if 'hitstop_ms' in a:
            d.text((6, y0 + 40), f"hitstop {a['hitstop_ms']} ms", fill=(255, 200, 120), font=fs)
        if a.get('shake'):
            d.text((6, y0 + 56), f"shake {a['shake']['frames']}f/{a['shake']['amp']}px", fill=(255, 200, 120), font=fs)
        for i, im in enumerate(fr):
            x = label_w + i * (cell + 6)
            d.line([(x, y0 + 2), (x, y0 + cell + 2)], fill=GRID)
            d.line([(x, y0 + 2 + meta['ground_y'] * scale + scale), (x + cell, y0 + 2 + meta['ground_y'] * scale + scale)], fill=GRID)
            big = im.resize((cell, cell), Image.NEAREST)
            img.paste(big, (x, y0 + 2), big)
            tag = f"{i}  {a['frames'][i]['ms']} ms"
            col = (255, 255, 255)
            if i in (a.get('smear_frames') or []):
                tag += '  smear'
                col = (120, 220, 255)
            if a.get('hit_frame') == i:
                tag += '  HIT'
                col = (255, 160, 120)
            if a.get('proj_frame') == i and a.get('hit_frame') != i:
                tag += '  release'
                col = (255, 160, 120)
            d.text((x + 2, y0 + cell + 6), tag, fill=col, font=fs)
    img.save(out)
    return out


def reel(ch, names, out, root='assets', scale=4, repeat=2, bg=(32, 32, 32)):
    meta, sr, _ = load(ch, root)
    c = meta['cell'][0]
    cell = c * scale
    f = font(16)
    frames, durs = [], []
    for n in names:
        a = meta['anims'].get(n)
        if not a:
            continue
        fr = frames_of(meta, sr, n)
        reps = repeat if (a['loop'] or len(fr) <= 6) else 1
        for _ in range(reps):
            for i, im in enumerate(fr):
                img = Image.new('RGB', (cell, cell + 30), bg)
                d = ImageDraw.Draw(img)
                d.text((6, 4), f"{n}  [{a['cat']}]", fill=(255, 255, 255), font=f)
                big = im.resize((cell, cell), Image.NEAREST)
                img.paste(big, (0, 30), big)
                frames.append(img)
                durs.append(max(20, a['frames'][i]['ms']))
        if frames:
            durs[-1] += 250
    pal = frames[0].quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in frames]
    q[0].save(out, save_all=True, append_images=q[1:], duration=durs, loop=0, optimize=False, disposal=1)
    return out, len(frames)


CATS = {
    'locomotion': ['idle', 'idle_flourish', 'walk', 'walk_back', 'dash', 'backdash', 'jump', 'crouch', 'turn'],
    'strikes': ['jab', 'cross', 'uppercut', 'low_kick', 'roundhouse'],
    'signature': None,          # strike, special, super from the character's signature
    'defense': ['block', 'block_hit', 'crouch_block', 'parry'],
    'reactions': ['hit', 'hit_heavy', 'knockdown', 'getup', 'dizzy', 'ko'],
    'emotes': ['victory', 'victory2', 'taunt', 'wave', 'thumbs_up', 'facepalm', 'shrug', 'highfive', 'fistbump', 'bow'],
    'states': ['work', 'type', 'review', 'wait', 'sleep', 'wake', 'powerup', 'rage'],
    'ultimate': None,           # the ultimate (+ support)
}


def reels(ch, out_dir, root='assets', scale=4):
    meta, _, _ = load(ch, root)
    sig = meta['signature']
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for cat, names in CATS.items():
        if cat == 'signature':
            names = [sig['strike'], sig['special'], sig['super']]
        elif cat == 'ultimate':
            names = [sig['ultimate']] + ([meta['anims'][sig['ultimate']]['support']] if meta['anims'][sig['ultimate']].get('support') else [])
        out = os.path.join(out_dir, f'{ch}-{cat}.gif')
        made.append(reel(ch, names, out, root, scale))
    return made


def before_after(old_root, new_root, ch, names, out, scale=3):
    """Old build (a snapshot root) above the new build, per move, so the change reads at a glance."""
    mo = load(ch, old_root)
    mn = load(ch, new_root)
    c = mo[0]['cell'][0]
    cell = c * scale
    f, fs = font(13), font(11)
    rows = []
    for n in names:
        rows.append((n, frames_of(mo[0], mo[1], n), mo[0]['anims'][n], 'before'))
        rows.append((n, frames_of(mn[0], mn[1], n), mn[0]['anims'][n], 'after'))
    width = 110 + 8 * (cell + 4)
    img = Image.new('RGB', (width, len(rows) * (cell + 20) + 4), BG)
    d = ImageDraw.Draw(img)
    for r, (n, fr, a, tag) in enumerate(rows):
        y0 = r * (cell + 20)
        d.text((6, y0 + 6), n, fill=(255, 255, 255), font=f)
        d.text((6, y0 + 24), tag, fill=(255, 200, 120) if tag == 'after' else (170, 170, 190), font=fs)
        d.text((6, y0 + 40), f"{len(fr)}f · {sum(x['ms'] for x in a['frames'])} ms", fill=(170, 170, 190), font=fs)
        for i, im in enumerate(fr):
            x = 110 + i * (cell + 4)
            big = im.resize((cell, cell), Image.NEAREST)
            img.paste(big, (x, y0 + 2), big)
            d.text((x + 2, y0 + cell + 4), f"{a['frames'][i]['ms']}", fill=(140, 140, 160), font=fs)
        if tag == 'after':
            d.line([(0, y0 + cell + 19), (width, y0 + cell + 19)], fill=(90, 90, 110))
    img.save(out)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['strip', 'reel', 'reels', 'before-after'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--root', default='assets')
    ap.add_argument('--scale', type=int, default=4)
    a = ap.parse_args()
    if a.cmd == 'strip':
        print(strip(a.args[0], a.args[1].split(','), a.args[2], a.root, a.scale))
    elif a.cmd == 'reel':
        print(reel(a.args[0], a.args[1].split(','), a.args[2], a.root, a.scale))
    elif a.cmd == 'reels':
        for out, n in reels(a.args[0], a.args[1], a.root, a.scale):
            print(out, n, 'frames')
    else:
        print(before_after(a.args[0], a.args[1], a.args[2], a.args[3].split(','), a.args[4]))
