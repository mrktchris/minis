"""V6 art QA: contact sheets, silhouette test, roster lineup.  Renders straight from the rig (no build needed).

  python art/qa_v6.py sheet <character|all> [--res 1|2] [--scale N] [--out DIR] [--moves idle,walk,...]
  python art/qa_v6.py silhouettes [--out DIR]          every idle as flat black on #202020 at 1x and 4x, side by side
  python art/qa_v6.py lineup [--out DIR]               all idles at 4x with names; plus a 1x strip on a dark taskbar
                                                       (the 64 px cell bottom-aligned: the top 16 px sit over the desktop)
"""
from __future__ import annotations
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import rig  # noqa: E402
import roster  # noqa: E402
import build_fighters as BF  # noqa: E402
from moves import build_moves  # noqa: E402

DEFAULT_OUT = os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'Temp', 'minis-v6-art')
SHEET_MOVES = ('idle', 'walk', 'jab', 'cross', 'roundhouse', '@strike', '@special', '@super', 'hit', 'knockdown', '@ultimate')
BG = (32, 32, 32)


def font(sz):
    for f in ('segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def resolve(ch, names):
    out = []
    for n in names:
        if n.startswith('@'):
            n = ch.signature[n[1:]]
        out.append(n)
    return out


def frames_of(ch, name, res):
    rig.set_res(res)
    mv = build_moves(ch)[name]
    fr = BF.render_move(ch, name, mv, None)
    rig.set_res(1)
    return [(f['r'], f['ms'], i == mv.get('hit_frame'), i in (mv.get('smear_frames') or [])) for i, f in enumerate(fr)]


def contact_sheet(name, res=1, scale=4, moves=SHEET_MOVES, bg=BG):
    ch = roster.get(name)
    names = resolve(ch, moves)
    cell = 64 * res * scale
    lab = 110
    rows = [frames_of(ch, n, res) for n in names]
    W_ = lab + 8 * cell
    H_ = len(rows) * (cell + 14)
    im = Image.new('RGB', (W_, H_), bg)
    d = ImageDraw.Draw(im)
    f = font(13)
    for r, (n, fr) in enumerate(zip(names, rows)):
        y = r * (cell + 14)
        d.text((6, y + cell // 2 - 8), n, fill=(230, 230, 230), font=f)
        for i, (fim, ms, hit, smear) in enumerate(fr):
            x = lab + i * cell
            big = fim.resize((cell, cell), Image.NEAREST)
            im.paste(big, (x, y), big)
            tag = f'{ms}' + (' HIT' if hit else '') + (' sm' if smear else '')
            d.text((x + 3, y + cell + 1), tag, fill=(255, 200, 90) if hit else (150, 150, 150), font=font(10))
    return im


def silhouettes(out):
    rig.set_res(1)
    ims = []
    for n in roster.NAMES:
        fr = frames_of(roster.get(n), 'idle', 1)[0][0]
        a = fr.getchannel('A')
        s = Image.new('RGB', (64, 64), BG)
        s.paste((0, 0, 0), (0, 0), a)
        ims.append(s)
    strip = Image.new('RGB', (64 * len(ims) + 4 * (len(ims) + 1), 72), BG)
    for i, s in enumerate(ims):
        strip.paste(s, (4 + i * 68, 4))
    strip.save(os.path.join(out, 'silhouettes-1x.png'))
    strip.resize((strip.width * 4, strip.height * 4), Image.NEAREST).save(os.path.join(out, 'silhouettes-4x.png'))


def lineup(out, scale=4):
    rig.set_res(1)
    n = len(roster.NAMES)
    cell = 64 * scale
    im = Image.new('RGB', (n * cell, cell + 40), BG)
    d = ImageDraw.Draw(im)
    f = font(22)
    strip = Image.new('RGB', (n * 70 + 10, 64), (58, 76, 104))       # desktop above, the 48 px taskbar below (as the engine places it)
    ImageDraw.Draw(strip).rectangle([0, 16, strip.width - 1, 63], fill=(20, 22, 28))
    for i, nm in enumerate(roster.NAMES):
        ch = roster.get(nm)
        fr = frames_of(ch, 'idle', 1)[0][0]
        big = fr.resize((cell, cell), Image.NEAREST)
        im.paste(big, (i * cell, 0), big)
        tw = d.textlength(ch.display, font=f)
        d.text((i * cell + (cell - tw) / 2, cell + 6), ch.display, fill=(235, 235, 235), font=f)
        strip.paste(fr, (8 + i * 70, 0), fr)
    return im, strip


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('who', nargs='?', default='all')
    ap.add_argument('--res', type=int, default=1)
    ap.add_argument('--scale', type=int, default=0)
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--moves', default='')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.cmd == 'sheet':
        who = roster.NAMES if a.who == 'all' else a.who.split(',')
        mv = tuple(a.moves.split(',')) if a.moves else SHEET_MOVES
        for w in who:
            sc = a.scale or (4 if a.res == 1 else 2)
            p = os.path.join(a.out, f'{w}-res{a.res}-x{sc}.png')
            contact_sheet(w, a.res, sc, mv).save(p)
            print(p)
    elif a.cmd == 'silhouettes':
        silhouettes(a.out)
    elif a.cmd == 'lineup':
        im, strip = lineup(a.out)
        im.save(os.path.join(a.out, 'v6-roster.png'))
        strip.save(os.path.join(a.out, 'v6-roster-taskbar.png'))
        print(os.path.join(a.out, 'v6-roster.png'))
