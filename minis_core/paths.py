"""Where the code, the art and the user's settings live, for every way Taskbar Fighters can be installed.

  repo checkout   <clone>/assets, <clone>/assets_hd, <clone>/minis.json            (the original layout; unchanged)
  PyInstaller     sys._MEIPASS/assets ...; minis.json next to the frozen executable
  py2app          $RESOURCEPATH (Contents/Resources)/assets ...; minis.json next to the .app
  wheel (PyPI)    the art ships inside the package `taskbar_fighters_assets` (assets/, assets_hd/); there is no
                  minis.json beside site-packages to read, so a wheel install runs on defaults + the CLI toggles

Every lookup goes through this module, so the rest of the program never builds a path from __file__ itself.
Pure: nothing here imports a desktop library.
"""
from __future__ import annotations
import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSET_PACKAGE = 'taskbar_fighters_assets'


def frozen() -> bool:
    """A PyInstaller / py2app build (sys.frozen is set by both)."""
    return bool(getattr(sys, 'frozen', False))


def bundle_root() -> Path:
    """The folder that holds assets/ and assets_hd/ for this install."""
    mei = getattr(sys, '_MEIPASS', None)
    if mei:
        return Path(mei)
    res = os.environ.get('RESOURCEPATH')                  # py2app sets it to <App>.app/Contents/Resources
    if frozen() and res:
        return Path(res)
    if checkout():
        return REPO
    pkg = _package_dir(ASSET_PACKAGE)                     # wheel: site-packages/taskbar_fighters_assets/{assets,assets_hd}
    if pkg is not None and (pkg / 'assets').is_dir():
        return pkg
    return REPO


def checkout() -> bool:
    """Running from a source tree (git clone, sdist, source zip): minis.py with the art and the tests beside it.
    A wheel install puts minis.py in site-packages with neither, so a stray site-packages/assets from some other
    package is never mistaken for ours."""
    return (not frozen() and (REPO / 'minis.py').is_file() and (REPO / 'assets' / 'icon').is_dir()
            and (REPO / 'minis_core').is_dir() and (REPO / 'tests').is_dir())


def _package_dir(name):
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(list(spec.submodule_search_locations)[0])


def assets_dir() -> Path:
    return bundle_root() / 'assets'


def assets_hd_dir() -> Path:
    return bundle_root() / 'assets_hd'


def icon_path(name='minis.ico') -> Path:
    """assets/icon/<name>: minis.ico (Windows), minis-256.png (macOS menu bar)."""
    return assets_dir() / 'icon' / name


def settings_dir() -> Path:
    """Where minis.json is read: next to minis.py in a checkout, next to the executable / the .app when frozen."""
    if frozen():
        exe = Path(sys.executable).resolve()
        for parent in exe.parents:                         # <X>.app/Contents/MacOS/<exe> -> the folder holding X.app
            if parent.suffix == '.app':
                return parent.parent
        return exe.parent
    return REPO                                            # a wheel install: site-packages, where no minis.json lives


def qa_dir():
    """The repo's qa/ folder for previews and captures, or None in an installed build (never write inside a bundle or
    site-packages)."""
    return REPO / 'qa' if checkout() else None
