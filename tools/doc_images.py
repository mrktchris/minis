"""Render every annotated README image (Taskbar Fighters) into docs/img/ - offline, from the real renderer, planner and arena.

    python tools/doc_images.py [--only roster,moves,...] [--out docs/img]

Nothing here reads the screen, a window, a transcript or this machine's minis data: the data folder is redirected to a
temp dir, the plates show DEMO numbers, the arena runs on a RAM Surface over a synthetic desktop drawn here.  The one
live image (the taskbar capture) is made by tools/taskbar_capture.py and annotated with `--annotate-live <dir>`.

Sections: hero (offline twin of the live strip), roster, moves, impact, select, scoreboard, plates, arena, detection,
before-after.  Annotations use one style: a dark card (readable on GitHub light and dark), white titles, coloured
callouts with a dot on the thing they name.
"""
from __future__ import annotations
import argparse, io, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'art'))
_TMP = Path(tempfile.mkdtemp(prefix='minis-docimg-'))
from minis_core import config as cfgmod  # noqa: E402
cfgmod.data_dir = lambda: _TMP           # never read or write the real %LOCALAPPDATA%\minis
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

OUT = ROOT / 'docs' / 'img'
BG, EDGE, INK, DIM = (22, 24, 30), (64, 70, 84), (236, 238, 244), (160, 166, 180)
YEL, CYA, PNK, GRN, ORA, VIO = (255, 204, 77), (95, 211, 243), (255, 120, 160), (140, 220, 140), (255, 150, 80), (180, 160, 255)
_fc = {}


def F(sz, bold=True):
    k = (sz, bold)
    if k not in _fc:
        for n in (('segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf') if bold else ('segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf')):
            try:
                _fc[k] = ImageFont.truetype(n, sz)
                break
            except OSError:
                pass
        else:
            _fc[k] = ImageFont.load_default()
    return _fc[k]


def up(im, k):
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def tw(d, s, f):
    return int(d.textlength(s, font=f))


def label_box(d, xy, s, col, size=15, anchor='lt'):
    """A dark box with an accent border and white text; returns its rect.  anchor: l/c/r + t/b of the given point."""
    f = F(size)
    lines = s.split('\n')
    w = max(tw(d, ln, f) for ln in lines) + 16
    h = len(lines) * (size + 5) + 8
    x, y = xy
    x = x - w // 2 if anchor[0] == 'c' else (x - w if anchor[0] == 'r' else x)
    y = y - h if anchor[1] == 'b' else y
    d.rounded_rectangle([x, y, x + w, y + h], 6, fill=(30, 33, 42), outline=col, width=2)
    for i, ln in enumerate(lines):
        d.text((x + 8, y + 4 + i * (size + 5)), ln, fill=INK, font=f)
    return (x, y, x + w, y + h)


def callout(d, pt, xy, s, col, anchor='lt', size=15):
    """Dot on `pt`, a line to the label box at `xy`."""
    r = label_box(d, xy, s, col, size, anchor)
    bx = min(max(pt[0], r[0] + 10), r[2] - 10)
    by = r[1] if pt[1] < r[1] else (r[3] if pt[1] > r[3] else (r[1] + r[3]) // 2)
    if not (r[0] <= pt[0] <= r[2] and r[1] <= pt[1] <= r[3]):
        d.line([pt, (bx, by)], fill=col, width=2)
    d.ellipse([pt[0] - 5, pt[1] - 5, pt[0] + 5, pt[1] + 5], fill=col, outline=BG, width=2)
    label_box(d, xy, s, col, size, anchor)        # on top of the line


def card(body, title, sub=None, foot=None, mt=0, mb=0, ml=0, mr=0, pad=24):
    """-> (canvas, (ox, oy)) with the body pasted at (ox, oy); margins leave room for callouts."""
    body = body.convert('RGBA')
    d0 = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    th = 34 + (26 if sub else 0)
    fh = (len(foot.split('\n')) * 22 + 10) if foot else 0
    W = max(body.width + ml + mr, tw(d0, title, F(26)) + 20, tw(d0, sub or '', F(17, False)) + 20) + 2 * pad
    H = pad + th + mt + body.height + mb + fh + pad
    im = Image.new('RGBA', (W, H), BG + (255,))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([1, 1, W - 2, H - 2], 14, outline=EDGE, width=2)
    d.text((pad, pad - 4), title, fill=INK, font=F(26))
    if sub:
        d.text((pad, pad + 30), sub, fill=DIM, font=F(17, False))
    ox, oy = pad + ml, pad + th + mt
    im.alpha_composite(body, (ox, oy))
    if foot:
        for i, ln in enumerate(foot.split('\n')):
            d.text((pad, oy + body.height + mb + 8 + i * 22), ln, fill=DIM, font=F(15, False))
    return im, (ox, oy)


def save_png(im, name):
    p = OUT / name
    im.convert('RGB').save(p, optimize=True)
    print(f'{p.name:28s} {im.width}x{im.height}  {p.stat().st_size // 1024} KB')
    return p


def save_gif(frames, name, ms=100, colors=96, hold_last=1200):
    pal = frames[len(frames) // 2].convert('RGB').quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    q = [f.convert('RGB').quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    dur = [ms] * len(q)
    dur[-1] = hold_last
    p = OUT / name
    q[0].save(p, save_all=True, append_images=q[1:], duration=dur, loop=0, optimize=True, disposal=1)
    print(f'{p.name:28s} {frames[0].width}x{frames[0].height} x{len(q)}  {p.stat().st_size // 1024} KB')
    return p


# ======================================================================== the taskbar strip, offline
def taskbar_strip_frames(seconds=34, fps=10, seed=7, chars=('claude', 'codex'), names=('Claude Code', 'Codex')):
    """Simulated live strip (screen x 0..940, 16 desktop rows + the 48 taskbar rows): plates at the left, fighters in the
    fight zone, the scoreboard at the right - the layout minis.py draws, with DEMO numbers from the real planner."""
    from minis_core import sim, render, scoreboard as SB
    from minis_core.brain import LEFT, RIGHT
    cfg = dict(cfgmod.DEFAULTS)
    cfg.update({'bout_min_s': 999, 'bout_max_s': 999, 'clash_min_s': 999, 'clash_max_s': 999, 'match_min_s': 3, 'match_max_s': 4})
    tele = {LEFT: sim.FakeTelemetry(LEFT, [(0, 'idle', 48.0)], plan=(12.0, 'wk')),
            RIGHT: sim.FakeTelemetry(RIGHT, [(0, 'idle', 31.0)])}
    cfg, atl, brains = sim.make(seed, cfg, 1000.0, chars={LEFT: chars[0], RIGHT: chars[1]})
    for w, x in ((LEFT, 420), (RIGHT, 610)):
        brains[w].x = brains[w].home_x = x
        brains[w].home = (x - 40, x + 40)
    bus, frames, meta = {}, [], []
    sbx = SB.left_x(cfg)
    rec = {'a': [12, 7], 'b': [7, 12]}
    last_result = None
    for i in range(int(seconds * fps) + 1):
        now = 1000.0 + i / fps
        sim.step(brains, tele, now, bus)
        im = Image.new('RGBA', (940, 64), (0, 0, 0, 0))
        bg = Image.new('RGBA', (940, 64), (24, 26, 34, 255))
        dd = ImageDraw.Draw(bg)
        dd.rectangle([0, 16, 940, 63], fill=(32, 32, 32, 255))
        dd.line([(0, 16), (940, 16)], fill=(58, 58, 62, 255))
        for w in (LEFT, RIGHT):
            im.alpha_composite(render.compose_full(atl[w], atl[w], brains[w].view(now), brains[w].snap, now, 940, cfg, win_x=0, show_plate=False))
        for k, w in enumerate((LEFT, RIGHT)):
            bg.alpha_composite(render.plate(atl[w], brains[w].snap, now, name=names[k]), (cfgmod.plate_left(cfg, w), 27))
        hp = {w: brains[w].hp for w in (LEFT, RIGHT)}
        lm = brains[LEFT].last_match
        if lm and lm.get('winner') and last_result is None:
            last_result = (now, lm)
            win = lm['winner']
            rec[win][0] += 1
            rec['b' if win == 'a' else 'a'][1] += 1
        st = dict(names={'a': 'Claude', 'b': 'Codex'}, records={k: tuple(v) for k, v in rec.items()}, mode='taskbar', arena=False, paused=False,
                  hp=hp if hp[LEFT] is not None else None, wins=(brains[LEFT].round or {}).get('wins') or {}, spark=[20, 35, 60, 72, 91, 40, 48])
        if last_result and now - last_result[0] < 6 and hp[LEFT] is None:
            lm = last_result[1]
            sc = lm.get('wins') or {}
            st['result'] = f"{('CLAUDE' if lm['winner'] == 'a' else 'CODEX')} WINS {max(sc.values() or [2])}-{min(sc.values() or [1])}"
        bg.alpha_composite(SB.render(st), (sbx, 18))
        bg.alpha_composite(im)
        frames.append(bg)
        meta.append(dict(t=i / fps, script=any(brains[w].script is not None for w in (LEFT, RIGHT)), x={w: brains[w].x for w in (LEFT, RIGHT)},
                         hp=hp, result='result' in st))
    return frames, meta, cfg


def hero():
    frames, meta, cfg = taskbar_strip_frames()
    idx = [i for i, m in enumerate(meta) if m['script']]
    a, b = max(0, idx[0] - 10), min(len(frames) - 1, idx[-1] + 40) if idx else (0, len(frames) - 1)
    clip = frames[a:b + 1]
    cand = [i for i in range(a, b) if meta[i]['hp'].get('a') is not None and 0 < (meta[i]['hp'].get('a') or 0) < 100 and 0 < (meta[i]['hp'].get('b') or 0) < 100]
    white = lambda i: frames[i].crop((300, 0, 740, 64)).convert('L').point(lambda v: 255 if v > 240 else 0).histogram()[255]   # impact silhouettes
    still_i = min(cand[::3], key=white) if cand else a + (b - a) // 2
    K, X0 = 2, 30
    notes_base = []

    def frame(im, m):
        strip = up(im.crop((X0, 0, 940, 64)), K)
        c, (ox, oy) = card(strip, 'Taskbar Fighters on the Windows 11 taskbar', 'Rendered offline by the real planner and renderer (DEMO numbers)',
                           mt=78, mb=70)
        d = ImageDraw.Draw(c)
        sx = lambda x: ox + (x - X0) * K
        sy = lambda y: oy + y * K
        callout(d, (sx(60), sy(30)), (sx(40), oy - 72), 'HUD plates: program, state,\ncontext meter + number', YEL)
        fx = int((m['x']['a'] + m['x']['b']) / 2)
        callout(d, (sx(fx), sy(20)), (sx(fx) - 120, oy - 72), 'two fighters, one per AI program\n(at most two on stage)', CYA)
        callout(d, (sx(840), sy(24)), (sx(940) - 2, oy - 72), 'scoreboard: W-L, HP, result,\nPause / Arena / Bout now', PNK, anchor='rt')
        d.text((sx(X0) + 4, sy(64) + 14), 'Fighters only use the empty stretch left of the taskbar icons; the Start button and icons are never covered.',
               fill=DIM, font=F(15, False))
        return c

    save_png(frame(frames[still_i], meta[still_i]), 'hero-taskbar.png')
    save_gif([frame(f, meta[a + i]) for i, f in enumerate(clip[::2])], 'hero-bout.gif', ms=200, colors=64)


def annotate_live(src):
    """Annotate captures from tools/taskbar_capture.py (taskbar rows only, bbox 4,1392,936,1440)."""
    src = Path(src)
    stills = sorted(src.glob('*-[0-9].png'))
    gif = next(src.glob('*-match.gif'), None)
    K = 2

    def frame(im):
        strip = up(im.convert('RGBA'), K)
        c, (ox, oy) = card(strip, 'Live: a bout on the real taskbar', 'Captured with tools/taskbar_capture.py (only the taskbar rows of the fighter zone)',
                           mt=78, mb=30)
        d = ImageDraw.Draw(c)
        callout(d, (ox + 70 * K, oy + 12 * K), (ox + 20, oy - 72), 'HUD plates', YEL)
        callout(d, (ox + 470 * K, oy + 6 * K), (ox + 400 * K, oy - 72), 'fighters', CYA, anchor='ct')
        callout(d, (ox + 840 * K, oy + 10 * K), (ox + strip.width, oy - 72), 'scoreboard', PNK, anchor='rt')
        return c

    for i, s in enumerate(stills[:1]):
        save_png(frame(Image.open(s)), 'live-taskbar.png')
    if gif:
        g = Image.open(gif)
        fr = []
        try:
            while True:
                fr.append(frame(g.convert('RGBA')))
                g.seek(g.tell() + 1)
        except EOFError:
            pass
        save_gif(fr[::2], 'live-bout.gif', ms=400, colors=64)


# ======================================================================== roster
PROGRAMS = {'claude': 'Claude Code', 'codex': 'Codex (CLI + app)', 'gemini': 'Gemini (app + CLI)', 'cursor': 'Cursor', 'ollama': 'Ollama',
            'lmstudio': 'LM Studio', 'generic': 'aider, opencode, Windsurf,\nCopilot CLI, Qwen, Grok,\nPerplexity, sparring bot'}
WEAPON = {'claude': 'katana', 'codex': 'twin kunai', 'gemini': 'twin short blades', 'cursor': 'spear', 'ollama': 'staff', 'lmstudio': 'energy katana',
          'generic': 'bow + dagger', 'kunoichi': 'twin fans', 'knight': 'greatsword', 'barbarian': 'axe', 'monk': 'twin tonfa', 'nomad': 'twin chakrams',
          'oni': 'kanabo club'}


def roster_img():
    import rig, roster, build_fighters as BF
    from moves import build_moves
    rig.set_res(1)
    names = list(roster.NAMES)
    S, cw, ch_ = 4, 260, 400
    cols = 7
    rows = (len(names) + cols - 1) // cols
    body = Image.new('RGBA', (cols * cw, rows * ch_), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    for k, nm in enumerate(names):
        ch = roster.get(nm)
        mv = build_moves(ch)['idle']
        fr = BF.render_move(ch, 'idle', mv, None)[0]['r']
        x, y = (k % cols) * cw, (k // cols) * ch_
        extra = nm not in PROGRAMS
        d.rounded_rectangle([x + 6, y + 6, x + cw - 6, y + ch_ - 6], 10, fill=(30, 33, 42), outline=(ORA if extra else tuple(int(ch.accent[i:i + 2], 16) for i in (1, 3, 5))), width=2)
        big = up(fr, S)
        body.alpha_composite(big, (x + (cw - big.width) // 2, y + 4))
        d.text((x + 16, y + 262), ch.display, fill=INK, font=F(22))
        d.text((x + 16, y + 292), 'weapon: ' + WEAPON[nm], fill=DIM, font=F(15, False))
        if extra:
            d.text((x + 16, y + 314), 'selectable extra', fill=ORA, font=F(15))
            d.text((x + 16, y + 334), 'any program can wear it', fill=DIM, font=F(14, False))
        else:
            for i, ln in enumerate(('plays: ' + PROGRAMS[nm]).split('\n')):
                d.text((x + 16, y + 314 + i * 19), ln, fill=CYA, font=F(14))
    c, _ = card(body, 'The V6 roster: 13 armed fighters', 'Top row: one character per AI program.  Bottom row: six extras, picked as a "look" for any program (4x, idle frame 1)',
                foot='Every frame is drawn by art/rig.py from pose data (python art/build_fighters.py).  Generic "Agent" stands in for every program without its own character.')
    save_png(c, 'roster.png')


# ======================================================================== move showcase
def _move_strip(a, move, fxd, facing=1, cw=176, kind='strike'):
    from minis_core.effects import EffectPlayer
    n = len(a.anim[move]['frames'])
    cell = a.cell[0]
    out = []
    p = EffectPlayer(fxd, res=a.res, fps=30)
    hand, sched = a.hand(move), a.move_fx(move)
    for i in range(n):
        t = a.start_ms(move, i) / 1000.0 + 0.001
        for off, name, until in sched:
            # what rounds.py plays: strikes ask for no move effect, a special's own effect is its projectile; and only effects
            # with art on the sheet are drawn here (a missing one would show the engine's procedural stand-in bar)
            if kind == 'strike' or (kind == 'special' and name == move) or not fxd.has_art(name):
                continue
            if off <= t and not any(inst.tag == name for inst in p.active):
                p.spawn(name, off, cw // 2 - 20, a.ground_y, facing, tag=name, hand=hand, fade_ms=((until - off) * 1000.0 if until else None))
        p.tick(t)
        canvas = Image.new('RGBA', (cw, cell), (0, 0, 0, 0))
        for im, lx, ty, layer, inst in p.placements(t, layer='back'):
            _blit(canvas, im, lx, ty)
        canvas.alpha_composite(a.frame_image(move, i, facing), (cw // 2 - 20 - a.anchor(facing), 0))
        for im, lx, ty, layer, inst in p.placements(t, layer='front'):
            _blit(canvas, im, lx, ty)
        f = a.anim[move]['frames'][i]
        out.append((canvas, f['ms'], i == a.anim[move].get('hit_frame'), i in (a.anim[move].get('smear_frames') or [])))
    return out


def _blit(canvas, im, lx, ty):
    w, h = canvas.size
    if lx < w and ty < h and lx + im.width > 0 and ty + im.height > 0:
        canvas.alpha_composite(im.crop((max(0, -lx), max(0, -ty), min(im.width, w - lx), min(im.height, h - ty))), (max(0, lx), max(0, ty)))


def moves():
    from minis_core.atlas import Library
    from minis_core import fx as fxmod
    HD, FX = Library(hd=True), fxmod.default()
    for who in ('claude', 'codex', 'knight'):
        a = HD[who]
        sig = a.signature()
        cw, lab = 176, 190
        rows = [(k, sig[k], _move_strip(a, sig[k], FX, cw=cw, kind=k)) for k in ('strike', 'special', 'super', 'ultimate')]
        n = max(len(r[2]) for r in rows)
        body = Image.new('RGBA', (lab + n * cw, len(rows) * (a.cell[1] + 30)), (0, 0, 0, 0))
        d = ImageDraw.Draw(body)
        for r, (kind, move, fr) in enumerate(rows):
            y = r * (a.cell[1] + 30)
            d.text((0, y + 40), kind.upper(), fill=(YEL, CYA, VIO, PNK)[r], font=F(18))
            d.text((0, y + 64), move, fill=INK, font=F(16, False))
            for i, (im, ms, hit, smear) in enumerate(fr):
                x = lab + i * cw
                d.rounded_rectangle([x + 2, y, x + cw - 2, y + a.cell[1] - 2], 6, fill=(30, 33, 42))
                body.alpha_composite(im, (x, y))
                tag = f'{ms} ms' + ('  HIT' if hit else '') + ('  smear' if smear else '')
                d.text((x + 6, y + a.cell[1] + 2), tag, fill=YEL if hit else DIM, font=F(14, hit))
        c, _ = card(body, f'{a.display}: strike, special, super, ultimate', 'HD sheets (assets_hd/) with the effects from fx.json, frame by frame; every frame shows how long it holds',
                    foot='HIT = the contact frame (hitstop freezes both fighters there).  smear = a streak/crescent frame that sells the swing.\n'
                         'python art/qa_v6.py sheet <character> renders the full rig contact sheet.')
        save_png(c, f'moves-{who}.png')


# ======================================================================== arena (headless)
def _desktop(w, h, wins):
    """A synthetic desktop: a gradient and blank 'windows' at the stage's rectangles (no text, no real screen)."""
    im = Image.new('RGBA', (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(28 + 30 * t), int(40 + 20 * t), int(72 + 30 * t), 255))
    for _, l, t, r, b in wins:
        d.rectangle([l, t, r, b], fill=(236, 238, 242, 255), outline=(150, 156, 170, 255))
        d.rectangle([l, t, r, t + 30], fill=(205, 210, 222, 255))
        for k, col in enumerate(((220, 90, 90), (230, 190, 80), (100, 190, 110))):
            d.ellipse([r - 22 - k * 20, t + 9, r - 10 - k * 20, t + 21], fill=col + (255,))
        for yy in range(t + 52, b - 20, 26):
            d.rounded_rectangle([l + 24, yy, l + 24 + int((r - l - 60) * (0.45 + 0.5 * ((yy * 7919) % 97) / 97)), yy + 10], 4, fill=(208, 212, 222, 255))
    d.rectangle([0, h - 48, w, h], fill=(32, 32, 32, 255))
    return im


def arena_run(seed=2, secs=80, want=None):
    from minis_core import arena as AR, fx as fxmod
    from minis_core.atlas import Library
    HD = Library(hd=True)
    wins = [(1, 260, 260, 900, 760), (2, 1080, 420, 1700, 940), (3, 620, 560, 1180, 1000)]
    st = AR.Stage((0, 0, 1920, 1080), wins, floor_y=1032)
    bd = _desktop(1920, 1080, wins)
    ar = AR.Arena(st, {'a': HD['claude'], 'b': HD['codex']}, fxmod.default(), seed=seed, backdrop=bd, now=0.0, record=lambda *a, **k: None,
                  names={'a': 'Claude', 'b': 'Codex'})
    ar.flashes = True
    surf = AR.Surface(1920, 1080)
    comp = AR.Compositor(ar, surf)
    now = 0.0
    while ar.phase != 'done' and now < secs:
        now += 1 / 30.0
        ar.tick(now)
        comp.render(now)
        want(now, ar, surf)
    return ar


def arena_imgs():
    shots, gif, ring = {}, [], []
    st = dict(shattered=0, expl=0, impacts=0, ko=None, last_cracks=0)
    ko_frames = []

    def crop_mid(ar, surf, w=760, h=520):
        xs = [ar.f[s].x for s in 'ab']
        ys = [ar.f[s].y for s in 'ab']
        cx, cy = int(sum(xs) / 2), int(min(max(sum(ys) / 2 - 120, h // 2), 1080 - h // 2))
        cx = min(max(cx, w // 2), 1920 - w // 2)
        return surf.canvas.crop((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2))

    def want(now, ar, surf):
        if int(now * 30) % 2 == 0 and now > 1.0 and len(gif) < 400:
            gif.append((now, surf.canvas.resize((640, 360), Image.BILINEAR)))
        fy = ar.stage.floor_y
        if 'ledge' not in shots and ar.phase == 'fight' and any(ar.f[s].y < fy - 200 and ar.f[s].grounded for s in 'ab') \
                and sum(ar.cracks.count.values()) > 0:
            shots['ledge'] = surf.canvas.copy()
        if len(ar.cracks.shattered) > st['shattered']:
            st['shattered'] = len(ar.cracks.shattered)
            st['shatter_t'] = now
        if 'shatter' not in shots and st.get('shatter_t') and now - st['shatter_t'] > 0.35:
            shots['shatter'] = surf.canvas.copy()
        if ar.explosions > st['expl']:
            st['expl'] = ar.explosions
            st['expl_t'] = now
        if 'explosion' not in shots and st.get('expl_t') and now - st['expl_t'] > 0.12:
            shots['explosion'] = surf.canvas.copy()
        if 'banner' not in shots and ar.banner and ar.banner[0] == 'winner' and now - ar.phase_t0 > 0.6 and ar.fxp.flash(now) <= 0:
            shots['banner'] = surf.canvas.copy()
        ring.append((now, crop_mid(ar, surf)))
        if ar.final_ko and 'impact' not in shots:                  # the match-deciding KO: 1 frame before, then the impact run
            shots['impact'] = [ring[-2]]
        if 'impact' in shots and len(shots['impact']) < 6 and ring[-1] is not shots['impact'][-1]:
            shots['impact'].append(ring[-1])
        del ring[:-12]
        if ar.final_ko and st['ko'] is None:
            st['ko'] = ar.final_ko[0]
            ko_frames.extend(ring[-6::3])
        if st['ko'] is not None:
            dt = now - st['ko']
            marks = [0.05, 0.3, 0.7, 1.2, 1.9, 2.8]
            if len(ko_frames) - 2 < len(marks) and dt >= marks[len(ko_frames) - 2]:
                ko_frames.append((now, crop_mid(ar, surf)))

    ar = arena_run(want=want)
    print('arena:', ar.state()['phase'], 'winner', ar.winner, 'cracks', sum(ar.cracks.count.values()), 'shattered', len(ar.cracks.shattered),
          'explosions', ar.explosions, 'shots', sorted(shots))
    tag = 'VISUAL ONLY - nothing real happens to your windows'
    # the four-panel still
    panels = [(k, t) for k, t in (('ledge', 'Fighters stand on window ledges; knock-backs crack them'), ('shatter', 'Three cracks shatter a window: shards + letters'),
                                  ('explosion', 'Ultimates explode, flash and shake the overlay'), ('banner', 'Match over: the winner banner over three shattered windows'))
              if k in shots]
    pw, ph = 900, 506
    body = Image.new('RGBA', (2 * pw + 20, ((len(panels) + 1) // 2) * (ph + 40)), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    for i, (k, t) in enumerate(panels):
        x, y = (i % 2) * (pw + 20), (i // 2) * (ph + 40)
        body.alpha_composite(shots[k].resize((pw, ph), Image.LANCZOS).convert('RGBA'), (x, y))
        d.text((x, y + ph + 6), t, fill=INK, font=F(17))
    c, (ox, oy) = card(body, 'Arena mode: the fight breaks out onto a whole monitor', 'Headless render on a synthetic desktop (blank windows drawn for this image)',
                       foot=f'{tag}: the arena is a click-through overlay that only reads window rectangles; it never moves, focuses, closes or types into a window.\n'
                            'python minis.py arena [--monitor N] [--seconds S]   |   ESC, the EXIT button, `arena stop` or the scoreboard end it.')
    dd = ImageDraw.Draw(c)
    label_box(dd, (c.width - 30, 20), tag, PNK, 16, anchor='rt')
    save_png(c, 'arena.png')
    # the GIF: ~7 s around the first shatter (or the middle)
    t0 = st.get('shatter_t') or (gif[len(gif) // 2][0] if gif else 0)
    seq = [im for t, im in gif if t0 - 4.0 <= t <= t0 + 3.0] or [im for t, im in gif[:100]]
    fr = []
    for im in seq[::2]:
        cc, _ = card(im, 'Arena mode (visual only)', 'Headless render, synthetic desktop')
        fr.append(cc)
    save_gif(fr, 'arena.gif', ms=133, colors=96)
    return shots, ko_frames


def impact_imgs(shots, ko_frames):
    imp = shots.get('impact') or []
    if imp:
        cols = 3
        body = Image.new('RGBA', (cols * 420, ((len(imp) + cols - 1) // cols) * 320), (0, 0, 0, 0))
        d = ImageDraw.Draw(body)
        t0 = imp[1][0] if len(imp) > 1 else imp[0][0]
        for i, (t, im) in enumerate(imp):
            x, y = (i % cols) * 420, (i // cols) * 320
            body.alpha_composite(im.resize((400, 274), Image.LANCZOS).convert('RGBA'), (x, y))
            ms = int(round((t - t0) * 1000))
            d.text((x, y + 280), f'frame {i + 1}:  {ms:+d} ms' + ('  (before contact)' if ms < 0 else ''), fill=INK, font=F(16))
        c, _ = card(body, 'Impact frames', 'Heavy hits, supers, ultimates and KOs only: ~130 ms of flat silhouettes and radial lines, then play resumes',
                    foot='The match-deciding KO in the arena (HD, 30 fps); the taskbar plays the same beats at 64 px.\n'
                         '`python minis.py flash off` turns impact frames and white flashes off.')
        save_png(c, 'impact-frames.png')
    if ko_frames:
        n = len(ko_frames)
        cols = 4
        body = Image.new('RGBA', (cols * 420, ((n + cols - 1) // cols) * 320), (0, 0, 0, 0))
        d = ImageDraw.Draw(body)
        t_ko = ko_frames[min(2, n - 1)][0]
        labels = ['the last exchange', 'the deciding blow', 'KO contact: impact frame', 'the freeze holds', 'the fall, in slow motion', 'down; the winner turns', 'winner pose, KO stars', 'the loser slumps up']
        for i, (t, im) in enumerate(ko_frames):
            x, y = (i % cols) * 420, (i // cols) * 320
            body.alpha_composite(im.resize((400, 274), Image.LANCZOS).convert('RGBA'), (x, y))
            d.text((x, y + 280), f'{i + 1}. {labels[i] if i < len(labels) else ""}  ({t - t_ko:+.2f} s)', fill=INK, font=F(15))
        c, _ = card(body, 'The KO finisher', 'The match-deciding KO: a long freeze on contact, the fall in slow motion, dust, the winner\'s pose under the banner (3.4 s in all)',
                    foot='Arena render (HD) of the same finisher beat the taskbar plays (minis_core/rounds.py, POST_KO_S = 3.4).')
        save_png(c, 'ko-finisher.png')


# ======================================================================== select screen + scoreboard (offscreen)
def ui_imgs():
    from minis_core import lineup, scoreboard as SB, select
    from minis_core.atlas import Library
    rows = [dict(source='claude', program='Claude Code', label='Claude', character='claude', state='working'),
            dict(source='codex', program='Codex', label='Codex', character='codex', state='asleep'),
            dict(source='grok', program='Grok', label='Grok', character='generic', state='idle'),
            dict(source='ollama', program='Ollama', label='Ollama', character='ollama', state='idle'),
            dict(source='sparring', program='Sparring bot', label='Bot', character='generic', state='bot')]
    lu = {'a': 'auto', 'b': 'codex', 'skins': {'grok': 'gemini'}}
    chars = lineup.characters()
    m = select.Model(('a', 'b'), select.offer(rows, lu), lu, chars, select.Portraits(Library()), now=0.0)
    m.cur['a'] = 1
    who = up(m.render(0.1), 2)
    m.key(select.VK['enter'], 0.2)                   # P1 confirms Claude -> LOOK stage
    look = up(m.render(0.4), 2)
    m.key(select.VK['enter'], 0.5)                   # P1 keeps Claude's own look; P2 on its pick
    m.key(select.VK['enter'], 0.7)
    m.key(select.VK['enter'], 0.8)
    vs = up(m.render(0.9), 2)
    gap = 30
    vs = vs.crop((0, 0, vs.width, vs.height))
    body = Image.new('RGBA', (who.width + gap + look.width, max(who.height, look.height) + 60 + vs.height), (0, 0, 0, 0))
    body.alpha_composite(who.convert('RGBA'), (0, 0))
    body.alpha_composite(look.convert('RGBA'), (who.width + gap, 0))
    vy = max(who.height, look.height) + 60
    body.alpha_composite(vs.convert('RGBA'), (0, vy))
    c, (ox, oy) = card(body, 'Fighter select', 'Pick WHO fights on each side (or AUTO), then the LOOK it wears; confirm and a VS card plays', mt=80)
    d = ImageDraw.Draw(c)
    lx = ox + who.width + gap
    callout(d, (ox + 88, oy + 150), (ox + 10, oy - 76), 'WHO row: AUTO (the director decides), then every\ndetected or remembered program with its state', YEL)
    callout(d, (lx + 120, oy + 236), (lx + 10, oy - 76), 'LOOK grid: every character on disk, 7 per row;\nany program can wear any character', CYA)
    callout(d, (ox + vs.width - 10, oy + vy + 60), (ox + vs.width + 40, oy + vy + 40), 'VS card, then the lineup is written to control.json', GRN)
    tx, ty = ox + vs.width + 40, oy + vy + 110
    for ln, col in (('Players', INK), ('1P (red) picks the left side, then 2P (blue) the right', DIM), ('', None),
                    ('Open it', INK), ('right-click a fighter > Select fighters...', DIM), ('or click a name on the scoreboard (that side only)', DIM), ('', None),
                    ('Keys', INK), ('arrows move, Enter chooses, Backspace goes back,', DIM), ('Esc or a click elsewhere cancels; mouse + wheel work', DIM), ('', None),
                    ('Same thing from the CLI', INK), ('python minis.py fighters', CYA), ('python minis.py fighters pin b codex', CYA),
                    ('python minis.py skin grok knight', CYA), ('python minis.py pick a auto', CYA), ('python minis.py fighters reset', CYA)):
        if col:
            d.text((tx, ty), ln, fill=col, font=F(17, col == INK))
        ty += 26 if col else 12
    save_png(c, 'select.png')

    base = dict(names={'a': 'Claude', 'b': 'Codex'}, records={'a': (12, 7), 'b': (7, 12)}, mode='taskbar', arena=False, paused=False,
                hp=None, wins={}, spark=[20, 35, 60, 72, 91, 40, None])
    states = (('Plain', 'names + W-L per program, 7-day context sparkline, three buttons', base),
              ('During a match', 'two HP bars and the round score', dict(base, hp={'a': 64, 'b': 22}, wins={'a': 1, 'b': 0})),
              ('After a match', 'a plain result line for a few seconds', dict(base, result='CLAUDE WINS 2-1')),
              ('A fighter hidden', '"show" brings it back (or: python minis.py show b)', dict(base, hidden={'b': 3120.0})),
              ('Paused', 'every fighter frozen; the button now says Resume', dict(base, mode='paused', paused=True)))
    ims = []
    for title, sub, stt in states:
        im = SB.render(stt)
        bg = Image.new('RGBA', (im.width + 16, 48), (32, 32, 32, 255))
        bg.alpha_composite(im, (8, 2))
        ims.append((title, sub, up(bg, 3)))
    rowh = ims[0][2].height + 22
    body = Image.new('RGBA', (ims[0][2].width + 40 + 560, len(ims) * rowh), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    for i, (title, sub, im) in enumerate(ims):
        y = i * rowh
        body.alpha_composite(im, (0, y))
        d.text((im.width + 30, y + 36), title, fill=INK, font=F(20))
        d.text((im.width + 30, y + 66), sub, fill=DIM, font=F(16, False))
    c, (ox, oy) = card(body, 'The scoreboard widget', 'Sits at the right end of the fighter zone, just left of the taskbar icons (3x)',
                       foot='Click a name to pick that side\'s fighter.  Pause/Resume freezes every fighter; Arena starts arena mode; Bout now starts one bout.\n'
                            'Only the names, the buttons and "show" take clicks; the rest is click-through.')
    save_png(c, 'scoreboard.png')


# ======================================================================== plates
def plates_img():
    from minis_core import render
    from minis_core.atlas import Library
    from minis_core.telemetry import Snapshot
    L = Library()
    S = 5
    big = up(render.plate(L['claude'], Snapshot('claude', 'working', 48.0, 12.0, 'wk', resets_in='2d 4h'), 0.0, name='Claude Code'), S)
    body = Image.new('RGBA', (big.width, big.height), (0, 0, 0, 0))
    body.alpha_composite(big)
    c1, (ox, oy) = card(body, 'The HUD plate', 'One per fighter, fixed at the left end of the zone; numbers and states only (5x)', mt=90, mb=110, ml=40, mr=40)
    d = ImageDraw.Draw(c1)
    callout(d, (ox + 30 * S, oy + 7 * S), (ox - 20, oy - 86), 'program name\n(in its accent colour)', YEL)
    callout(d, (ox + 108 * S, oy + 7 * S), (ox + big.width + 20, oy - 86), 'state word', CYA, anchor='rt')
    callout(d, (ox + 25 * S, oy + 19 * S), (ox - 20, oy + big.height + 30), '10-segment context meter:\naccent < 70%, amber 70-89%,\nred and blinking at 90%+', PNK)
    callout(d, (ox + 80 * S, oy + 19 * S), (ox + big.width + 20, oy + big.height + 30), 'context %  +  plan figure and reset\ncountdown (only when it can be trusted)', GRN, anchor='rt')
    states = [('working', 48.0, None, ''), ('idle', 23.0, None, ''), ('waiting', 61.0, None, ''), ('done', 33.0, None, ''),
              ('working', 78.0, None, ''), ('working', 93.0, None, ''), ('limit', 96.0, None, ''), ('sleeping', None, None, '')]
    expl = ['busy on a task', 'nothing for 10 min', 'a tool call unanswered 45 s:\nneeds you (amber border)', 'just finished a task (8 s)',
            '70%+ context: amber', '90%+ context: red blink', 'at its limit (KO + console)', '30 min quiet, or dormant\npartner: ctx unknown = "-"']
    who = [('claude', 'Claude Code'), ('codex', 'Codex'), ('gemini', 'Gemini'), ('cursor', 'Cursor'), ('ollama', 'Ollama'), ('lmstudio', 'LM Studio'),
           ('codex', 'Codex'), ('generic', 'Grok')]
    rowh = 26 * 3 + 30
    body2 = Image.new('RGBA', (2 * (128 * 3 + 340), 4 * rowh), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(body2)
    for i, (st, ctx, p, lab) in enumerate(states):
        x, y = (i // 4) * (128 * 3 + 340), (i % 4) * rowh
        ch, nm = who[i]
        body2.alpha_composite(up(render.plate(L[ch], Snapshot(ch, st, ctx, p, lab), 0.0, name=nm), 3), (x, y))
        for k, ln in enumerate(expl[i].split('\n')):
            d2.text((x + 128 * 3 + 16, y + 14 + k * 22), ln, fill=INK if k == 0 else DIM, font=F(16, k == 0))
    c2, _ = card(body2, 'Every state', 'Unknown is always "-", never a guess.  Process-detected programs have no numbers (ctx -)',
                 foot='Context = tokens of the newest assistant line / the model\'s context window, read from local transcripts (numbers only).')
    if c1.width < c2.width:
        c1, (ox, oy) = card(body, 'The HUD plate', 'One per fighter, fixed at the left end of the zone; numbers and states only (5x)', mt=90, mb=110, ml=40,
                            mr=40 + c2.width - c1.width)
        d = ImageDraw.Draw(c1)
        callout(d, (ox + 30 * S, oy + 7 * S), (ox - 20, oy - 86), 'program name\n(in its accent colour)', YEL)
        callout(d, (ox + 108 * S, oy + 7 * S), (ox + big.width + 20, oy - 86), 'state word', CYA, anchor='rt')
        callout(d, (ox + 25 * S, oy + 19 * S), (ox - 20, oy + big.height + 30), '10-segment context meter:\naccent < 70%, amber 70-89%,\nred and blinking at 90%+', PNK)
        callout(d, (ox + 80 * S, oy + 19 * S), (ox + big.width + 20, oy + big.height + 30), 'context %  +  plan figure and reset\ncountdown (only when it can be trusted)', GRN, anchor='rt')
        tx = ox + big.width + 120
        for i, (ln, col) in enumerate((('Colours', INK), ("border + name: the program's accent", DIM), ('amber border: waiting for you', DIM),
                                       ('meter: accent / amber 70%+ / red 90%+', DIM), ('dimmed fighter: asleep or dormant', DIM))):
            d.text((tx, oy + i * 28), ln, fill=col, font=F(17, col == INK))
    W = max(c1.width, c2.width)
    im = Image.new('RGBA', (W, c1.height + c2.height + 16), (0, 0, 0, 0))
    im.alpha_composite(c1, (0, 0))
    im.alpha_composite(c2, (0, c1.height + 16))
    bg = Image.new('RGBA', im.size, BG + (255,))
    bg.alpha_composite(im)
    save_png(bg, 'plates.png')


# ======================================================================== detection diagram
def detection_img():
    W, H = 1540, 720
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def box(x, y, w, h, title, lines, col):
        d.rounded_rectangle([x, y, x + w, y + h], 10, fill=(30, 33, 42), outline=col, width=3)
        d.text((x + 14, y + 10), title, fill=col, font=F(19))
        for i, ln in enumerate(lines):
            d.text((x + 14, y + 40 + i * 22), ln, fill=INK if not ln.startswith('  ') else DIM, font=F(15, False))

    def arrow(x0, y0, x1, y1, col=DIM, label=None):
        d.line([(x0, y0), (x1, y1)], fill=col, width=3)
        import math
        a = math.atan2(y1 - y0, x1 - x0)
        for s in (-0.45, 0.45):
            d.line([(x1, y1), (x1 - 14 * math.cos(a + s), y1 - 14 * math.sin(a + s))], fill=col, width=3)
        if label:
            d.text(((x0 + x1) // 2 - tw(d, label, F(13, False)) // 2, (y0 + y1) // 2 - 22), label, fill=DIM, font=F(13, False))

    box(20, 20, 300, 300, 'Programs on your PC', ['Claude Code', 'Codex (CLI + desktop app)', 'Gemini (app + CLI)', 'Cursor, Windsurf', 'Ollama, LM Studio',
                                                  'aider, opencode', 'Copilot CLI, Qwen Code', 'Perplexity, Grok'], YEL)
    box(20, 380, 300, 300, 'Not read, ever', ['prompt or reply text', 'window titles', 'file or project names', 'the network', 'your agents\' settings',
                                             '  hooks, status lines and config', '  are never touched'], PNK)
    box(410, 20, 360, 190, 'Transcript sources', ['Claude Code, Codex', '  newest local session file;', '  only appended bytes, numbers', '  and enums: state, context %,',
                                                  '  plan % when it checks out'], CYA)
    box(410, 250, 360, 190, 'Process sources', ['everything else in the table', '  exe / package name (ctypes),', '  working = process tree CPU',
                                               '  > 15% of one core (6 s avg);', '  no numbers: ctx -'], CYA)
    box(410, 480, 360, 200, 'Memory (seen.json)', ['id, last activity, character,', 'program - nothing else', '  a program that went quiet stays', '  a dormant partner for 24 h;',
                                                  '  else the sparring bot'], CYA)
    box(860, 180, 290, 330, 'Director', ['polls every 2 s', 'picks at most two', '  by recency, kept stable:', '  a slot changes only when', '  another program is active',
                                         '  AND its own idle > 60 s', 'your lineup (fighter select)', '  overrides a side', 'writes assign.json'], GRN)
    box(1230, 60, 250, 200, 'Slot a (left)', ['fighter process', '  layered window over', '  the taskbar; plate,', '  bouts from usage'], ORA)
    box(1230, 420, 250, 200, 'Slot b (right)', ['fighter process', '  same timeline from the', '  same seed: contacts land', '  on the same instant'], ORA)
    arrow(320, 120, 405, 110, label='')
    arrow(320, 170, 405, 330)
    arrow(770, 115, 855, 260)
    arrow(770, 345, 855, 345)
    arrow(770, 580, 855, 440)
    arrow(1150, 300, 1225, 160)
    d.text((1160, 340), 'assign.json', fill=DIM, font=F(14))
    arrow(1150, 400, 1225, 520)
    d.line([(1355, 260), (1355, 420)], fill=VIO, width=3)
    d.text((1365, 306), 'bus/a.json <->', fill=VIO, font=F(14))
    d.text((1365, 326), 'bus/b.json', fill=VIO, font=F(14))
    d.text((1365, 348), 'invites, events,', fill=DIM, font=F(13, False))
    d.text((1365, 366), 'x, HP', fill=DIM, font=F(13, False))
    c, _ = card(im, 'How detection works', 'programs -> sources -> director -> slots a / b -> fighters   (all local, every 2 s)',
                foot='python minis.py detect shows what the sources see right now and how (names and numbers only).\n'
                     'minis_core/sources.py holds the program table; add a row there to teach minis a new program.')
    save_png(c, 'detection.png')


# ======================================================================== before / after
def before_after():
    from minis_core.atlas import Atlas
    old = Path(tempfile.mkdtemp(prefix='minis-v5-'))
    names = ('claude', 'codex', 'gemini', 'cursor', 'ollama', 'lmstudio', 'generic')
    for n in names:
        (old / n).mkdir()
        for f in ('anim.json', 'sheet.png', 'sheet_l.png', 'fx.json', 'fx.png', 'proj.png'):
            r = subprocess.run(['git', 'show', f'42c8760:assets/{n}/{f}'], cwd=ROOT, capture_output=True)
            if r.returncode == 0:
                (old / n / f).write_bytes(r.stdout)
    S, cw = 3, 64 * 3 + 12
    body = Image.new('RGBA', (len(names) * cw * 2 + (len(names) - 1) * 16, 64 * S * 2 + 90), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    for i, n in enumerate(names):
        a_old, a_new = Atlas(n, root=old / n), Atlas(n)
        x = i * (cw * 2 + 16)
        for k, (a, tag) in enumerate(((a_old, 'V5'), (a_new, 'V6'))):
            for r, mv in enumerate(('idle', a.signature()['strike'])):
                hf = a.anim[mv].get('hit_frame') or 0 if r else 0
                fr = up(a.frame_image(mv, hf, 1), S)
                y = r * (64 * S + 6)
                d.rounded_rectangle([x + k * cw, y, x + k * cw + cw - 6, y + 64 * S], 6, fill=(30, 33, 42))
                body.alpha_composite(fr, (x + k * cw, y))
            d.text((x + k * cw + 6, 2), tag, fill=DIM if k == 0 else YEL, font=F(16))
        d.text((x + 6, 2 * (64 * S + 6) + 4), a_new.display, fill=INK, font=F(18))
    c, _ = card(body, 'V5 -> V6: the armed redraw', 'Each pair: V5 (left, from git 42c8760) and V6 (right); top row idle, bottom row the signature strike\'s contact frame (3x)',
                foot='V6: taller (~4.5 heads), a weapon in hand, 1 px outline and 5 tones in HD, weapon crescents and streak smears, longer wind-ups and holds.')
    save_png(c, 'before-after.png')
    shutil.rmtree(old, True)


# ======================================================================== app icon + tray (illustration)
def icon_img():
    from minis_win import tray as T
    ico = Image.open(ROOT / 'assets' / 'icon' / 'minis.ico')
    sizes = sorted(ico.info.get('sizes') or [(16, 16), (32, 32), (48, 48)])
    frames = {}
    for sz in sizes:
        ico.size = sz
        frames[sz[0]] = ico.convert('RGBA').copy()
    big = Image.open(ROOT / 'assets' / 'icon' / 'minis-256.png').convert('RGBA')
    small = [s for s in (16, 20, 24, 32, 48) if s in frames]
    # left: the 256 px icon; right: the real small sizes at 1x and 4x on the dark and light taskbar colours
    rows = []
    for bgc, name in (((32, 32, 32, 255), 'dark taskbar'), ((243, 243, 243, 255), 'light taskbar')):
        row = Image.new('RGBA', (sum(s * 4 + 40 for s in small) + 170, 10 + max(small) + 12 + max(small) * 4 + 30), bgc)
        d = ImageDraw.Draw(row)
        x = 16
        for s in small:
            row.alpha_composite(frames[s], (x, 10))
            y4 = 10 + max(small) + 12
            row.alpha_composite(up(frames[s], 4), (x, y4))
            d.text((x, y4 + s * 4 + 4), f'{s} px', fill=(120, 120, 130), font=F(14, False))
            x += s * 4 + 40
        d.text((x, 14), name, fill=(150, 150, 160), font=F(15))
        rows.append(row)
    rh = max(r.height for r in rows)
    body = Image.new('RGBA', (big.width + 40 + max(r.width for r in rows), max(big.height, 2 * rh + 20)), (0, 0, 0, 0))
    body.alpha_composite(big, (0, 0))
    for i, r in enumerate(rows):
        body.alpha_composite(r, (big.width + 40, i * (rh + 20)))
    c1, _ = card(body, 'The app icon', 'Two crossed katanas on a terracotta disc; every size is drawn natively (no resampling): 1x and 4x on both taskbar colours',
                 foot='assets/icon/minis.ico and minis-256.png, built by python art/build_icon.py [--preview <png>]')
    # the tray, as an illustration (not a capture): the real tooltip text and menu items from minis_win/tray.py
    W_, H_ = 980, 470
    im = Image.new('RGBA', (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, H_ - 48, W_, H_], fill=(32, 32, 32, 255))
    d.line([(0, H_ - 48), (W_, H_ - 48)], fill=(58, 58, 62, 255))
    ix = W_ - 260
    d.text((ix - 40, H_ - 36), '^', fill=(200, 200, 205), font=F(18))
    tic = frames.get(20) or frames[min(frames)]
    im.alpha_composite(tic, (ix + 6, H_ - 24 - tic.height // 2))
    d.text((W_ - 120, H_ - 40), '9:41 AM', fill=(220, 220, 225), font=F(14, False))
    d.text((W_ - 120, H_ - 22), '10/15/2026', fill=(220, 220, 225), font=F(14, False))
    tip = T.tooltip({'a': {'source': 'claude', 'program': 'Claude Code', 'character': 'claude'},
                     'b': {'source': 'codex', 'program': 'Codex', 'character': 'codex'}})
    tw_ = tw(d, tip, F(15, False)) + 20
    d.rounded_rectangle([ix - tw_ + 40, H_ - 100, ix + 40, H_ - 66], 6, fill=(43, 43, 48), outline=(80, 80, 90))
    d.text((ix - tw_ + 50, H_ - 93), tip, fill=INK, font=F(15, False))
    items = T.tray_menu({'paused': False, 'flash': True, 'plates': True, 'rival': True, 'arena': False})
    mx, my, mw = ix - 470, 20, 300
    ih = 30
    n = sum(1 for it in items)
    mh = sum(ih if it else 10 for it in items) + 12
    d.rounded_rectangle([mx, my, mx + mw, my + mh], 8, fill=(43, 43, 48), outline=(80, 80, 90))
    y = my + 6
    for it in items:
        if not it:
            d.line([(mx + 10, y + 5), (mx + mw - 10, y + 5)], fill=(70, 70, 78))
            y += 10
            continue
        label, opt = it[1], (it[2] if len(it) > 2 else {})
        col = (120, 120, 128) if opt.get('disabled') else INK
        if opt.get('checked'):
            d.text((mx + 12, y + 4), 'v', fill=INK, font=F(15))
        d.text((mx + 36, y + 4), label, fill=col, font=F(15, False))
        y += ih
    c2, (ox, oy) = card(im, 'Tray icon and menu (illustration)', 'Drawn for this page with the real tooltip text and menu items; not a screen capture', mr=10,
                        foot='Left-click the icon: fighter select.  Right-click: the menu above.  "tray_icon": false in minis.json turns it off.\n'
                             'python minis.py shortcut [--desktop] adds Taskbar Fighters to Start; then right-click it in Start > Pin to taskbar.')
    dd = ImageDraw.Draw(c2)
    callout(dd, (ox + ix + 16, oy + H_ - 40), (ox + ix + 80, oy + H_ - 200), 'the tray icon\nhover: who is fighting', YEL)
    callout(dd, (ox + mx + mw, oy + my + 40), (ox + mx + mw + 40, oy + my + 10), 'right-click menu', CYA)
    W = max(c1.width, c2.width)
    out = Image.new('RGBA', (W, c1.height + c2.height + 16), BG + (255,))
    out.alpha_composite(c1, (0, 0))
    out.alpha_composite(c2, (0, c1.height + 16))
    save_png(out, 'icon-tray.png')


SECTIONS = dict(icon=icon_img, hero=hero, roster=roster_img, moves=moves, ui=ui_imgs, plates=plates_img, detection=detection_img, before=before_after)


def main(argv=None):
    global OUT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='')
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--annotate-live', default=None, help='a tools/taskbar_capture.py --out folder')
    a = ap.parse_args(argv)
    OUT = Path(a.out)
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        if a.annotate_live:
            annotate_live(a.annotate_live)
            return 0
        only = set(filter(None, a.only.split(','))) or set(SECTIONS) | {'arena'}
        for k, fn in SECTIONS.items():
            if k in only:
                fn()
        if 'arena' in only:
            impact_imgs(*arena_imgs())
    finally:
        shutil.rmtree(_TMP, True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
