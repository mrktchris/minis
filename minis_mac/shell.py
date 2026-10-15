"""macOS desktop layer (PyObjC AppKit + Quartz): the same surface as minis_win.shell, so minis.py runs unchanged on top.

EXPERIMENTAL.  Written and desk-checked on Windows; it has never run on a Mac.  docs/MAC-TESTING.md lists every call this
module makes that has not been exercised, and the steps that prove or break it.

What it does
- Overlay: one borderless, transparent, non-activating NSPanel per fighter / plate / scoreboard / select popup, at
  NSStatusWindowLevel (above the Dock), on every Space, out of the window cycle.  Frames are PIL RGBA images shown as the
  CGImage contents of a layer-hosting view, scaled with nearest-neighbour filtering (crisp pixel art on Retina).
- Click-through: the window ignores the mouse except over its opaque pixels or where `on_hittest` says so - polled at 30 Hz
  and applied with setIgnoresMouseEvents_ (the stand-in for WM_NCHITTEST).
- run_loop(step): AppKit must own the main thread, so the fighter / director / arena loops are driven by an NSTimer inside
  NSApplication.run() instead of a blocking Python sleep loop.  SIGTERM / SIGINT stop it cleanly (finally blocks run).
- The app is an accessory app (no Dock icon, no menu bar of its own); the director shows a menu-bar status item (tray.py).
- Geometry: the "taskbar" is a strip on top of the Dock (geometry.dock_strip); coordinates are points, top-left origin.
- Reads window BOUNDS only (CGWindowListCopyWindowInfo): never a window name or owner name; Screen Recording is never needed.
"""
from __future__ import annotations
import logging, os, signal, time
from pathlib import Path

try:
    import objc
    import AppKit
    import Foundation
    import Quartz
    from AppKit import NSApplication, NSColor, NSEvent, NSImage, NSMenu, NSMenuItem, NSPanel, NSScreen, NSView
    from Foundation import NSData, NSDate, NSMakePoint, NSMakeRect, NSMakeSize, NSNull, NSObject, NSRunLoop, NSTimer
except ImportError as _e:                                   # pragma: no cover - only on a Mac without PyObjC
    raise ImportError('Taskbar Fighters on macOS needs PyObjC. Run ./scripts/setup_mac.sh, or: '
                      'python3 -m pip install -r requirements-mac.txt   (missing: %s)' % _e) from _e

from PIL import Image, ImageChops

from . import geometry as G
from .procs import make_mutex  # noqa: F401  (same name as minis_win.shell.make_mutex)
from minis_platform.menus import menu_entries

log = logging.getLogger('minis.mac')


def _k(module, name, default):
    """A constant by name with a numeric fallback (PyObjC renamed several between macOS SDKs)."""
    return getattr(module, name, default)


# ---------------------------------------------------------------- constants (numeric fallbacks are the SDK values)
BORDERLESS = _k(AppKit, 'NSWindowStyleMaskBorderless', 0)
NONACTIVATING = _k(AppKit, 'NSWindowStyleMaskNonactivatingPanel', 1 << 7)
BUFFERED = _k(AppKit, 'NSBackingStoreBuffered', 2)
STATUS_LEVEL = _k(AppKit, 'NSStatusWindowLevel', 25)                         # the Dock is at 20
ACCESSORY = _k(AppKit, 'NSApplicationActivationPolicyAccessory', 1)
BEHAVIOR = (_k(AppKit, 'NSWindowCollectionBehaviorCanJoinAllSpaces', 1 << 0)
            | _k(AppKit, 'NSWindowCollectionBehaviorStationary', 1 << 4)
            | _k(AppKit, 'NSWindowCollectionBehaviorIgnoresCycle', 1 << 6)
            | _k(AppKit, 'NSWindowCollectionBehaviorFullScreenAuxiliary', 1 << 8))
SHIFT = _k(AppKit, 'NSEventModifierFlagShift', 1 << 17)
CONTROL = _k(AppKit, 'NSEventModifierFlagControl', 1 << 18)
APP_DEFINED = _k(AppKit, 'NSEventTypeApplicationDefined', 15)
MASK_ANY = _k(AppKit, 'NSEventMaskAny', _k(AppKit, 'NSAnyEventMask', 0xFFFFFFFFFFFFFFFF))
STATE_ON = _k(AppKit, 'NSControlStateValueOn', _k(AppKit, 'NSOnState', 1))
STATE_OFF = _k(AppKit, 'NSControlStateValueOff', _k(AppKit, 'NSOffState', 0))
DEFAULT_MODE = _k(Foundation, 'NSDefaultRunLoopMode', 'kCFRunLoopDefaultMode')
COMMON_MODES = _k(Foundation, 'NSRunLoopCommonModes', 'kCFRunLoopCommonModes')
FILTER_NEAREST = _k(Quartz, 'kCAFilterNearest', 'nearest')
FILTER_LINEAR = _k(Quartz, 'kCAFilterLinear', 'linear')
FADED_ALPHA = 0.18                                     # a fade_on_hover window under the mouse: see-through, click-through
CG_ONSCREEN = _k(Quartz, 'kCGWindowListOptionOnScreenOnly', 1)
CG_NO_DESKTOP = _k(Quartz, 'kCGWindowListExcludeDesktopElements', 16)
CG_NULL_WINDOW = _k(Quartz, 'kCGNullWindowID', 0)
CG_ALL = _k(Quartz, 'kCGWindowListOptionAll', 0)
CG_PREMULT_LAST = _k(Quartz, 'kCGImageAlphaPremultipliedLast', 1)
CG_ORDER_DEFAULT = _k(Quartz, 'kCGBitmapByteOrderDefault', 0)
CG_INTENT_DEFAULT = _k(Quartz, 'kCGRenderingIntentDefault', 0)

from minis_core import paths as _paths  # noqa: E402
ICON_PATH = _paths.icon_path('minis-256.png')
_instances = []
_state = dict(app=None, launched=False, in_run_loop=False)


class MacBackendError(RuntimeError):
    pass


# ---------------------------------------------------------------- the application object
def app():
    """The shared NSApplication as an accessory app: no Dock icon, no bounce, no menu bar of its own (LSUIElement-like)."""
    if _state['app'] is None:
        a = NSApplication.sharedApplication()
        if a is None:
            raise MacBackendError('NSApplication.sharedApplication() returned nothing (is this a GUI login session?)')
        a.setActivationPolicy_(ACCESSORY)
        _state['app'] = a
    return _state['app']


def activate():
    """Bring this (accessory) app forward: menus and the select screen need it to take keyboard input."""
    a = app()
    try:
        a.activateIgnoringOtherApps_(True)
    except Exception:
        try:
            a.activate()
        except Exception:
            pass


def _pyobj_safe(fn, what):
    """Call fn(); never let a Python exception cross into Objective-C (it would abort the process)."""
    try:
        return fn()
    except Exception:
        log.exception('%s failed', what)
        return None


class MinisTicker(NSObject):
    """NSTimer target: tick_ calls the Python callable in `fn` (set after init)."""

    def tick_(self, timer):
        fn = getattr(self, 'fn', None)
        if fn is not None:
            try:
                fn()
            except BaseException:                          # nothing may escape into the run loop
                log.exception('timer callback failed')


def _ticker(fn):
    t = MinisTicker.alloc().init()
    t.fn = fn
    return t


def _timer(ticker, seconds, repeats):
    """An NSTimer in the common modes (so it also fires while a menu is tracking)."""
    t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(float(seconds), ticker, 'tick:', None, bool(repeats))
    NSRunLoop.currentRunLoop().addTimer_forMode_(t, COMMON_MODES)
    return t


def pump_events(timeout=0.0):
    """Outside run_loop (doctor, selftest): handle pending AppKit events for up to `timeout` seconds."""
    a = app()
    if not _state['launched']:
        a.finishLaunching()
        _state['launched'] = True
    until = NSDate.dateWithTimeIntervalSinceNow_(float(timeout))
    while True:
        ev = a.nextEventMatchingMask_untilDate_inMode_dequeue_(MASK_ANY, until, DEFAULT_MODE, True)
        if ev is None:
            break
        a.sendEvent_(ev)
        until = NSDate.distantPast()
    a.updateWindows()
    update_hover()
    return True


def spin(seconds):
    """Keep the windows alive and drawn for `seconds` without a run loop (doctor, selftest)."""
    end = time.monotonic() + float(seconds)
    while time.monotonic() < end:
        pump_events(min(0.05, max(0.0, end - time.monotonic())))


def run_loop(step, log_=None, hover_hz=30.0):
    """Drive `step()` (-> seconds until the next call, or None to quit) from an NSTimer inside NSApplication.run(), on the
    main thread.  A 30 Hz timer keeps the click-through state current.  SIGTERM / SIGINT end the loop at the next tick."""
    lg = log_ or log
    a = app()
    st = dict(stop=False, exc=None)

    def on_signal(signum, frame):
        st['stop'] = True
    old = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            old[sig] = signal.signal(sig, on_signal)
        except (ValueError, OSError):
            pass
    holder = {}

    def finish():
        a.stop_(None)
        ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            APP_DEFINED, NSMakePoint(0, 0), 0, 0.0, 0, None, 0, 0, 0)
        if ev is not None:
            a.postEvent_atStart_(ev, True)              # stop_ takes effect after the next event: wake run() up

    def tick():
        if st['stop']:
            finish()
            return
        try:
            dt = step()
        except Exception:
            lg.exception('loop step failed')
            dt = 0.25
        except BaseException as e:                       # SystemExit / KeyboardInterrupt from inside the step
            st['exc'] = e
            finish()
            return
        if dt is None or st['stop']:
            finish()
            return
        holder['t'] = _timer(holder['ticker'], max(0.005, float(dt)), False)

    holder['ticker'] = _ticker(tick)
    hover = _timer(_ticker(update_hover), 1.0 / hover_hz, True)
    holder['t'] = _timer(holder['ticker'], 0.0, False)
    _state['in_run_loop'] = True
    try:
        a.run()
    finally:
        _state['in_run_loop'] = False
        hover.invalidate()
        t = holder.get('t')
        if t is not None:
            t.invalidate()
        for sig, h in old.items():
            try:
                signal.signal(sig, h)
            except (ValueError, OSError):
                pass
    if st['exc'] is not None:
        raise st['exc']
    return 0


# ---------------------------------------------------------------- screens
def _frame(r):
    return (float(r.origin.x), float(r.origin.y), float(r.size.width), float(r.size.height))


def _screens():
    ss = NSScreen.screens()
    if ss is None or len(ss) == 0:
        raise MacBackendError('no screens reported by NSScreen.screens()')
    return list(ss)


def primary_h():
    return _frame(_screens()[0].frame())[3]


def dock_info():
    """geometry.dock_strip() for the menu-bar screen: rect, edge, dock side, dock top."""
    s = _screens()[0]
    f = _frame(s.frame())
    return G.dock_strip(f, _frame(s.visibleFrame()), primary_h=f[3])


def taskbar_rect():
    """(l, t, r, b, edge) of the virtual taskbar band: a strip on top of the Dock (edge 3 = bottom, always)."""
    d = dock_info()
    return tuple(d['rect']) + (d['edge'],)


def taskbar_autohide():
    return False                                      # an auto-hiding Dock falls back to the visible frame's bottom


def hud_density():
    """The menu-bar screen's backing scale (2 on Retina): the HUD (plates, scoreboard) is drawn that many times finer."""
    try:
        return max(1, min(3, int(round(float(_screens()[0].backingScaleFactor())))))
    except Exception:
        return 1


def screen_size():
    f = _frame(_screens()[0].frame())
    return int(f[2]), int(f[3])


def monitors():
    return G.monitors_from_frames([(_frame(s.frame()), _frame(s.visibleFrame()), float(s.backingScaleFactor())) for s in _screens()])


def _cg_windows():
    infos = Quartz.CGWindowListCopyWindowInfo(CG_ONSCREEN | CG_NO_DESKTOP, CG_NULL_WINDOW)
    return list(infos or ())


def _notch_left(s):
    """Cocoa x where the camera notch starts on screen `s` (macOS 12+ auxiliaryTopLeftArea), or None without a notch."""
    try:
        if float(s.safeAreaInsets().top) <= 0:
            return None
        r = s.auxiliaryTopLeftArea()
        return float(r.origin.x + r.size.width) if r is not None and r.size.width > 0 else None
    except Exception:
        return None


def menubar_plate_origin(slot, w, h, gap):
    """(x, y) of a HUD plate placed in the menu bar of the menu-bar screen (see geometry.menubar_plate_origin)."""
    s = _screens()[0]
    return G.menubar_plate_origin(slot, _frame(s.frame()), _frame(s.visibleFrame()), _notch_left(s), w, h, gap)


def menubar_icon_shown(pid):
    """geometry.status_item_shown for process `pid` (the director): True, False (hidden by macOS) or None (unknown)."""
    try:
        return G.status_item_shown(list(Quartz.CGWindowListCopyWindowInfo(CG_ALL, CG_NULL_WINDOW) or ()), pid)
    except Exception:
        return None


def window_rects(exclude=()):
    """Rectangles of other apps' normal windows, front to back: [(number, l, t, r, b)].  Bounds only, never a title."""
    try:
        return G.platforms_from_cg(_cg_windows(), os.getpid(), exclude)
    except Exception:
        log.exception('window list failed')
        return []


def fullscreen_busy():
    try:
        w, h = screen_size()
        return G.fullscreen_from_cg(_cg_windows(), os.getpid(), (0, 0, w, h))
    except Exception:
        return False


def raise_taskbar():
    return False                                       # nothing to raise on a Mac (the Dock never covers our level)


def cursor_pos():
    try:
        p = NSEvent.mouseLocation()
        return G.point_to_app(p.x, p.y, primary_h())
    except Exception:
        return None


def shift_down():
    try:
        return bool(NSEvent.modifierFlags() & SHIFT)
    except Exception:
        return False


def find_own_window(class_name='MinisArena'):
    return 0                                           # `arena capture` is Windows-only (it would need Screen Recording here)


def capture_window(hwnd):
    return None


# ---------------------------------------------------------------- icons + tray
def load_icon(path=None, size=18):
    p = Path(path) if path else ICON_PATH
    if not p.exists():
        return None
    img = NSImage.alloc().initWithContentsOfFile_(str(p))
    if img is None:
        return None
    img.setSize_(NSMakeSize(float(size), float(size)))
    return img


def make_tray(tip, flags, on_choice, on_left, log=None, icon_path=None):
    """The director's menu-bar status item: minis_win.tray.Tray (pure logic) over minis_mac.tray.MacTrayApi."""
    from minis_win.tray import Tray
    from .tray import MacTrayApi
    t = Tray(MacTrayApi(), str(icon_path or ICON_PATH), tip, flags, on_choice, on_left, log=log)
    t.create()
    return t


# ---------------------------------------------------------------- images
def cgimage(img):
    """PIL image -> CGImage (premultiplied RGBA, 8 bits per channel)."""
    img = img.convert('RGBA')
    r, g, b, a = img.split()
    data = Image.merge('RGBA', (ImageChops.multiply(r, a), ImageChops.multiply(g, a), ImageChops.multiply(b, a), a)).tobytes()
    w, h = img.size
    provider = Quartz.CGDataProviderCreateWithCFData(NSData.dataWithBytes_length_(data, len(data)))
    space = Quartz.CGColorSpaceCreateDeviceRGB()
    return Quartz.CGImageCreate(w, h, 8, 32, 4 * w, space, CG_PREMULT_LAST | CG_ORDER_DEFAULT, provider, None, False, CG_INTENT_DEFAULT)


def _no_actions():
    n = NSNull.null()
    return {'contents': n, 'bounds': n, 'position': n, 'frame': n, 'hidden': n, 'opacity': n}


def new_layer():
    lay = Quartz.CALayer.layer()
    lay.setActions_(_no_actions())
    lay.setMagnificationFilter_(FILTER_NEAREST)
    lay.setMinificationFilter_(FILTER_NEAREST)
    return lay


def _no_anim(fn):
    Quartz.CATransaction.begin()
    Quartz.CATransaction.setDisableActions_(True)
    try:
        fn()
    finally:
        Quartz.CATransaction.commit()


# ---------------------------------------------------------------- menus
class MinisMenuTarget(NSObject):
    def menuPick_(self, sender):
        self.picked = int(sender.tag())


def build_menu(items, target=None):
    """-> (NSMenu, target).  target.picked holds the chosen id after the menu closes (0 = nothing)."""
    if target is None:
        target = MinisMenuTarget.alloc().init()
        target.picked = 0
    m = NSMenu.alloc().initWithTitle_('')
    m.setAutoenablesItems_(False)
    for e in menu_entries(items):
        if e[0] == 'sep':
            m.addItem_(NSMenuItem.separatorItem())
        elif e[0] == 'sub':
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(e[1], None, '')
            sub, _ = build_menu(e[2], target)
            it.setSubmenu_(sub)
            m.addItem_(it)
        else:
            _, mid, label, opt = e
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, 'menuPick:', '')
            it.setTarget_(target)
            it.setTag_(int(mid))
            it.setEnabled_(not opt.get('disabled'))
            it.setState_(STATE_ON if opt.get('checked') else STATE_OFF)
            m.addItem_(it)
    return m, target


# ---------------------------------------------------------------- windows
class MinisPanel(NSPanel):
    """Borderless panel; becomes key only when its Overlay is activatable (the select screen, the arena's ESC)."""

    def canBecomeKeyWindow(self):
        o = getattr(self, 'minis_owner', None)
        return bool(o is not None and o.activatable)

    def canBecomeMainWindow(self):
        return False

    def resignKeyWindow(self):
        objc.super(MinisPanel, self).resignKeyWindow()
        o = getattr(self, 'minis_owner', None)
        if o is not None and o.on_blur is not None:
            _pyobj_safe(o.on_blur, 'on_blur')


class MinisView(NSView):
    """Content view: mouse and keys to the Overlay's callbacks in logical (sprite) pixels, top-left origin."""

    def acceptsFirstMouse_(self, event):
        return True

    def acceptsFirstResponder(self):
        return True

    def isOpaque(self):
        return False

    @objc.python_method                                # a Python helper, not an Objective-C selector
    def _send(self, kind, event):
        o = getattr(self, 'minis_owner', None)
        if o is not None:
            _pyobj_safe(lambda: o._mouse(kind, event, self), 'mouse ' + kind)

    def mouseDown_(self, event):
        self._send('dbl' if event.clickCount() == 2 else 'down', event)

    def mouseUp_(self, event):
        self._send('up', event)

    def mouseDragged_(self, event):
        self._send('move', event)

    def mouseMoved_(self, event):
        self._send('move', event)

    def rightMouseDown_(self, event):
        pass                                           # the menu opens on the release, like Windows WM_RBUTTONUP

    def rightMouseUp_(self, event):
        self._send('rclick', event)

    def scrollWheel_(self, event):
        o = getattr(self, 'minis_owner', None)
        if o is not None and o.on_event is not None:
            dy = event.scrollingDeltaY()
            if dy:
                _pyobj_safe(lambda: o.on_event('wheel', 120 if dy > 0 else -120, 0), 'wheel')

    def keyDown_(self, event):
        o = getattr(self, 'minis_owner', None)
        vk = G.vk_from_mac(event.keyCode())
        if o is not None and o.on_key is not None and vk is not None:
            _pyobj_safe(lambda: o.on_key(vk), 'key')


class Overlay:
    """Same interface as minis_win.shell.Overlay: x, y (points, top-left), w, h (points), scale, visible; present, move,
    show, reassert_topmost, set_scale, start_timer, stop_timer, focus, menu, pump, close."""

    def __init__(self, title, x, y, w, h, scale=1, on_event=None, on_timer=None, on_hittest=None, on_key=None, activatable=False,
                 on_blur=None):
        app()
        self.scale, self.on_event, self.on_timer = max(1, int(scale)), on_event, on_timer
        self.on_hittest, self.on_key, self.activatable, self.on_blur = on_hittest, on_key, bool(activatable), on_blur
        self._dragging = False
        self._alpha = None
        self._ignoring = None
        self.fade_on_hover = False                     # plates: fade and let clicks through while the mouse is over them
        self._faded = False
        self._timer = None
        self._closed = False
        self.x, self.y, self.w, self.h = int(x), int(y), int(w) * self.scale, int(h) * self.scale
        style = BORDERLESS | (0 if activatable else NONACTIVATING)
        ox, oy = G.to_cocoa_origin(self.x, self.y, self.h, primary_h())
        p = MinisPanel.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(ox, oy, self.w, self.h), style, BUFFERED, False)
        if p is None:
            raise MacBackendError('could not create an NSPanel')
        p.minis_owner = self
        p.setTitle_(str(title))
        p.setOpaque_(False)
        p.setBackgroundColor_(NSColor.clearColor())
        p.setHasShadow_(False)
        p.setFloatingPanel_(True)                        # before setLevel_: it resets the level to NSFloatingWindowLevel (3)
        p.setLevel_(STATUS_LEVEL + (1 if activatable else 0))
        p.setCollectionBehavior_(BEHAVIOR)
        p.setHidesOnDeactivate_(False)                   # NSPanel hides when its app deactivates - ours never is active
        p.setReleasedWhenClosed_(False)
        p.setAcceptsMouseMovedEvents_(True)
        v = MinisView.alloc().initWithFrame_(NSMakeRect(0, 0, self.w, self.h))
        v.minis_owner = self
        self.layer = new_layer()
        self.layer.setFrame_(NSMakeRect(0, 0, self.w, self.h))
        v.setLayer_(self.layer)                          # layer-hosting view: we own the layer and its contents
        v.setWantsLayer_(True)
        p.setContentView_(v)
        p.makeFirstResponder_(v)
        self.panel, self.view = p, v
        self.visible = False
        _instances.append(self)
        self.show(True)                                  # like Windows: created visible (callers hide it at once)

    @property
    def hwnd(self):
        try:
            return int(self.panel.windowNumber())
        except Exception:
            return 0

    def _mouse(self, kind, event, view):
        pt = view.convertPoint_fromView_(event.locationInWindow(), None)
        lx = int(pt.x) // self.scale
        ly = int(self.h - pt.y) // self.scale               # view is not flipped: y from the top
        if kind in ('down', 'dbl'):
            self._dragging = True
        elif kind == 'up':
            self._dragging = False
        if self.on_event is not None:
            self.on_event(kind, lx, ly)

    def _set_frame(self):
        ox, oy = G.to_cocoa_origin(self.x, self.y, self.h, primary_h())
        self.panel.setFrame_display_(NSMakeRect(ox, oy, self.w, self.h), False)
        self.view.setFrame_(NSMakeRect(0, 0, self.w, self.h))
        self.layer.setFrame_(NSMakeRect(0, 0, self.w, self.h))

    def present(self, img, x=None):
        if self._closed:
            return False
        moved = x is not None and int(x) != self.x
        if x is not None:
            self.x = int(x)
        dens = max(1, int(getattr(img, 'info', {}).get('density', 1)))   # a HUD image drawn k times finer (Retina)
        lw, lh = img.width // dens, img.height // dens
        w, h = lw * self.scale, lh * self.scale
        resized = (w, h) != (self.w, self.h)
        self.w, self.h = w, h
        a = img.getchannel('A') if img.mode == 'RGBA' else None
        self._alpha = a.reduce(dens) if a is not None and dens > 1 else a      # hit-testing stays in logical px
        cg = cgimage(img)

        def apply():
            if moved or resized:
                self._set_frame()
            self.layer.setMinificationFilter_(FILTER_LINEAR if dens > 1 else FILTER_NEAREST)   # a 2x HUD on a 1x screen
            self.layer.setContents_(cg)
        _no_anim(apply)
        return True

    def actual_rect(self):
        """The panel's real frame in app coordinates (selftest / doctor)."""
        return G.to_app_rect(_frame(self.panel.frame()), primary_h())

    def update_ignore(self, mouse):
        if self._closed:
            return
        rect = (self.x, self.y, self.x + self.w, self.y + self.h)
        if self._dragging:
            want = False
        else:
            want = not G.window_solid_at(mouse, rect, self.scale, self._alpha, self.on_hittest)
        if want != self._ignoring:
            self.panel.setIgnoresMouseEvents_(want)
            self._ignoring = want
        if self.fade_on_hover:
            fade = bool(want and mouse is not None and rect[0] <= mouse[0] < rect[2] and rect[1] <= mouse[1] < rect[3])
            if fade != self._faded:
                self.panel.setAlphaValue_(FADED_ALPHA if fade else 1.0)
                self._faded = fade

    def reassert_topmost(self):
        if self.visible and not self._closed:
            self.panel.orderFrontRegardless()

    def set_scale(self, scale):
        self.scale = max(1, int(scale))

    def start_timer(self, ms):
        if self.on_timer is None or self._closed:
            return False
        self.stop_timer()
        self._timer = _timer(_ticker(self.on_timer), int(ms) / 1000.0, True)
        return True

    def stop_timer(self):
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None

    def move(self, x, y):
        self.x, self.y = int(x), int(y)
        ox, oy = G.to_cocoa_origin(self.x, self.y, self.h, primary_h())
        self.panel.setFrameOrigin_(NSMakePoint(ox, oy))

    def show(self, visible):
        if visible != self.visible and not self._closed:
            if visible:
                self.panel.orderFrontRegardless()
            else:
                self.panel.orderOut_(None)
            self.visible = visible

    def focus(self):
        if self.activatable and not self._closed:
            activate()
            self.panel.makeKeyAndOrderFront_(None)

    @staticmethod
    def build_menu(items):
        return build_menu(items)

    def menu(self, items):
        """Pop up a menu at the mouse.  -> chosen id or 0.  on_timer keeps ticking while it is open."""
        m, target = build_menu(items)
        ticking = self.on_timer is not None and self.start_timer(250)
        activate()
        try:
            m.popUpMenuPositioningItem_atLocation_inView_(None, NSEvent.mouseLocation(), None)
        finally:
            if ticking:
                self.stop_timer()
        return int(getattr(target, 'picked', 0) or 0)

    def pump(self):
        if self._closed:
            return False
        if not _state['in_run_loop']:
            pump_events(0.0)
        return True

    def close(self):
        self.stop_timer()
        if not self._closed:
            self._closed = True
            try:
                self.panel.orderOut_(None)
                self.panel.close()
            finally:
                if self in _instances:
                    _instances.remove(self)


def update_hover():
    """Click-through: each window takes the mouse only over its opaque pixels / hit-test area."""
    if not _instances:
        return
    m = cursor_pos()
    for ov in list(_instances):
        try:
            ov.update_ignore(m)
        except Exception:
            log.exception('hover update failed')


def pump_or_true():
    if not _state['in_run_loop']:
        pump_events(0.0)
    return True


# ---------------------------------------------------------------- self-checks (doctor / selftest-gui)
def probe_overlay(seconds=1.0):
    """Open a tiny transparent window for `seconds`, then close it.  -> (ok, detail)."""
    ov = Overlay('minis-doctor', 40, 40, 8, 8)
    try:
        ov.present(Image.new('RGBA', (8, 8), (255, 0, 0, 0)))
        spin(seconds)
        vis = bool(ov.panel.isVisible())
        rect = ov.actual_rect()
        return vis, f'NSPanel opened at {rect}, visible={vis}, level={int(ov.panel.level())}'
    finally:
        ov.close()
