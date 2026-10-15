# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Windows standalone bundle (onedir).
#
#   pyinstaller --noconfirm --clean packaging/taskbar_fighters.spec      (run from the repo root)
#
# Output: dist/TaskbarFighters/
#   TaskbarFighters.exe       windowed; double-click = start; same subcommands as `python minis.py`
#   TaskbarFighters-cli.exe   console twin for status / stop / detect / --help with visible output
#   _internal/                Python runtime + minis code + assets/ + assets_hd/ (incl. assets/icon)
#
# Assumes the frozen-path changes listed in docs/PACKAGING.md (ROOT from sys._MEIPASS, child processes re-launch the exe
# instead of `python minis.py`).  Until those land the bundle runs every read-only command but `start` cannot launch
# its child processes.
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

REPO = os.path.abspath(os.path.join(SPECPATH, '..'))
sys.path.insert(0, REPO)

# runtime packages; minis_mac is the macOS backend (pyobjc) and never belongs in the Windows bundle
packages = [p for p in ('minis_core', 'minis_win', 'minis_platform') if os.path.isdir(os.path.join(REPO, p))]
hidden = []
for p in packages:
    hidden += collect_submodules(p)

datas = [(os.path.join(REPO, 'assets'), 'assets')]
if os.path.isdir(os.path.join(REPO, 'assets_hd')):
    datas.append((os.path.join(REPO, 'assets_hd'), 'assets_hd'))

ICON = os.path.join(REPO, 'assets', 'icon', 'minis.ico')

a = Analysis(
    [os.path.join(SPECPATH, 'tf_launcher.py')],
    pathex=[REPO],
    binaries=[],
    datas=datas,
    hiddenimports=['minis'] + hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=['minis_mac', 'tkinter', 'unittest', 'pydoc', 'objc', 'AppKit', 'Quartz', 'Foundation'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe_gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TaskbarFighters',
    icon=ICON,
    console=False,
    upx=False,
)
exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TaskbarFighters-cli',
    icon=ICON,
    console=True,
    upx=False,
)
coll = COLLECT(
    exe_gui,
    exe_cli,
    a.binaries,
    a.datas,
    upx=False,
    name='TaskbarFighters',
)
