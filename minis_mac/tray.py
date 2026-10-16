"""The menu-bar status item (macOS stand-in for the Windows tray icon), hosted by the director process.

minis_win.tray.Tray holds all the logic (tooltip, menu items, choices) and is pure Python; this module is only its `api`:
the same methods the Win32Api has, implemented with NSStatusItem / NSMenu.  Left click opens fighter select, right click
(or Control-click) opens the menu - the same split as Windows.  EXPERIMENTAL: untested on a real Mac.

Notch fallback (docs/MAC-HANDOFF.md FOUND-3).  An app cannot force its status item's place: macOS lays items out right to
left and hides whatever does not fit (a full menu bar, or the camera notch on a MacBook).  So:
- the item is a compact square icon (no title), and has an autosaveName, so after the user Cmd-drags it to a visible spot
  macOS keeps it there on the next launch;
- every few seconds pump() asks whether macOS shows it (shell.menubar_icon_shown, bounds only).  While it is hidden, a
  small badge with the same icon appears in the free stretch just left of the notch (left of the HUD plates when they sit
  in the menu bar): left click = fighter select, right click = the same menu.  It goes away when the item is visible again;
- and every fighter's own right-click menu carries the same controls.
"""
from __future__ import annotations
import logging, os, time

from AppKit import NSApplication, NSStatusBar
from Foundation import NSMakePoint, NSObject
import AppKit

from minis_win.tray import PRODUCT, WM_LBUTTONUP, WM_RBUTTONUP, WM_TRAY
from . import shell

log = logging.getLogger('minis.mac')
SQUARE = getattr(AppKit, 'NSSquareStatusItemLength', -2.0)
LEFT_UP = getattr(AppKit, 'NSEventMaskLeftMouseUp', 1 << 2)
RIGHT_UP = getattr(AppKit, 'NSEventMaskRightMouseUp', 1 << 4)
RIGHT_UP_TYPE = getattr(AppKit, 'NSEventTypeRightMouseUp', 4)
AUTOSAVE = 'TaskbarFighters'
CHECK_S = 5.0                                           # how often the status item's visibility is checked


class MinisTrayTarget(NSObject):
    def clicked_(self, sender):
        fn = getattr(self, 'fn', None)
        if fn is not None:
            try:
                fn()
            except BaseException:
                log.exception('status item click failed')


class MacTrayApi:
    def __init__(self):
        self.item = None
        self.target = None
        self._handler = None
        self.badge = None                               # the FOUND-3 fallback panel while macOS hides the item
        self._icon_path = None
        self._next_check = time.monotonic() + 2.0

    def register_message(self, name):
        return 0                                       # no TaskbarCreated broadcast on macOS

    def create_window(self, handler):
        shell.app()
        self._handler = handler
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(SQUARE)
        if self.item is None:
            raise shell.MacBackendError('could not create the menu-bar status item')
        try:
            self.item.setAutosaveName_(AUTOSAVE)        # a Cmd-drag to a visible spot is remembered by macOS
        except Exception:
            pass
        btn = self.item.button()
        self.target = MinisTrayTarget.alloc().init()
        self.target.fn = self._clicked
        btn.setTarget_(self.target)
        btn.setAction_('clicked:')
        btn.sendActionOn_(LEFT_UP | RIGHT_UP)
        return 1                                       # a non-None handle (Tray only checks it is set)

    def _clicked(self):
        ev = NSApplication.sharedApplication().currentEvent()
        right = ev is not None and (ev.type() == RIGHT_UP_TYPE or bool(ev.modifierFlags() & shell.CONTROL))
        self._handler(WM_TRAY, 0, WM_RBUTTONUP if right else WM_LBUTTONUP)

    def small_icon_size(self, hwnd):
        return 18                                      # menu-bar icons are 18 pt

    def load_icon(self, path, size):
        self._icon_path = path
        return shell.load_icon(path, size)

    def destroy_icon(self, hicon):
        pass

    def notify(self, action, hwnd, uid, cbmsg, hicon, tip):
        if self.item is None:
            return False
        if action == 'delete':
            NSStatusBar.systemStatusBar().removeStatusItem_(self.item)
            self.item = None
            return True
        btn = self.item.button()
        if hicon is not None:
            btn.setImage_(hicon)
        else:
            btn.setTitle_('TF')
        btn.setToolTip_(tip or PRODUCT)
        return True

    def menu(self, hwnd, items):
        if self.badge is not None and self.badge.visible:
            return self.badge.menu(items)               # the item is hidden: the menu opens at the badge (the mouse)
        if self.item is None:
            return 0
        m, target = shell.build_menu(items)
        btn = self.item.button()
        shell.activate()
        m.popUpMenuPositioningItem_atLocation_inView_(None, NSMakePoint(0, btn.bounds().size.height + 4), btn)
        return int(getattr(target, 'picked', 0) or 0)

    def pump(self):
        now = time.monotonic()
        if self.item is not None and now >= self._next_check:
            self._next_check = now + CHECK_S
            try:
                self.update_badge(shell.menubar_icon_shown(os.getpid()))
            except Exception:
                log.exception('menu-bar badge check failed')
        return shell.pump_or_true()

    def update_badge(self, shown):
        """shown False (macOS hides the item): show the fallback badge; True: remove it; None (unknown): leave it."""
        if shown is False and self.badge is None:
            self.badge = self._make_badge()
            if self.badge is not None:
                log.info('menu-bar icon hidden by macOS: fallback badge shown left of the notch')
        elif shown and self.badge is not None:
            self.badge.close()
            self.badge = None

    def _make_badge(self):
        from PIL import Image, ImageDraw
        from minis_core import config as cfgmod, control
        from . import geometry as G
        s0 = shell._screens()[0]
        f, v = shell._frame(s0.frame()), shell._frame(s0.visibleFrame())
        x, y = G.menubar_badge_origin(f, v, shell._notch_left(s0), control.hud_position() == 'menubar', cfgmod.PLATE_W, cfgmod.PLATE_H,
                                      cfgmod.PLATE_SPACING)
        k = shell.hud_density()
        n = G.BADGE * k
        img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle([0, 0, n - 1, n - 1], 5 * k, fill=(24, 22, 30, 220))
        try:
            icon = Image.open(str(self._icon_path or shell.ICON_PATH)).convert('RGBA').resize((n - 4 * k, n - 4 * k), Image.LANCZOS)
            img.alpha_composite(icon, (2 * k, 2 * k))
        except Exception:
            ImageDraw.Draw(img).text((4 * k, 4 * k), 'TF', fill=(255, 236, 120, 255))
        img.info['density'] = k

        def on_event(kind, lx, ly):
            if kind == 'down':
                self._handler(WM_TRAY, 0, WM_LBUTTONUP)
            elif kind == 'rclick':
                self._handler(WM_TRAY, 0, WM_RBUTTONUP)
        ov = shell.Overlay('minis-menubar-badge', x, y, G.BADGE, G.BADGE, scale=1, on_event=on_event, on_hittest=lambda px, py: True)
        ov.present(img)
        return ov

    def destroy_window(self, hwnd):
        if self.badge is not None:
            self.badge.close()
            self.badge = None
        if self.item is not None:
            NSStatusBar.systemStatusBar().removeStatusItem_(self.item)
            self.item = None
