"""Self-dump of the composited window images, for docs (tools/own_capture.py).  No screen capture of any kind: each
process writes the images it hands to its own windows, and the tool composites them over a neutral background.

Request: <data_dir>/dump/request.json = {"id": "[A-Za-z0-9_-]{1,32}", "until": wall seconds, "every_ms": int}
(written atomically by the tool, deleted when it is done).  A malformed / expired request is ignored.

Response, while a request is active: <data_dir>/dump/<id>/<role>-<wall_ms>.png (the image exactly as passed to
Overlay.present) + <role>-<wall_ms>.json {role, id, wall, x, y, w, h, scale, density, visible, png}.  x, y: the window's
top-left in screen px after present; w, h: its screen size (image size // density * scale; density is the macOS HUD
image's info['density'], 1 on Windows).  `png` names the image the record shows: a record written because a window was
hidden, shown or moved without a new present reuses the last image.  Roles: a, b, a-plate, b-plate, scoreboard.

Cost with no request: one os.stat of request.json per process at most every 0.5 s.  Writes stay under
<data_dir>/dump/<id>/; nothing here ever raises into the caller or logs.
"""
from __future__ import annotations
import json, os, re, sys, threading, time, weakref
from pathlib import Path

from . import config as cfgmod

ROLES = ('a', 'b', 'a-plate', 'b-plate', 'scoreboard')
ID_RE = re.compile(r'[A-Za-z0-9_-]{1,32}')
CHECK_S = 0.5                      # request.json is stat'ed at most this often per process
MIN_EVERY_MS, MAX_EVERY_MS, DEFAULT_EVERY_MS = 20, 10000, 100
MAX_SPAN_S = 3600.0                # a request claiming to run longer than an hour is ignored (a forgotten file)
AUTO_POLL = os.environ.get('MINIS_TESTING') != '1'   # the poll thread; tests drive poll_once() themselves

_wall = time.time
_mono = time.monotonic
_lock = threading.RLock()
_req_cache = {}                    # root -> [checked_mono, stat signature, request or None]
_watchers = []
_thread = None


def dump_root() -> Path:
    return cfgmod.data_dir() / 'dump'


def request_path(root=None) -> Path:
    return Path(root or dump_root()) / 'request.json'


def parse_request(data, now=None):
    """-> {'id', 'until', 'every_ms'} for a well-formed request still running at `now`, else None."""
    if not isinstance(data, dict):
        return None
    rid = data.get('id')
    if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
        return None
    try:
        until = float(data.get('until'))
        every = int(data.get('every_ms', DEFAULT_EVERY_MS))
    except (TypeError, ValueError):
        return None
    now = _wall() if now is None else now
    if not (now <= until <= now + MAX_SPAN_S):
        return None
    return {'id': rid, 'until': until, 'every_ms': max(MIN_EVERY_MS, min(MAX_EVERY_MS, every))}


def active(root=None, force=False):
    """The active request for this data dir, or None.  Re-reads at most every CHECK_S (force=True: now)."""
    root = Path(root or dump_root())
    key = str(root)
    m = _mono()
    with _lock:
        hit = _req_cache.get(key)
        if hit and not force and m - hit[0] < CHECK_S:
            req = hit[2]
        else:
            p = request_path(root)
            try:
                st = os.stat(p)
                sig = (st.st_mtime_ns, st.st_size, st.st_ctime_ns)
            except OSError:
                sig = None
            if sig is None:
                req = None
            elif hit and hit[1] == sig:
                req = hit[2]
            else:
                try:
                    req = json.loads(p.read_text(encoding='utf-8'))
                except Exception:
                    req = None
            _req_cache[key] = [m, sig, req]
    return parse_request(req) if req is not None else None


def safe_dir(root, rid):
    """<root>/<rid>, resolved and checked to sit directly under <root>; None for anything else."""
    if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
        return None
    try:
        base = Path(root).resolve()
        d = (base / rid).resolve()
    except (OSError, RuntimeError):
        return None
    return d if d.parent == base else None


class _Watcher:
    def __init__(self, overlay, role, root):
        try:
            self.ref = weakref.ref(overlay)
        except TypeError:
            self.ref = lambda o=overlay: o
        self.role, self.root = role, Path(root)
        self.img = None            # the last image presented (a reference, never a copy)
        self.png = None            # file name of the last image written for the current request
        self.req_id = None
        self.last_ms = 0           # wall ms of the last record written
        self.last_img_ms = -10 ** 15
        self.seen = None           # (x, y, visible) of the last record

    def state(self, ov):
        return (int(getattr(ov, 'x', 0) or 0), int(getattr(ov, 'y', 0) or 0), bool(getattr(ov, 'visible', True)))

    def write(self, req, ov, with_image):
        """One record (png + json, or json only reusing the last png).  Caller holds _lock."""
        d = safe_dir(self.root, req['id'])
        if d is None or self.img is None:
            return False
        if self.req_id != req['id']:
            self.req_id, self.png, self.last_ms, self.last_img_ms = req['id'], None, 0, -10 ** 15
        if self.png is None:
            with_image = True
        wall = _wall()
        ms = max(int(wall * 1000), self.last_ms + 1)
        d.mkdir(parents=True, exist_ok=True)
        stem = f'{self.role}-{ms}'
        img = self.img
        if with_image:
            img.save(d / f'{stem}.png', compress_level=1)
            self.png, self.last_img_ms = f'{stem}.png', ms
        dens = 1
        if sys.platform == 'darwin':           # only the macOS shell draws a density-k image at 1/k size
            try:
                dens = max(1, int(getattr(img, 'info', {}).get('density', 1)))
            except (TypeError, ValueError):
                dens = 1
        scale = max(1, int(getattr(ov, 'scale', 1) or 1))
        x, y, vis = self.state(ov)
        rec = {'role': self.role, 'id': req['id'], 'wall': ms / 1000.0, 'x': x, 'y': y,
               'w': (img.width // dens) * scale, 'h': (img.height // dens) * scale, 'scale': scale, 'density': dens,
               'visible': vis, 'png': self.png}
        tmp = d / f'.{stem}.json.tmp'
        tmp.write_text(json.dumps(rec, separators=(',', ':')), encoding='utf-8')
        os.replace(tmp, d / f'{stem}.json')
        self.last_ms, self.seen = ms, (x, y, vis)
        return True


def _on_present(w, ov, img):
    w.img = img
    req = active(w.root)
    if req is None:
        return
    with _lock:
        fresh = w.req_id != req['id']
        if fresh or int(_wall() * 1000) - w.last_img_ms >= req['every_ms']:
            w.write(req, ov, with_image=True)


def poll_once():
    """For every live watcher: on a new request, write what its window shows now (a window that only redraws on change
    would otherwise never appear); afterwards a record whenever it is hidden, shown or moved without a present."""
    with _lock:
        live = []
        for w in _watchers:
            ov = w.ref()
            if ov is None:
                continue
            live.append(w)
            try:
                req = active(w.root)
                if req is None or w.img is None:
                    continue
                if w.req_id != req['id']:
                    w.write(req, ov, with_image=True)
                elif w.seen != w.state(ov):
                    w.write(req, ov, with_image=False)
            except Exception:
                pass
        _watchers[:] = live


def _loop():
    while True:
        time.sleep(CHECK_S)
        try:
            poll_once()
        except Exception:
            pass


def _ensure_thread():
    global _thread
    if not AUTO_POLL or (_thread is not None and _thread.is_alive()):
        return
    _thread = threading.Thread(target=_loop, name='minis-dump', daemon=True)
    _thread.start()


def watch(overlay, role):
    """Wrap this overlay instance's present() so it dumps what it shows while a request is active.  Returns the overlay.
    Never raises: a dump that cannot be set up leaves the window exactly as it was."""
    try:
        if overlay is None or role not in ROLES or getattr(overlay, '_dump_watched', False):
            return overlay
        w = _Watcher(overlay, role, dump_root())
        orig = overlay.present

        def present(img, x=None):
            r = orig(img, x)
            try:
                _on_present(w, overlay_ref(), img)
            except Exception:
                pass
            return r

        overlay_ref = w.ref
        overlay.present = present
        overlay._dump_watched = True
        with _lock:
            _watchers.append(w)
        _ensure_thread()
    except Exception:
        pass
    return overlay


def reset():
    """Forget every watcher and cached request (tests)."""
    with _lock:
        _watchers.clear()
        _req_cache.clear()
