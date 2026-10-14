"""Throwaway feasibility spike (NOT the product): two separate per-pixel-alpha,
always-on-top, click-through windows over the empty Windows 11 taskbar, plus a
test that they survive the taskbar re-raising itself. Saves evidence PNGs."""
import ctypes, sys, time, json
from ctypes import wintypes as wt
from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageChops, ImageFilter

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
except Exception:
    pass

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uCallbackMessage", wt.UINT),
                ("uEdge", wt.UINT), ("rc", wt.RECT), ("lParam", wt.LPARAM)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU,
                                   wt.HINSTANCE, wt.LPVOID]
user32.CreateWindowExW.restype = wt.HWND
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wt.UINT]
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT),
                                       ctypes.POINTER(wt.SIZE), wt.HDC, ctypes.POINTER(wt.POINT),
                                       wt.COLORREF, ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype = wt.HWND
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.DestroyWindow.argtypes = [wt.HWND]
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFOHEADER), wt.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]

WS_POPUP = 0x80000000
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_LAYERED = 0x8, 0x80, 0x80000
WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = 0x20, 0x08000000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
HWND_TOPMOST = wt.HWND(-1)
ULW_ALPHA = 2


def wndproc(hwnd, msg, wparam, lparam):
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_proc = WNDPROC(wndproc)
hinst = kernel32.GetModuleHandleW(None)
wc = WNDCLASSEXW()
wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
wc.lpfnWndProc = _proc
wc.hInstance = hinst
wc.lpszClassName = "MiniSpike"
user32.RegisterClassExW(ctypes.byref(wc))


def taskbar_rect():
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    shell32.SHAppBarMessage(5, ctypes.byref(abd))  # ABM_GETTASKBARPOS
    r = abd.rc
    return r.left, r.top, r.right, r.bottom, abd.uEdge


def render(label, rgb, w, h):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle((3, 3, w - 4, h - 4), 12, fill=rgb + (150,))
    glow = glow.filter(ImageFilter.GaussianBlur(3))  # soft alpha edge = per-pixel alpha proof
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, w - 7, h - 7), 10, fill=rgb + (255,), outline=(255, 255, 255, 255), width=2)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    d.text((w // 2, h // 2), label, fill=(255, 255, 255, 255), font=font, anchor="mm")
    return img


def present(hwnd, img, x, y):
    w, h = img.size
    r, g, b, a = img.split()
    pm = Image.merge("RGBA", (ImageChops.multiply(b, a), ImageChops.multiply(g, a),
                              ImageChops.multiply(r, a), a))  # premultiplied BGRA
    data = pm.tobytes()
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    ctypes.memmove(bits, data, len(data))
    old = gdi32.SelectObject(mem_dc, hbmp)
    blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
    ok = user32.UpdateLayeredWindow(hwnd, screen_dc, ctypes.byref(wt.POINT(x, y)),
                                    ctypes.byref(wt.SIZE(w, h)), mem_dc, ctypes.byref(wt.POINT(0, 0)),
                                    0, ctypes.byref(blend), ULW_ALPHA)
    gdi32.SelectObject(mem_dc, old)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, screen_dc)
    return bool(ok)


def make(label, rgb, x, y, w, h):
    ex = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
    hwnd = user32.CreateWindowExW(ex, "MiniSpike", label, WS_POPUP, x, y, w, h, None, None, hinst, None)
    ok = present(hwnd, render(label, rgb, w, h), x, y)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    return hwnd, ok


def pump(seconds):
    msg = wt.MSG()
    end = time.time() + seconds
    while time.time() < end:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.02)


out = sys.argv[1]
l, t, r, b, edge = taskbar_rect()
print(json.dumps({"taskbar": [l, t, r, b], "edge": edge, "height": b - t}))
H = b - t
ha, oka = make("CLAUDE", (217, 119, 87), 120, t, 130, H)
hb, okb = make("CODEX", (91, 107, 255), 420, t, 130, H)
print("UpdateLayeredWindow ok:", oka, okb)
tray = user32.FindWindowW("Shell_TrayWnd", None)


def shot(name):
    im = ImageGrab.grab(bbox=(0, t - 4, 900, b), all_screens=False)
    im.save(f"{out}/{name}.png")
    return im


pump(1.0)
s1 = shot("spike1-visible")
# Simulate what a click on the taskbar does: the taskbar re-asserts itself as topmost.
user32.SetWindowPos(tray, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
pump(0.4)
s2 = shot("spike2-after-taskbar-raise")
for h in (ha, hb):  # the product's periodic keep-on-top tick
    user32.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
pump(0.4)
s3 = shot("spike3-after-reassert")
comp = Image.new("RGB", (s1.width, s1.height * 3 + 8), (255, 0, 255))
for i, s in enumerate((s1, s2, s3)):
    comp.paste(s.convert("RGB"), (0, i * (s1.height + 4)))
comp.save(f"{out}/spike-composite.png")
user32.DestroyWindow(ha)
user32.DestroyWindow(hb)
print("done")
