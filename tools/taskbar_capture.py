"""Capture the taskbar rows the fighters live on - and nothing else - for a look at a live bout.

    python tools/taskbar_capture.py --out <dir> [--prefix rival] [--seconds 40] [--fps 5] [--stills 4,16,30] [--demo match]
                                    [--bbox 4,1392,936,1440]

Grabs ONLY the given screen rectangle (default: the fighters' roam zone on a 2560x1440 primary display with a 48 px
bottom taskbar) with PIL.ImageGrab, `--fps` times a second for `--seconds`.  Writes <prefix>-1.png, -2.png, -3.png at the
`--stills` seconds and <prefix>-match.gif from every frame.  `--demo <kind>` asks the fighters for that bout first
(what `minis.py demo` does), so the recording catches it from the walk-out.  Never a full-screen grab, never a
window title: the rectangle is the whole input.
"""
from __future__ import annotations
import argparse, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True)
    ap.add_argument('--prefix', default='rival')
    ap.add_argument('--seconds', type=float, default=40.0)
    ap.add_argument('--fps', type=float, default=5.0)
    ap.add_argument('--stills', default='4,16,30', help='seconds into the recording for the three PNG stills')
    ap.add_argument('--demo', default=None, choices=(None, 'spar', 'clash', 'ranged', 'match'))
    ap.add_argument('--bbox', default='4,1392,936,1440', help='left,top,right,bottom in primary-screen pixels')
    a = ap.parse_args(argv)
    from PIL import ImageGrab
    bbox = tuple(int(v) for v in a.bbox.split(','))
    if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        print('--bbox needs left,top,right,bottom')
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stills = sorted(float(s) for s in a.stills.split(',') if s.strip())
    if a.demo:
        from minis_core import control
        control.request_demo(a.demo)
        print(f'{a.demo} requested')
    frames, times = [], []
    t0 = time.monotonic()
    nxt = 0.0
    taken = 0
    while True:
        el = time.monotonic() - t0
        if el >= a.seconds:
            break
        if el >= nxt:
            im = ImageGrab.grab(bbox=bbox, all_screens=False).convert('RGB')
            frames.append(im)
            times.append(el)
            nxt += 1.0 / a.fps
            while taken < len(stills) and el >= stills[taken]:
                p = out / f'{a.prefix}-{taken + 1}.png'
                im.save(p)
                print(f'{el:5.1f}s  {p}')
                taken += 1
        time.sleep(0.01)
    while taken < len(stills) and frames:                       # a recording shorter than the last still mark
        p = out / f'{a.prefix}-{taken + 1}.png'
        frames[-1].save(p)
        print(f'(end)  {p}')
        taken += 1
    if frames:
        gif = out / f'{a.prefix}-match.gif'
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=int(1000 / a.fps), loop=0, optimize=False)
        print(f'{len(frames)} frames -> {gif}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
