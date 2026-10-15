"""Backend selection: which desktop layer this machine uses.

  Windows (sys.platform == 'win32')   minis_win   ctypes Win32 (the original, tested backend)
  macOS   (sys.platform == 'darwin')  minis_mac   PyObjC AppKit + Quartz (EXPERIMENTAL: untested on real hardware)

Nothing here imports a desktop library: `module(part)` imports the backend's module only when it is asked for, so the CLI,
minis_core and the test suite never load ctypes.windll or AppKit at import time.  Every backend module that the rest of the
program uses has the same name in both packages: shell, procs, arena_window, tray.
"""
from __future__ import annotations
import importlib
import sys

PACKAGES = {'win': 'minis_win', 'mac': 'minis_mac'}
PARTS = ('shell', 'procs', 'arena_window', 'tray')


class UnsupportedPlatform(RuntimeError):
    pass


def current(platform: str | None = None) -> str:
    """'win', 'mac' or 'other' for a sys.platform value (default: this machine's)."""
    p = sys.platform if platform is None else platform
    if p == 'win32':
        return 'win'
    if p == 'darwin':
        return 'mac'
    return 'other'


def is_mac() -> bool:
    return current() == 'mac'


def is_windows() -> bool:
    return current() == 'win'


def package(platform: str | None = None) -> str:
    name = current(platform)
    if name not in PACKAGES:
        raise UnsupportedPlatform(f'Taskbar Fighters runs on Windows and (experimentally) macOS, not on {sys.platform if platform is None else platform}')
    return PACKAGES[name]


def module(part: str, platform: str | None = None):
    """The backend's `part` module (shell | procs | arena_window | tray), imported on first use."""
    if part not in PARTS:
        raise ValueError(f'unknown backend part {part!r}')
    return importlib.import_module(f'{package(platform)}.{part}')


def shell():
    return module('shell')


def procs():
    return module('procs')


def label(platform: str | None = None) -> str:
    """Human name of the backend, for `doctor` and `status`."""
    return {'win': 'minis_win (Windows, ctypes Win32)', 'mac': 'minis_mac (macOS, PyObjC AppKit - experimental)'}.get(
        current(platform), 'none (unsupported OS)')
