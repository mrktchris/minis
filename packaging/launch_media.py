"""Launch media: docs/social-preview.png (1280x640 GitHub/X card), docs/demo.gif and docs/demo.mp4.

    python packaging/launch_media.py            # all three
    python packaging/launch_media.py preview    # only the social card
    python packaging/launch_media.py demo       # only the gif + mp4

Built only from what is in the repo: the 128 px sprite sheets in assets_hd/ (idle frame 1, nearest-neighbour upscale),
the app icon, and for the loop two offline renders at 2x pixel scale: the taskbar strip of tools/doc_images.py (real
planner + renderer, DEMO numbers) over a SYNTHETIC desktop, then an arena desktop-weapon forge on doc_images' SYNTHETIC
busy desktop.  The mp4 needs ffmpeg on PATH (skipped otherwise).  Never captures the screen.
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


def idle_frame(char, facing='R', art='assets_hd'):
    """Idle frame 1 of a character's sheet (default: the 128 px HD art the app draws at the default fighter_size),
    cropped to its pixels, plus the ground line inside the crop.
    facing 'L' is the R frame mirrored (exactly what the app draws for a fighter facing left)."""
    meta = json.loads((ROOT / art / char / 'anim.json').read_text(encoding='utf-8'))
    cw, ch = meta['cell']
    sheet = Image.open(ROOT / art / char / meta['sheets']['R']).convert('RGBA')
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
# Two acts, both at 2x pixel scale in a 1280x720 frame, both rendered offline (never a screen capture):
#   1. the taskbar: the offline strip of tools/doc_images.py (real planner + renderer, DEMO numbers, 128 px HD fighters =
#      the default fighter_size) with a SYNTHETIC desktop above the taskbar, 20 fps: the exchange that ends round 1, K.O.;
#   2. the arena: a desktop weapon forged out of a window on the SYNTHETIC busy desktop of doc_images (the cut, the lift,
#      the pixel morph, the weapon in the hand), then two hits with it and the shatter; 30 fps resampled to 20.
FPS = 20
W, H = 1280, 720
ACT1_BEFORE_KO, ACT1_AFTER_KO = 66, 20            # frames before / after the first K.O. of the match
XFADE = 4


def _tools():
    for p in (ROOT, ROOT / 'tools'):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import doc_images
    return doc_images


def _desk_backdrop(w, h):
    """The rows above the taskbar: doc_images' synthetic busy desktop at half scale (so at 2x it reads as a normal
    desktop), dimmed so the fighters stay the subject."""
    desk = _tools()._busy_desktop().convert('RGB').resize((960, 540), Image.LANCZOS)
    im = desk.crop((0, 516 - (h - 48), w, 516))
    im = ImageEnhance.Brightness(im).enhance(0.62)
    im = im.quantize(colors=40, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert('RGB')  # flat: leaves
    # the gif palette to the fighters
    out = Image.new('RGBA', (w, h), (0, 0, 0, 255))
    out.paste(im, (0, 0))
    return out


def _act1():
    doc_images = _tools()
    from minis_core import config as cfgmod
    rows = H // 2                                                    # 360 strip rows at 2x = 720
    extra = rows - (128 + 16 + cfgmod.headroom_px(128))
    frames, meta, _cfg = doc_images.taskbar_strip_frames(seconds=40, fps=FPS, backdrop=_desk_backdrop, extra_top=extra)
    ko = next(i for i, m in enumerate(meta) if m['hp'].get('a') is not None and min(m['hp'].values()) <= 0)
    a, b = max(0, ko - ACT1_BEFORE_KO), min(len(frames), ko + ACT1_AFTER_KO)
    print(f'act 1: strip frames {a}..{b - 1} (first K.O. at {ko})')
    x0 = 940 - W // 2                                                # the fight zone and the scoreboard
    return [up(f.crop((x0, 0, 940, rows)), 2).convert('RGB') for f in frames[a:b]]


def _ease(t):
    return t * t * (3 - 2 * t)


def _act2():
    doc_images = _tools()
    from minis_core import forge as FG
    ar, surf, comp, now = doc_images._forge_arena(chars=('claude', 'codex'))
    A, B = ar.f['a'], ar.f['b']
    B.x = A.x + 250.0                                                # close enough that the forged blade reaches
    raw = []
    wide = (160, 360, 1440, 1080)                                    # the window's title bar and both fighters

    def tight():
        x0 = int(A.x - 230)
        return (x0, 1080 - 360, x0 + 640, 1080)

    def tick(k=1):
        nonlocal now
        for _ in range(k):
            now += 1 / 30.0
            ar.tick(now)
            comp.render(now)
            raw.append(doc_images._v7_frame(surf, (0, 0, 1920, 1080)).convert('RGB'))

    job = ar.forge.start('a', 'weapon', now)
    while not job.done and len(raw) < 120:
        tick()
    n_forge = len(raw)
    tick(4)
    hits = 0
    for mv in ('cross', 'cross_cut'):
        mv = mv if mv in A.atlas.anim else 'jab'
        spec = A.atlas.anim[mv]
        contact = sum(f['ms'] for f in spec['frames'][:spec.get('hit_frame', 2)]) / 1000.0
        A.play(mv, now, loop=False, hold='idle')
        t_hit = now + contact
        for _ in range(int(A.atlas.total_ms(mv) / 1000.0 * 30) + 2):
            tick()
            if t_hit is not None and now >= t_hit:
                hits += 1
                B.play('hit_high' if 'hit_high' in B.atlas.anim else 'hit', now, loop=False, hold='idle')
                ar.forge.on_hit_landed('a', now)
                if hits == 2:                                        # the second hit breaks it
                    for _ in range(FG.CRACKS_TO_SHATTER - 2):
                        ar.forge.on_hit_landed('a', now)
                t_hit = None
    tick(10)
    # camera: wide while the piece is cut out of the window, an eased push-in to 2x while it re-forms, 2x after
    z0, z1 = max(0, n_forge - 22), n_forge - 4
    out = []
    for i, fr in enumerate(raw):
        t = 0.0 if i < z0 else 1.0 if i >= z1 else _ease((i - z0) / (z1 - z0))
        tb = tight()
        box = tuple(int(round(wide[j] + (tb[j] - wide[j]) * t)) for j in range(4))
        out.append(fr.crop(box).resize((W, H), Image.NEAREST if t >= 1.0 else Image.LANCZOS))
    print(f'act 2: {len(raw)} arena frames at 30 fps (forged after {n_forge}), {hits} hits')
    return [out[int(round(i * 1.5))] for i in range(int(len(out) / 1.5))]   # 30 -> 20 fps


def _label(im, text, sub=None, xy=(28, 24)):
    d = ImageDraw.Draw(im, 'RGBA')
    f, fs = font(30, 'black'), font(19, 'bold')
    w = max(d.textlength(text, font=f), d.textlength(sub, font=fs) if sub else 0)
    hgt = 50 + (26 if sub else 0)
    d.rounded_rectangle([xy[0], xy[1], xy[0] + w + 32, xy[1] + hgt], 10, fill=(10, 11, 16, 205))
    d.text((xy[0] + 16, xy[1] + 6), text, font=f, fill=INK)
    if sub:
        d.text((xy[0] + 16, xy[1] + 48), sub, font=fs, fill=DIM)


def demo(gif_out=DOCS / 'demo.gif', mp4_out=DOCS / 'demo.mp4'):
    a1, a2 = _act1(), _act2()
    for f in a1:
        _label(f, 'Claude Code vs Codex, on your taskbar', 'they fight from what your agents are really doing')
    for f in a2:
        _label(f, 'Arena mode: weapons forged from your desktop', 'demo render on a synthetic desktop')
    n1 = len(a1)
    clip = a1[:-XFADE] + [Image.blend(a1[n1 - XFADE + k], a2[k], (k + 1) / (XFADE + 1)) for k in range(XFADE)] + a2[XFADE:]
    print(f'demo: {len(clip)} frames, {len(clip) / FPS:.2f} s at {FPS} fps')

    # GIF: 1280x720 like the mp4 (a downscale would blend pixel edges into colours the palette lacks), no dither (pixel art). A palette per act, each built from frames spread
    # over that act: one shared palette for both acts shifted Claude's coat to red.
    small = clip

    def palette(frames):
        pal = Image.new('RGB', (W, H * len(frames)))
        for k, f in enumerate(frames):
            pal.paste(f, (0, k * H))
        return pal.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    n2 = len(small) - n1
    p1 = palette(small[0:n1:max(1, n1 // 8)])
    p2 = palette(small[n1::max(1, n2 // 8)])
    q = [f.quantize(palette=p1 if i < n1 - XFADE // 2 else p2, dither=Image.Dither.NONE) for i, f in enumerate(small)]
    q[0].save(gif_out, save_all=True, append_images=q[1:], duration=1000 // FPS, loop=0, optimize=True, disposal=1)
    print(f'wrote {gif_out.relative_to(ROOT)} {small[0].size} x{len(q)} {gif_out.stat().st_size // 1024} KB')

    # MP4 for X: 1280x720, the same frames plus the repo URL in the corner
    ff = shutil.which('ffmpeg')
    if not ff:
        print('demo.mp4: skipped (ffmpeg not on PATH)')
        return
    with tempfile.TemporaryDirectory() as td:
        for i, f in enumerate(clip):
            fr = f.copy()
            d = ImageDraw.Draw(fr, 'RGBA')
            u, uf = 'github.com/mrktchris/taskbar-fighters', font(20, 'bold')
            tw = d.textlength(u, font=uf)
            d.rounded_rectangle([W - tw - 52, 22, W - 24, 60], 8, fill=(10, 11, 16, 205))
            d.text((W - tw - 38, 28), u, font=uf, fill=INK)
            fr.save(Path(td) / f'f{i:04d}.png')
        cmd = [ff, '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', str(Path(td) / 'f%04d.png'),
               '-vf', 'fps=30', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', str(mp4_out)]
        subprocess.run(cmd, check=True)
    print(f'wrote {mp4_out.relative_to(ROOT)} {W}x{H} {mp4_out.stat().st_size // 1024} KB')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    what = argv[0] if argv else 'all'
    if what in ('all', 'preview'):
        social_preview()
    if what in ('all', 'demo'):
        demo()


if __name__ == '__main__':
    main()
