"""A live picture of a bout at any fighter size, WITHOUT a screen capture: the running fighters dump the images they hand
to their own windows (minis_core/dump.py), and this tool composites them over a neutral desktop with a taskbar bar.

    python tools/own_capture.py --out <dir> [--seconds 20] [--fps 10] [--demo match|spar|clash|ranged]
                                [--gif live-bout.gif] [--still live-taskbar.png --at S] [--keep] [--no-frames]

Writes <data_dir>/dump/request.json, optionally asks for a demo bout (what `minis.py demo` does), waits, deletes the
request, and builds frames at --fps: at each tick the latest dump of every window at or before it, pasted at its screen
rect.  Outputs (relative names land in --out): the GIF, the PNG still at --at seconds (default: the middle), and unless
--no-frames a frames/ folder + own-capture.json for `tools/doc_images.py --annotate-live <out>`.  With neither --gif nor
--still both defaults are written.  The raw dump folder is deleted unless --keep.  The fighters must be running.

Nothing here imports or calls a screen-capture API: the inputs are the processes' own images and their window rects.
The taskbar rect comes from the OS appbar query (minis_win.shell.taskbar_rect), never from pixels.
"""
from __future__ import annotations
import argparse, json, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

BG = (59, 63, 71, 255)            # a flat desktop
BAR = (31, 31, 35, 217)           # the taskbar, ~85 % opaque
BAR_H = 48
MARGIN = 8
LAYERS = ('scoreboard', 'a-plate', 'b-plate', 'a', 'b')    # paint order: fighters on top


def load_records(dump_dir):
    """-> {role: [record, ...] sorted by wall}; unreadable records are skipped."""
    out = {}
    for p in sorted(Path(dump_dir).glob('*.json')):
        try:
            r = json.loads(p.read_text(encoding='utf-8'))
            if r.get('role') in LAYERS and isinstance(r.get('png'), str):
                r['wall'] = float(r['wall'])
                for k in ('x', 'y', 'w', 'h'):
                    r[k] = int(r[k])
                out.setdefault(r['role'], []).append(r)
        except Exception:
            continue
    for v in out.values():
        v.sort(key=lambda r: r['wall'])
    return out


def latest(recs, t):
    best = None
    for r in recs:
        if r['wall'] <= t:
            best = r
        else:
            break
    return best


def os_taskbar_rect():
    """(l, t, r, b) of the taskbar from the OS appbar query, or None.  An API call, not a capture."""
    try:
        if sys.platform == 'win32':
            from minis_win.shell import taskbar_rect
        elif sys.platform == 'darwin':
            from minis_mac.shell import taskbar_rect
        else:
            return None
        l, t, r, b = (int(v) for v in taskbar_rect()[:4])
        return (l, t, r, b) if r > l and b > t else None
    except Exception:
        return None


def plan(records, ticks, taskbar=None):
    """-> (crop box (l, t, r, b) in screen px, bar rect (l, t, r, b)).  The crop is the union of every visible window rect
    used by a frame, plus MARGIN, stretched to keep the taskbar bar rows in frame."""
    rects = []
    for t in ticks:
        for role in LAYERS:
            r = latest(records.get(role, ()), t)
            if r and r.get('visible', True):
                rects.append((r['x'], r['y'], r['x'] + r['w'], r['y'] + r['h']))
    if not rects:
        return None, None
    ux0, uy0 = min(r[0] for r in rects), min(r[1] for r in rects)
    ux1, uy1 = max(r[2] for r in rects), max(r[3] for r in rects)
    if taskbar and taskbar[1] < uy1 and taskbar[3] > uy0:           # a taskbar the windows actually sit on
        bar = (ux0 - MARGIN, taskbar[1], ux1 + MARGIN, taskbar[3])
    else:
        bar = (ux0 - MARGIN, uy1 - BAR_H, ux1 + MARGIN, uy1)
    box = (ux0 - MARGIN, min(uy0 - MARGIN, bar[1]), ux1 + MARGIN, max(uy1, bar[3]))   # nothing below the taskbar: the screen edge
    return box, bar


class Compositor:
    def __init__(self, dump_dir, records=None):
        self.dir = Path(dump_dir)
        self.records = load_records(dump_dir) if records is None else records
        self._img = {}

    def image(self, rec):
        key = (rec['png'], rec['w'], rec['h'])
        if key not in self._img:
            p = self.dir / Path(rec['png']).name             # a bare file name, never a path out of the dump folder
            im = Image.open(p).convert('RGBA')
            if im.size != (rec['w'], rec['h']):
                im = im.resize((rec['w'], rec['h']), Image.NEAREST)
            self._img[key] = im
        return self._img[key]

    def frame(self, t, box, bar):
        """The composited canvas (RGBA, box-sized) at wall time t, plus {role: rect relative to the canvas}."""
        x0, y0 = box[0], box[1]
        c = Image.new('RGBA', (box[2] - box[0], box[3] - box[1]), BG)
        c.alpha_composite(Image.new('RGBA', (bar[2] - bar[0], bar[3] - bar[1]), BAR), (bar[0] - x0, bar[1] - y0))
        rects = {}
        for role in LAYERS:
            r = latest(self.records.get(role, ()), t)
            if not r or not r.get('visible', True):
                continue
            try:
                im = self.image(r)
            except Exception:
                continue
            px, py = r['x'] - x0, r['y'] - y0
            layer = Image.new('RGBA', c.size, (0, 0, 0, 0))
            layer.paste(im, (px, py))
            c.alpha_composite(layer)
            rects[role] = (px, py, px + r['w'], py + r['h'])
        return c, rects


def save_gif(frames, path, ms):
    """Palette-quantized GIF with real timing; the palette is built from a sample of all frames."""
    step = max(1, len(frames) // 8)
    sample = frames[::step]
    strip = Image.new('RGB', (sample[0].width, sample[0].height * len(sample)))
    for i, f in enumerate(sample):
        strip.paste(f.convert('RGB'), (0, i * f.height))
    pal = strip.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    q = [f.convert('RGB').quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=int(round(ms)), loop=0, optimize=True, disposal=1)


def hidden_reason(ddir):
    """Why nothing could be drawn: windows that answered but were hidden the whole time, or no window at all."""
    roles = set()
    for p in Path(ddir).glob('*.json'):
        try:
            roles.add(json.loads(p.read_text(encoding='utf-8')).get('role'))
        except (OSError, ValueError):
            pass
    if not roles:
        return 'the dumps hold no visible window in that span'
    return ('Taskbar Fighters is running but its windows stayed hidden the whole time (%s): a full-screen app is up, '
            'an arena is playing, or they are hidden (`minis.py show`).' % ', '.join(sorted(r for r in roles if r)))


def build(dump_dir, t0, seconds, fps, out, gif=None, still=None, at=None, frames_dir=True, taskbar=None):
    """Composite the dumps in dump_dir for [t0, t0 + seconds] -> written paths (and the manifest dict)."""
    out = Path(out)
    comp = Compositor(dump_dir)
    n = max(1, int(round(seconds * fps)))
    ticks = [t0 + i / fps for i in range(n)]
    box, bar = plan(comp.records, ticks, taskbar)
    if box is None:
        return [], None
    frames, rects = [], []
    for t in ticks:
        im, rr = comp.frame(t, box, bar)
        frames.append(im)
        rects.append(rr)
    written = []
    out.mkdir(parents=True, exist_ok=True)
    if gif:
        p = gif if Path(gif).is_absolute() else out / gif
        save_gif(frames, p, 1000.0 / fps)
        written.append(Path(p))
    si = min(n - 1, max(0, int(round((seconds / 2.0 if at is None else at) * fps))))
    if still:
        p = still if Path(still).is_absolute() else out / still
        frames[si].convert('RGB').save(p, optimize=True)
        written.append(Path(p))
    manifest = {'fps': fps, 'seconds': seconds, 'origin': [box[0], box[1]], 'size': [box[2] - box[0], box[3] - box[1]],
                'bar': [bar[0] - box[0], bar[1] - box[1], bar[2] - box[0], bar[3] - box[1]], 'still_index': si,
                'rects': [{k: list(v) for k, v in rr.items()} for rr in rects]}
    if frames_dir:
        fd = out / 'frames'
        if fd.exists():
            shutil.rmtree(fd, True)
        fd.mkdir(parents=True)
        for i, f in enumerate(frames):
            f.convert('RGB').save(fd / f'{i:04d}.png')
        (out / 'own-capture.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
        written.append(fd)
    return written, manifest


def main(argv=None, sleep=time.sleep, wall=time.time):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True)
    ap.add_argument('--seconds', type=float, default=20.0)
    ap.add_argument('--fps', type=float, default=10.0)
    ap.add_argument('--demo', default=None, choices=('spar', 'clash', 'ranged', 'match'))
    ap.add_argument('--gif', default=None)
    ap.add_argument('--still', default=None)
    ap.add_argument('--at', type=float, default=None, help='seconds into the recording for --still (default: the middle)')
    ap.add_argument('--keep', action='store_true', help='keep the raw dump folder')
    ap.add_argument('--no-frames', action='store_true', help='skip frames/ + own-capture.json')
    a = ap.parse_args(argv)
    if a.seconds <= 0 or a.fps <= 0:
        print('--seconds and --fps must be positive')
        return 2
    if not a.gif and not a.still:
        a.gif, a.still = 'live-bout.gif', 'live-taskbar.png'
    from minis_core import dump
    from minis_core.bus import write_json_atomic
    root = dump.dump_root()
    rid = 'cap%x' % int(wall() * 1000)
    ddir = dump.safe_dir(root, rid)
    req_path = dump.request_path(root)
    every = max(dump.MIN_EVERY_MS, int(500 / a.fps))             # dumps at twice the frame rate
    rc = 0
    try:
        start = wall()
        if not write_json_atomic(req_path, {'id': rid, 'until': start + a.seconds + 2.0, 'every_ms': every}):
            print(f'could not write {req_path}')
            return 1
        print(f'dump requested ({rid}, every {every} ms)')
        sleep(dump.CHECK_S + 0.3)                                 # every process sees the request and dumps what it shows
        if a.demo:
            from minis_core import control
            control.request_demo(a.demo)
            print(f'{a.demo} requested')
        t0 = wall()
        end = t0 + a.seconds
        while wall() < end:
            sleep(min(0.25, max(0.0, end - wall())))
        sleep(0.3)                                                # the last dumps land
    except KeyboardInterrupt:
        print('interrupted')
        rc = 130
    finally:
        try:
            req_path.unlink()
        except OSError:
            pass
    try:
        if rc == 0:
            if ddir is None or not ddir.is_dir():
                print('no dumps arrived - are the fighters running (minis.py status)?')
                return 1
            written, _ = build(ddir, t0, a.seconds, a.fps, a.out, gif=a.gif, still=a.still, at=a.at,
                               frames_dir=not a.no_frames, taskbar=os_taskbar_rect())
            if not written:
                print(hidden_reason(ddir))
                rc = 1
            for p in written:
                print(p)
    finally:
        if not a.keep and ddir is not None and ddir.is_dir() and ddir.parent == Path(root).resolve():
            shutil.rmtree(ddir, True)
        elif a.keep and ddir is not None:
            print(f'raw dumps kept: {ddir}')
    return rc


if __name__ == '__main__':
    sys.exit(main())
