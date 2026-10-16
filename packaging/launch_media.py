"""Launch media: docs/social-preview.png (1280x640 GitHub/X card), docs/demo.gif and docs/demo.mp4.

    python packaging/launch_media.py            # all three
    python packaging/launch_media.py preview    # only the social card
    python packaging/launch_media.py demo       # only the gif + mp4

Built only from what is in the repo: the sprite sheets in assets/ (idle frame 1, nearest-neighbour upscale), the app icon,
and for the loop the offline taskbar render of tools/doc_images.py (real planner + renderer, DEMO numbers) at 20 fps.
The mp4 needs ffmpeg on PATH (skipped otherwise).  Never captures the screen.
"""
from __future__ import annotations
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs'
PROGRAMS = ('claude', 'codex', 'gemini', 'cursor', 'ollama', 'lmstudio', 'generic')
EXTRAS = ('kunoichi', 'knight', 'barbarian', 'monk', 'nomad', 'oni')
BG0, BG1 = (13, 14, 20), (28, 22, 36)
INK, DIM, ACCENT = (246, 246, 250), (176, 180, 196), (240, 161, 132)       # ACCENT = Claude's accent (#F0A184)


def font(size, weight='black'):
    names = {'black': ('seguibl.ttf', 'segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'),
             'bold': ('segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'),
             'regular': ('segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf')}[weight]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            pass
    return ImageFont.load_default()


def idle_frame(char, facing='R'):
    """Idle frame 1 of a character's 64 px sheet, cropped to its pixels, plus the ground line inside the crop.
    facing 'L' is the R frame mirrored (exactly what the app draws for a fighter facing left)."""
    meta = json.loads((ROOT / 'assets' / char / 'anim.json').read_text(encoding='utf-8'))
    cw, ch = meta['cell']
    sheet = Image.open(ROOT / 'assets' / char / meta['sheets']['R']).convert('RGBA')
    row = meta['anims']['idle']['row']
    cell = sheet.crop((0, row * ch, cw, (row + 1) * ch))
    if facing == 'L':
        cell = ImageOps.mirror(cell)
    box = cell.getbbox()
    return cell.crop(box), meta['ground_y'] - box[1]


def up(im, k):
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def shadow(sprite, k=1, alpha=150):
    """A soft dark halo behind the sprite so it reads on any background at thumbnail size."""
    a = sprite.split()[3].point(lambda v: alpha if v else 0)
    s = Image.new('RGBA', sprite.size, (0, 0, 0, 0))
    s.putalpha(a)
    pad = 8 * k
    out = Image.new('RGBA', (sprite.width + 2 * pad, sprite.height + 2 * pad), (0, 0, 0, 0))
    out.paste(s, (pad, pad), s)
    return out.filter(ImageFilter.GaussianBlur(3 * k)), pad


def gradient(w, h):
    im = Image.new('RGB', (w, h), BG0)
    px = im.load()
    for y in range(h):
        for x in range(w):
            t = min(1.0, (0.55 * x / w + 0.45 * y / h))
            px[x, y] = tuple(int(BG0[i] + (BG1[i] - BG0[i]) * t) for i in range(3))
    return im


def social_preview(out=DOCS / 'social-preview.png'):
    W, H = 1280, 640
    im = gradient(W, H).convert('RGBA')

    # faint pixel grid (composited, so it stays faint): says "pixel art" even at thumbnail size
    grid = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(grid)
    for x in range(0, W, 16):
        g.line([(x, 0), (x, H)], fill=(255, 255, 255, 7))
    for y in range(0, H, 16):
        g.line([(0, y), (W, y)], fill=(255, 255, 255, 7))
    im.alpha_composite(grid)
    d = ImageDraw.Draw(im)

    # ---- title block (icon + name + tagline), top-left
    icon = Image.open(ROOT / 'assets' / 'icon' / 'minis-256.png').convert('RGBA').resize((128, 128), Image.NEAREST)
    im.alpha_composite(icon, (60, 78))
    d.text((210, 62), 'Taskbar Fighters', font=font(96, 'black'), fill=INK)
    d.text((214, 180), 'Your AI agents fight in your taskbar.', font=font(40, 'bold'), fill=ACCENT)
    d.text((216, 238), 'Claude Code · Codex · Gemini · Cursor · Ollama · LM Studio · 13 fighters',
           font=font(25, 'bold'), fill=DIM)

    # ---- the taskbar strip along the bottom
    bar_top = 566
    d.rectangle([0, bar_top, W, H], fill=(30, 32, 42, 255))
    d.line([(0, bar_top), (W, bar_top)], fill=(78, 82, 100, 255), width=2)

    # ---- the lineup: 7 program fighters in front (~212 px tall), the 6 extras one step back (~160 px) in the gaps;
    # left half faces right, right half faces left (they square up in the middle)
    front_y, back_y = 628, 560
    n = len(PROGRAMS)
    xs = [96 + i * (1088 / (n - 1)) for i in range(n)]                        # front centres
    back_xs = [(xs[i] + xs[i + 1]) / 2 for i in range(n - 1)]                 # back centres, in the gaps

    def place(char, cx, feet_y, facing, target_h, dim=1.0):
        spr, ground = idle_frame(char, facing)
        k = max(1, round(target_h / spr.height))          # integer scale, whatever the sheet's cell size
        spr = up(spr, k)
        if dim != 1.0:
            rgb = ImageEnhance.Brightness(spr.convert('RGB')).enhance(dim)
            rgb.putalpha(spr.split()[3])
            spr = rgb
        sh, pad = shadow(spr, k=max(1, k // 2))
        x, y = int(cx - spr.width / 2), int(feet_y - ground * k)
        im.alpha_composite(sh, (x - pad, y - pad))
        im.alpha_composite(spr, (x, y))

    for i, c in enumerate(EXTRAS):
        place(c, back_xs[i], back_y, 'R' if back_xs[i] < W / 2 else 'L', 160, dim=0.72)
    for i, c in enumerate(PROGRAMS):
        place(c, xs[i], front_y, 'R' if xs[i] < W / 2 else 'L', 212)

    im.convert('RGB').save(out, optimize=True)
    print(f'wrote {out} {im.size}')


# ------------------------------------------------------------------ demo loop (gif + mp4)
# The same offline strip tools/doc_images.py renders for hero-bout.gif (real planner + renderer, DEMO numbers, 128 px HD
# fighters = the default fighter_size), at 20 fps instead of 5 so the loop is smooth.  Shown: screen x 300..940 (the fight
# zone and the scoreboard) at 2x = 1280 px wide.
FPS, STAGE_X = 20, (300, 940)


def _strip_frames(seconds=34):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'tools'))
    import doc_images
    frames, meta, _cfg = doc_images.taskbar_strip_frames(seconds=seconds, fps=FPS)
    return frames, meta


def _best_window(frames, meta, n):
    """Start index of the n-frame window with the most on-stage motion (frame-to-frame change in the fight zone), preferring
    windows inside a scripted bout so the loop is all fight."""
    import numpy as np
    zone = [np.asarray(f.crop((STAGE_X[0], 0, STAGE_X[1] - 200, f.height)).convert('L'), dtype=np.int16) for f in frames]
    motion = [0] + [int(np.abs(zone[i] - zone[i - 1]).sum()) for i in range(1, len(zone))]
    best, best_i = -1, 0
    for i in range(0, len(frames) - n):
        if not all(m['script'] for m in meta[i:i + n:4]):
            continue
        s = sum(motion[i:i + n])
        if s > best:
            best, best_i = s, i
    return best_i


CROP = None                                       # set by demo(): the clip's own motion box (+ margin), so the fight is framed


def _motion_box(clip, pad=48):
    """Union box of every pixel that changes across the clip (fighters, effects, banners, scoreboard), padded.  A fixed
    window went stale when the fight zone started scaling with fighter_size and cut the fighters in half."""
    from PIL import ImageChops
    base, box = clip[0].convert('RGB'), None
    for f in clip[1:]:
        b = ImageChops.difference(f.convert('RGB'), base).getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    w, h = clip[0].size
    if box is None:
        return (STAGE_X[0], 0, STAGE_X[1], h)
    return (max(0, box[0] - pad), max(0, box[1] - pad // 2), min(w, box[2] + pad // 4), h)


def _compose(strip, W=1280, top=0, bg=(22, 23, 30)):
    box = CROP or (STAGE_X[0], 0, STAGE_X[1], strip.height)
    stage = up(strip.crop(box), 2)
    c = Image.new('RGBA', (W, top + stage.height), bg + (255,))
    c.alpha_composite(stage, ((W - stage.width) // 2, top))
    return c


def demo(gif_out=DOCS / 'demo.gif', mp4_out=DOCS / 'demo.mp4', seconds=8.0):
    frames, meta = _strip_frames()
    n = int(seconds * FPS)
    a = _best_window(frames, meta, n)
    clip = frames[a:a + n]
    global CROP
    CROP = _motion_box(clip)
    print(f'demo: frames {a}..{a + n - 1} of {len(frames)} ({seconds:.0f} s at {FPS} fps)')

    # GIF: the 1280-wide strip; one shared palette, no dither (pixel art), 50 ms frames
    gif = [_compose(f).convert('RGB') for f in clip]
    pal = Image.new('RGB', (gif[0].width, gif[0].height * 3))
    for k, i in enumerate((0, len(gif) // 2, len(gif) - 1)):
        pal.paste(gif[i], (0, k * gif[0].height))
    pal = pal.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    q = [g.quantize(palette=pal, dither=Image.Dither.NONE) for g in gif]
    q[0].save(gif_out, save_all=True, append_images=q[1:], duration=1000 // FPS, loop=0, optimize=True, disposal=1)
    print(f'wrote {gif_out.relative_to(ROOT)} {gif[0].size} x{len(q)} {gif_out.stat().st_size // 1024} KB')

    # MP4 for X: 1280x720 with the title, the same stage + scoreboard, and the repo URL
    ff = shutil.which('ffmpeg')
    if not ff:
        print('demo.mp4: skipped (ffmpeg not on PATH)')
        return
    W, Hh = 1280, 720
    head = Image.new('RGBA', (W, Hh), BG0 + (255,))
    d = ImageDraw.Draw(head)
    icon = Image.open(ROOT / 'assets' / 'icon' / 'minis-256.png').convert('RGBA').resize((80, 80), Image.NEAREST)
    tf, sf, uf = font(64, 'black'), font(30, 'bold'), font(24, 'bold')
    tw = d.textlength('Taskbar Fighters', font=tf)
    x0 = int((W - (80 + 20 + tw)) / 2)
    head.alpha_composite(icon, (x0, 44))
    d.text((x0 + 100, 38), 'Taskbar Fighters', font=tf, fill=INK)
    s = 'Your AI agents fight in your taskbar.'
    d.text(((W - d.textlength(s, font=sf)) / 2, 132), s, font=sf, fill=ACCENT)
    u = 'github.com/mrktchris/taskbar-fighters'
    d.text(((W - d.textlength(u, font=uf)) / 2, 600), u, font=uf, fill=DIM)
    with tempfile.TemporaryDirectory() as td:
        for i, f in enumerate(clip):
            body = _compose(f)
            fr = head.copy()
            y0 = 236
            ImageDraw.Draw(fr).line([(0, y0 - 2), (W, y0 - 2)], fill=(70, 74, 90, 255), width=2)
            ImageDraw.Draw(fr).line([(0, y0 + body.height + 1), (W, y0 + body.height + 1)], fill=(70, 74, 90, 255), width=2)
            fr.alpha_composite(body, (0, y0))
            fr.convert('RGB').save(Path(td) / f'f{i:04d}.png')
        cmd = [ff, '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', str(Path(td) / 'f%04d.png'),
               '-vf', 'fps=30', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', str(mp4_out)]
        subprocess.run(cmd, check=True)
    print(f'wrote {mp4_out.relative_to(ROOT)} {W}x{Hh} {mp4_out.stat().st_size // 1024} KB')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    what = argv[0] if argv else 'all'
    if what in ('all', 'preview'):
        social_preview()
    if what in ('all', 'demo'):
        demo()


if __name__ == '__main__':
    main()
