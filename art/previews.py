"""Contact sheets + GIF reels from assets/<character>/anim.json.
python art/previews.py sheet <cat,cat> <out.png> [chars] | reel <names> <out.gif> [chars] | roster <out.png>"""
from __future__ import annotations
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BG = (38, 38, 46)
TASKBAR = (32, 32, 32)


def load(who):
    d = os.path.join(ROOT, 'assets', who)
    meta = json.load(open(os.path.join(d, 'anim.json'), encoding='utf-8'))
    return meta, Image.open(os.path.join(d, 'sheet.png')).convert('RGBA'), Image.open(os.path.join(d, 'sheet_l.png')).convert('RGBA')


def font(sz):
    for n in ('segoeuib.ttf', 'arialbd.ttf'):
        try:
            return ImageFont.truetype(n, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def frame_img(meta, sheet, name, i):
    w, h = meta['cell']
    r = meta['anims'][name]['row']
    return sheet.crop((i * w, r * h, (i + 1) * w, (r + 1) * h))


def contact(whos, cats, out, scale=2, names=None):
    metas = {w: load(w) for w in whos}
    first = metas[whos[0]][0]['anims']
    sel = [n for n, a in first.items() if (names and n in names) or (not names and a['cat'] in cats)]
    sel = [n for n in sel if all(n in metas[w][0]['anims'] for w in whos)] or sel
    cell = 64 * scale
    label_w = 150
    per = 8
    width = label_w + len(whos) * per * cell + (len(whos) - 1) * 12
    img = Image.new('RGB', (width, len(sel) * cell + 4), BG)
    d = ImageDraw.Draw(img)
    f = font(13)
    for r, n in enumerate(sel):
        d.text((6, r * cell + cell // 2 - 14), n, fill=(255, 255, 255), font=f)
        a = first[n]
        d.text((6, r * cell + cell // 2 + 2), f"{a['cat']} · {len(a['frames'])}f", fill=(170, 170, 190), font=font(11))
        for wi, w in enumerate(whos):
            meta, sr, sl = metas[w]
            if n not in meta['anims']:
                continue
            for i in range(len(meta['anims'][n]['frames'])):
                fr = frame_img(meta, sr, n, i).resize((cell, cell), Image.NEAREST)
                x = label_w + wi * (per * cell + 12) + i * cell
                img.paste(fr, (x, r * cell), fr)
        d.line([(0, (r + 1) * cell), (width, (r + 1) * cell)], fill=(55, 55, 66))
    img.save(out)
    return out, sel


def reel(whos, names, out, scale=4, bg=TASKBAR, repeat=2):
    metas = {w: load(w) for w in whos}
    cell = 64 * scale
    f = font(18)
    frames, durs = [], []
    for n in names:
        a0 = metas[whos[0]][0]['anims'].get(n)
        if not a0:
            continue
        nf = max(len(metas[w][0]['anims'][n]['frames']) for w in whos if n in metas[w][0]['anims'])
        total = 0
        for rep in range(repeat if a0['loop'] or len(a0['frames']) <= 6 else 1):
            for i in range(nf):
                img = Image.new('RGB', (len(whos) * cell + (len(whos) - 1) * 8, cell + 34), bg)
                d = ImageDraw.Draw(img)
                d.text((8, 6), f"{n}   [{a0['cat']}]", fill=(255, 255, 255), font=f)
                ms = 100
                for wi, w in enumerate(whos):
                    meta, sr, sl = metas[w]
                    an = meta['anims'].get(n)
                    if not an:
                        continue
                    j = min(i, len(an['frames']) - 1)
                    fr = frame_img(meta, sr, n, j).resize((cell, cell), Image.NEAREST)
                    img.paste(fr, (wi * (cell + 8), 34), fr)
                    ms = max(ms if wi else 0, an['frames'][j]['ms'])
                frames.append(img)
                durs.append(max(40, ms))
        # a short beat between moves
        if frames:
            durs[-1] += 160
    pal = frames[0].quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in frames]
    q[0].save(out, save_all=True, append_images=q[1:], duration=durs, loop=0, optimize=False, disposal=1)
    return out, len(frames)


def roster_contact(out, chars=None, scale=2):
    """Every character: idle + its signature strike, special, super, right-facing and left-facing rows,
    then the projectile strip.  Used to eyeball the whole roster in one image."""
    if chars is None:
        chars = sorted(d for d in os.listdir(os.path.join(ROOT, 'assets'))
                       if os.path.exists(os.path.join(ROOT, 'assets', d, 'anim.json')))
        order = ['claude', 'codex', 'gemini', 'cursor', 'ollama', 'lmstudio', 'generic']
        chars = [c for c in order if c in chars] + [c for c in chars if c not in order]
    cell = 64 * scale
    label_w, gap = 170, 10
    plan = []
    for c in chars:
        meta, sr, sl = load(c)
        sig = meta.get('signature') or {}
        seq = [('idle', 0)] + [(sig[k], i) for k in ('strike', 'special', 'super') if sig.get(k) in meta['anims']
                                for i in range(len(meta['anims'][sig[k]]['frames']))]
        plan.append((c, meta, sr, sl, seq))
    ncell = max(len(p[4]) for p in plan)
    pw = meta['projectile']['w'] * meta['projectile'].get('frames', 3) * scale
    width = label_w + ncell * cell + gap + pw + 8
    img = Image.new('RGB', (width, len(plan) * (2 * cell + gap)), BG)
    d = ImageDraw.Draw(img)
    for r, (c, meta, sr, sl, seq) in enumerate(plan):
        y0 = r * (2 * cell + gap)
        sig = meta.get('signature') or {}
        d.text((6, y0 + 6), f"{meta.get('display', c)}  {meta.get('tag', '')}", fill=(255, 255, 255), font=font(15))
        d.text((6, y0 + 28), f"{meta['colors']} colours + transparent", fill=(170, 170, 190), font=font(11))
        for k, role in enumerate(('strike', 'special', 'super')):
            d.text((6, y0 + 46 + k * 15), f"{role}: {sig.get(role)}", fill=(170, 170, 190), font=font(11))
        acc = meta.get('accent', '#888888').lstrip('#')
        d.rectangle([6, y0 + 96, 40, y0 + 104], fill=tuple(int(acc[i:i + 2], 16) for i in (0, 2, 4)))
        prev = None
        for j, (n, i) in enumerate(seq):
            x = label_w + j * cell
            for sheet, yy in ((sr, y0), (sl, y0 + cell)):
                fr = frame_img(meta, sheet, n, i).resize((cell, cell), Image.NEAREST)
                img.paste(fr, (x, yy), fr)
            if n != prev:
                d.line([(x, y0), (x, y0 + 2 * cell)], fill=(80, 80, 96))
                d.text((x + 3, y0 + 2), n, fill=(200, 200, 215), font=font(10))
                prev = n
        proj = Image.open(os.path.join(ROOT, 'assets', c, meta['projectile']['file'])).convert('RGBA')
        proj = proj.resize((proj.width * scale, proj.height * scale), Image.NEAREST)
        img.paste(proj, (label_w + ncell * cell + gap, y0 + cell // 2), proj)
        d.line([(0, y0 + 2 * cell + gap // 2), (width, y0 + 2 * cell + gap // 2)], fill=(70, 70, 84))
    img.save(out)
    return out


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'sheet':
        cats = sys.argv[2].split(',')
        who = (sys.argv[4] if len(sys.argv) > 4 else 'claude,codex').split(',')
        print(contact(who, cats, sys.argv[3]))
    elif cmd == 'reel':
        who = (sys.argv[4] if len(sys.argv) > 4 else 'claude,codex').split(',')
        print(reel(who, sys.argv[2].split(','), sys.argv[3]))
    elif cmd == 'roster':
        print(roster_contact(sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'qa', 'roster-contact.png')))
