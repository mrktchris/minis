"""Entry point of the frozen Windows build (PyInstaller, see packaging/taskbar_fighters.spec).

TaskbarFighters.exe      windowed: double-click = `start` (no arguments), otherwise the same commands as `python minis.py`
TaskbarFighters-cli.exe  console:  `TaskbarFighters-cli.exe status | stop | detect | --help ...` with visible output

Nothing here changes behaviour for `python minis.py`; this file is only the frozen build's front door.
"""
import os
import sys


def _ensure_streams():
    # A windowed (no-console) PyInstaller exe has sys.stdout / sys.stderr = None; anything that writes to them directly
    # (instead of print) would raise.  Point them at the null device.
    for name in ('stdout', 'stderr'):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, 'w', encoding='utf-8'))


def run():
    _ensure_streams()
    import minis
    argv = sys.argv[1:]
    windowed = getattr(sys, 'frozen', False) and not os.path.basename(sys.executable).lower().endswith('-cli.exe')
    if not argv and windowed:
        argv = ['start']                                   # double-click on the windowed exe
    sys.exit(minis.main(argv))


if __name__ == '__main__':
    run()
