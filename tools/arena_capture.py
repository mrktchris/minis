"""Capture the live arena at the moments that matter, from the arena's OWN window only (PrintWindow; never the desktop).

    python tools/arena_capture.py --monitor N --out <dir> [--seconds 45] [--seed K] [--fps 12] [--prefix v5]

Starts the arena (`minis.start_arena`, its own process), then polls PrintWindow of the `MinisArena` window at `fps` into a
short RAM ring and reads the arena heartbeat (`arena.json`, 1 Hz, carries the last 16 content-free events with their
monotonic times).  For each wanted moment the frame nearest the event time (+ a small offset) is written once:

    <prefix>-<effect>.png     'beam' event + 0.06 s (an ultimate's main effect mid-extension, named after it: kamehameha, rasengan_burst ...)
    <prefix>-flash.png        'flash' event + 0.035 s (the one-frame white flash of an ultimate landing; at 20 fps it is sometimes the frame beside it)
    <prefix>-air.png          'air_exchange' + 0.2 s (both fighters up: an air-to-air strike)
    <prefix>-knockdown.png    'knockdown' + 0.45 s  (the defender going down)
    <prefix>-last.png         the last frame seen

The ring holds ~3 s of frames because the heartbeat can lag an event by up to a second.  Nothing but these PNGs is written.
"""
import argparse, collections, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import minis  # noqa: E402
from minis_core import control  # noqa: E402
from minis_win import shell  # noqa: E402

MOMENTS = {'beam': ('beam', 0.06), 'flash': ('flash', 0.035), 'air_exchange': ('air', 0.2), 'knockdown': ('knockdown', 0.45)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--monitor', type=int, required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--seconds', type=float, default=45.0)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--fps', type=float, default=12.0)
    ap.add_argument('--prefix', default='v5')
    ap.add_argument('--no-start', action='store_true', help='the arena is already running: only capture')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if not a.no_start:
        msg, rc = minis.start_arena(a.monitor, False, a.seconds, a.seed)
        print(msg)
        if rc:
            return rc
    ring = collections.deque(maxlen=int(a.fps * 3.5))
    wanted = {}                                    # name -> (t_target, saved?)
    seen = set()
    saved = {}
    t0 = time.monotonic()
    hwnd = 0
    last_hb = -1.0
    n_frames = 0
    deadline = t0 + a.seconds + 12.0
    while time.monotonic() < deadline:
        tick = time.monotonic()
        if not hwnd:
            hwnd = shell.find_own_window('MinisArena')
        if hwnd:
            im = shell.capture_window(hwnd)
            if im is None:
                hwnd = 0
            else:
                ring.append((time.monotonic(), im))
                n_frames += 1
        st = control.arena_state()
        if st is None:
            if n_frames and time.monotonic() - t0 > 5.0:
                break                              # the arena left
        else:
            for ev in st.get('events') or []:
                kind, t = ev[0], ev[1]
                key = (kind, round(float(t), 3))
                if key in seen or kind not in MOMENTS:
                    continue
                seen.add(key)
                name, off = MOMENTS[kind]
                if kind == 'beam' and len(ev) > 2 and ev[2]:
                    name = str(ev[2])                      # the file is named after the effect that fired (kamehameha, rasengan_burst ...)
                if name not in saved and name not in wanted:
                    wanted[name] = float(t) + off
        for name, tt in list(wanted.items()):
            if ring and ring[-1][0] >= tt + 0.15:
                after = [fr for fr in ring if fr[0] >= tt]          # a frame before the moment cannot show it: first one at or after
                best = min(after, key=lambda fr: fr[0] - tt) if after else min(ring, key=lambda fr: abs(fr[0] - tt))
                if abs(best[0] - tt) <= 0.6:
                    p = out / f'{a.prefix}-{name}.png'
                    best[1].save(p)
                    saved[name] = (p, round(best[0] - tt, 3))
                    print(f'saved {name}: {p} (frame {best[0] - tt:+.3f} s from the moment)')
                del wanted[name]
        time.sleep(max(0.0, 1.0 / a.fps - (time.monotonic() - tick)))
    if ring:
        p = out / f'{a.prefix}-last.png'
        ring[-1][1].save(p)
        saved['last'] = (p, 0.0)
    missing = [m for m, _ in MOMENTS.values() if m not in saved and m != 'beam'] + ([] if any(k not in ('flash', 'air', 'knockdown', 'last') for k in saved) else ['beam'])
    print(f'frames seen {n_frames}; saved {sorted(saved)}; missing {missing}')
    return 0 if not missing else 1


if __name__ == '__main__':
    sys.exit(main())
