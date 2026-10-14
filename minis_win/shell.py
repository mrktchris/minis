"""Layered always-on-top window (UpdateLayeredWindow, premultiplied BGRA) + taskbar helpers.
Proven by reference/taskbar_spike.py: windows draw over the Windows 11 taskbar but vanish when the taskbar
re-raises itself, so the owner must call reassert_topmost() every <= 250 ms."""
from __future__ import annotations
import ctypes
from ctypes import wintypes as wt
from PIL import Image, ImageChops

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
shell32 = ctypes.WinDLL('shell32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))      # per-monitor v2
except Exception:
    pass

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [('cbSize', wt.UINT), ('style', wt.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int), ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON), ('hCursor', wt.HANDLE),
                ('hbrBackground', wt.HBRUSH), ('lpszMenuName', wt.LPCWSTR), ('lpszClassName', wt.LPCWSTR), ('hIconSm', wt.HICON)]


class APPBARDATA(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('hWnd', wt.HWND), ('uCallbackMessage', wt.UINT), ('uEdge', wt.UINT),
                ('rc', wt.RECT), ('lParam', wt.LPARAM)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [('BlendOp', ctypes.c_ubyte), ('BlendFlags', ctypes.c_ubyte), ('SourceConstantAlpha', ctypes.c_ubyte), ('AlphaFormat', ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG), ('biPlanes', wt.WORD), ('biBitCount', wt.WORD),
                ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD), ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG),
                ('biClrUsed', wt.DWORD), ('biClrImportant', wt.DWORD)]


user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.CreateWindowExW.restype = wt.HWND
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HDC,
                                       ctypes.POINTER(wt.POINT), wt.COLORREF, ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype = wt.HWND
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [wt.HWND]
user32.SetCapture.argtypes = [wt.HWND]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, ctypes.c_void_p]
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.SetForegroundWindow.argtypes = [wt.HWND]
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFOHEADER), wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE          # a 64-bit handle must not be truncated to a C int
kernel32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE
user32.ReleaseCapture.argtypes = []
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, ctypes.c_void_p]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [wt.HWND, ctypes.c_size_t]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wt.ATOM
shell32.SHAppBarMessage.argtypes = [wt.DWORD, ctypes.POINTER(APPBARDATA)]
shell32.SHAppBarMessage.restype = ctypes.c_size_t

WS_POPUP = 0x80000000
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x8, 0x80, 0x80000, 0x08000000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
HWND_TOPMOST = wt.HWND(-1)
ULW_ALPHA = 2
WM_DESTROY, WM_MOUSEACTIVATE, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP, WM_QUIT, WM_NULL = \
    0x2, 0x21, 0x200, 0x201, 0x202, 0x203, 0x205, 0x12, 0x0
WM_TIMER, WM_CAPTURECHANGED = 0x113, 0x215
WM_NCHITTEST, WM_KEYDOWN, WM_KILLFOCUS = 0x84, 0x100, 0x8
HTTRANSPARENT, HTCLIENT = -1, 1
MA_ACTIVATE, MA_NOACTIVATE = 1, 3
TICK_TIMER_ID = 0x4D49
CS_DBLCLKS = 0x8
CLASS_NAME = 'MinisFighter'

_instances = {}
_class_registered = False
_wndproc_ref = None


def _wndproc(hwnd, msg, wparam, lparam):
    ov = _instances.get(hwnd)
    if msg == WM_MOUSEACTIVATE:
        return MA_ACTIVATE if (ov and ov.activatable) else MA_NOACTIVATE      # fighters never steal focus
    if msg == WM_NCHITTEST and ov and ov.on_hittest:  # solid only where the owner says so (buttons); else click-through
        sx = ctypes.c_short(lparam & 0xFFFF).value
        sy = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        try:
            solid = ov.on_hittest((sx - ov.x) // ov.scale, (sy - ov.y) // ov.scale)
        except Exception:
            solid = False
        return HTCLIENT if solid else HTTRANSPARENT
    if msg == WM_KEYDOWN and ov and ov.on_key:
        try:
            ov.on_key(int(wparam))
        except Exception:
            pass
        return 0
    if msg == WM_CAPTURECHANGED:                         # capture taken away (alt-tab, a menu, another window): the drag is over
        if ov and ov._dragging:
            ov._dragging = False
            if ov.on_event:
                ov.on_event('up', -1, -1)
        return 0
    if msg == WM_TIMER and wparam == TICK_TIMER_ID:     # also delivered inside the modal menu loop
        if ov and ov.on_timer:
            try:
                ov.on_timer()
            except Exception:
                pass
        return 0
    if ov and msg in (WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEMOVE, WM_LBUTTONDBLCLK, WM_RBUTTONUP):
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        kind = {WM_LBUTTONDOWN: 'down', WM_LBUTTONUP: 'up', WM_MOUSEMOVE: 'move', WM_LBUTTONDBLCLK: 'dbl', WM_RBUTTONUP: 'rclick'}[msg]
        if msg == WM_LBUTTONDOWN:
            ov._dragging = True
            user32.SetCapture(hwnd)
        elif msg == WM_LBUTTONUP:
            ov._dragging = False
            user32.ReleaseCapture()
        if ov.on_event:
            ov.on_event(kind, x // ov.scale, y // ov.scale)
        return 0
    if msg == WM_DESTROY:
        _instances.pop(hwnd, None)
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _register():
    global _class_registered, _wndproc_ref
    if _class_registered:
        return
    _wndproc_ref = WNDPROC(_wndproc)
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.style = CS_DBLCLKS
    wc.lpfnWndProc = _wndproc_ref
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = CLASS_NAME
    user32.RegisterClassExW(ctypes.byref(wc))
    _class_registered = True


class Overlay:
    """on_hittest(cx, cy) -> bool makes the window click-through except where it answers True (WM_NCHITTEST).
    activatable=True + on_key(vk) lets a window take focus on a click and read keys (the arena's ESC); fighters never do."""

    def __init__(self, title, x, y, w, h, scale=1, on_event=None, on_timer=None, on_hittest=None, on_key=None, activatable=False):
        _register()
        self.scale, self.on_event, self.on_timer = scale, on_event, on_timer
        self.on_hittest, self.on_key, self.activatable = on_hittest, on_key, bool(activatable)
        self._dragging = False
        self._w = self._h = 0
        self.x, self.y, self.w, self.h = x, y, w * scale, h * scale
        ex = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | (0 if activatable else WS_EX_NOACTIVATE)
        self.hwnd = user32.CreateWindowExW(ex, CLASS_NAME, title, WS_POPUP, x, y, self.w, self.h, None, None,
                                           kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise OSError('CreateWindowExW failed: %d' % ctypes.get_last_error())
        _instances[self.hwnd] = self
        self._dc = self._bmp = self._old = None
        self._bits = ctypes.c_void_p()
        self.visible = True
        user32.ShowWindow(self.hwnd, 4)                     # SW_SHOWNOACTIVATE: a popup window is created hidden

    def _ensure_dib(self, w, h):
        if self._dc and (w, h) == (self._w, self._h):
            return
        self._free()
        sdc = user32.GetDC(None)
        try:
            dc = gdi32.CreateCompatibleDC(sdc)
            if not dc:
                raise OSError('CreateCompatibleDC failed: %d' % ctypes.get_last_error())
            bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            bits = ctypes.c_void_p()
            bmp = gdi32.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
            if not bmp or not bits.value:
                gdi32.DeleteDC(dc)
                raise OSError('CreateDIBSection failed: %d' % ctypes.get_last_error())
        finally:
            user32.ReleaseDC(None, sdc)
        self._dc, self._bmp, self._bits = dc, bmp, bits
        self._old = gdi32.SelectObject(self._dc, self._bmp)
        self._w, self._h = w, h

    def _free(self):
        if self._dc:
            gdi32.SelectObject(self._dc, self._old)
            gdi32.DeleteObject(self._bmp)
            gdi32.DeleteDC(self._dc)
            self._dc = None

    def present(self, img: Image.Image, x=None):
        if x is not None:
            self.x = int(x)
        if self.scale != 1:
            img = img.resize((img.width * self.scale, img.height * self.scale), Image.NEAREST)
        w, h = img.size
        r, g, b, a = img.split()
        pm = Image.merge('RGBA', (ImageChops.multiply(b, a), ImageChops.multiply(g, a), ImageChops.multiply(r, a), a)).tobytes()
        self._ensure_dib(w, h)
        ctypes.memmove(self._bits, pm, len(pm))
        sdc = user32.GetDC(None)
        blend = BLENDFUNCTION(0, 0, 255, 1)
        ok = user32.UpdateLayeredWindow(self.hwnd, sdc, ctypes.byref(wt.POINT(self.x, self.y)), ctypes.byref(wt.SIZE(w, h)),
                                        self._dc, ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA)
        user32.ReleaseDC(None, sdc)
        return bool(ok)

    def reassert_topmost(self):
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def set_scale(self, scale):
        self.scale = max(1, int(scale))

    def start_timer(self, ms):
        """A WM_TIMER tick that keeps running while a modal menu is open (the menu loop dispatches it to on_timer)."""
        return bool(self.hwnd and user32.SetTimer(self.hwnd, TICK_TIMER_ID, int(ms), None))

    def stop_timer(self):
        if self.hwnd:
            user32.KillTimer(self.hwnd, TICK_TIMER_ID)

    def move(self, x, y):
        self.x, self.y = x, y
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)

    def show(self, visible):
        if visible != self.visible:
            user32.ShowWindow(self.hwnd, 4 if visible else 0)      # SW_SHOWNOACTIVATE / SW_HIDE
            self.visible = visible

    def menu(self, items):
        """items: [(id, label)] -> chosen id or 0"""
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        hm = user32.CreatePopupMenu()
        for i, label in items:
            user32.AppendMenuW(hm, 0, i, label)
        user32.SetForegroundWindow(self.hwnd)
        ticking = self.on_timer is not None and self.start_timer(250)          # heartbeat + keep-on-top while the menu is up
        try:
            choice = user32.TrackPopupMenu(hm, 0x0100 | 0x0080, pt.x, pt.y, 0, self.hwnd, None)     # RETURNCMD | NONOTIFY
        finally:
            if ticking:
                self.stop_timer()
            user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
            user32.DestroyMenu(hm)
        return choice

    def pump(self):
        msg = wt.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            if msg.message == WM_QUIT:
                return False
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        return True

    def close(self):
        self.stop_timer()
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        self._free()


# ---------------------------------------------------------------- taskbar + desktop helpers
def taskbar_rect():
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    shell32.SHAppBarMessage(5, ctypes.byref(abd))          # ABM_GETTASKBARPOS
    r = abd.rc
    return r.left, r.top, r.right, r.bottom, abd.uEdge


def taskbar_autohide():
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    return bool(shell32.SHAppBarMessage(4, ctypes.byref(abd)) & 0x1)       # ABM_GETSTATE & ABS_AUTOHIDE


def screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def fullscreen_busy():
    """True while a fullscreen app / game / presentation is up (QUNS_BUSY, D3D fullscreen, presentation)."""
    st = ctypes.c_int()
    try:
        if shell32.SHQueryUserNotificationState(ctypes.byref(st)) == 0:
            return st.value in (2, 3, 4)
    except Exception:
        pass
    return False


def raise_taskbar():
    """What a click on the taskbar does: it re-asserts itself as topmost (used by the self-test)."""
    tray = user32.FindWindowW('Shell_TrayWnd', None)
    if tray:
        user32.SetWindowPos(tray, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    return bool(tray)


def cursor_pos():
    pt = wt.POINT()
    return (pt.x, pt.y) if user32.GetCursorPos(ctypes.byref(pt)) else None


def shift_down():
    return bool(user32.GetKeyState(0x10) & 0x8000)            # VK_SHIFT


def make_mutex(name):
    h = kernel32.CreateMutexW(None, False, name)
    return h, ctypes.get_last_error() == 183              # (handle, already_running)


# ---------------------------------------------------------------- monitors + window rectangles (arena stage)
class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('rcMonitor', wt.RECT), ('rcWork', wt.RECT), ('dwFlags', wt.DWORD)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), MONITORENUMPROC, wt.LPARAM]
user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.GetDesktopWindow.restype = wt.HWND
user32.GetShellWindow.restype = wt.HWND
try:
    dwmapi = ctypes.WinDLL('dwmapi')
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
except OSError:
    dwmapi = None
GWL_EXSTYLE, DWMWA_CLOAKED = -20, 14


def monitors():
    """-> [{'index': 1-based, 'rect': (l, t, r, b), 'work': (l, t, r, b), 'primary': bool}] in enumeration order."""
    out = []

    def cb(hmon, hdc, prc, lp):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r, w = mi.rcMonitor, mi.rcWork
            out.append(dict(index=len(out) + 1, rect=(r.left, r.top, r.right, r.bottom), work=(w.left, w.top, w.right, w.bottom),
                            primary=bool(mi.dwFlags & 1)))
        return True
    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return out


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, buf, 64)
    return buf.value


def _cloaked(hwnd):
    if dwmapi is None:
        return False
    v = wt.DWORD(0)
    try:
        return dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), 4) == 0 and v.value != 0
    except Exception:
        return False


OWN_CLASSES = (CLASS_NAME, 'MinisArena')
SKIP_CLASSES = ('Shell_TrayWnd', 'Shell_SecondaryTrayWnd', 'Progman', 'WorkerW', 'Windows.UI.Core.CoreWindow')


def window_rects(exclude=()):
    """Rectangles of visible top-level windows, top of the z-order first: [(hwnd, l, t, r, b)].  Rectangles only -
    no titles are read, ever.  Our own windows, the shell/taskbar and cloaked (hidden UWP) windows are left out."""
    out = []
    excl = set(int(h) for h in exclude if h)
    shell_win = user32.GetShellWindow()

    def cb(hwnd, lp):
        if int(hwnd) in excl or hwnd == shell_win or not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetAncestor(hwnd, 2) != hwnd:                     # GA_ROOT: only top-level windows
            return True
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex & WS_EX_TOOLWINDOW:
            return True
        cls = _class_name(hwnd)
        if cls in OWN_CLASSES or cls in SKIP_CLASSES or _cloaked(hwnd):
            return True
        r = wt.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)) and r.right > r.left and r.bottom > r.top:
            out.append((int(hwnd), r.left, r.top, r.right, r.bottom))
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def find_own_window(class_name='MinisArena'):
    """hwnd of one of OUR windows by its class name (never by title), or 0."""
    return user32.FindWindowW(class_name, None) or 0


def capture_window(hwnd):
    """PrintWindow(PW_RENDERFULLCONTENT) of ONE window into a PIL image: the window's own pixels, never the desktop."""
    r = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    sdc = user32.GetDC(None)
    dc = gdi32.CreateCompatibleDC(sdc)
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    bmp = gdi32.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    im = None
    try:
        old = gdi32.SelectObject(dc, bmp)
        ok = user32.PrintWindow(hwnd, dc, 2)
        if ok:
            raw = ctypes.string_at(bits, w * h * 4)
            im = Image.frombuffer('RGBA', (w, h), raw, 'raw', 'BGRA', 0, 1).copy()
        gdi32.SelectObject(dc, old)
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(None, sdc)
    return im
