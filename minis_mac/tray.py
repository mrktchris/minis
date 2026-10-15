"""The menu-bar status item (macOS stand-in for the Windows tray icon), hosted by the director process.

minis_win.tray.Tray holds all the logic (tooltip, menu items, choices) and is pure Python; this module is only its `api`:
the same methods the Win32Api has, implemented with NSStatusItem / NSMenu.  Left click opens fighter select, right click
(or Control-click) opens the menu - the same split as Windows.  EXPERIMENTAL: untested on a real Mac.
"""
from __future__ import annotations
import logging

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

    def register_message(self, name):
        return 0                                       # no TaskbarCreated broadcast on macOS

    def create_window(self, handler):
        shell.app()
        self._handler = handler
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(SQUARE)
        if self.item is None:
            raise shell.MacBackendError('could not create the menu-bar status item')
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
        if self.item is None:
            return 0
        m, target = shell.build_menu(items)
        btn = self.item.button()
        shell.activate()
        m.popUpMenuPositioningItem_atLocation_inView_(None, NSMakePoint(0, btn.bounds().size.height + 4), btn)
        return int(getattr(target, 'picked', 0) or 0)

    def pump(self):
        return shell.pump_or_true()

    def destroy_window(self, hwnd):
        if self.item is not None:
            NSStatusBar.systemStatusBar().removeStatusItem_(self.item)
            self.item = None
