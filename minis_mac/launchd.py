"""Start at login on macOS: a per-user LaunchAgent plist.  Pure (plistlib only), unit-tested on any OS.

Nothing is installed unless the user runs `python minis.py autostart on`; `print-startup` only prints the plist.  The agent
runs `<python> <ROOT>/minis.py start` once at login (RunAtLoad, no KeepAlive).  `start` launches the three roles in their own
sessions and exits; AbandonProcessGroup keeps launchd from reaping them when it does.
"""
from __future__ import annotations
import os, plistlib
from pathlib import Path

LABEL = 'io.github.mrktchris.taskbar-fighters'


def agents_dir(home=None):
    return Path(home or Path.home()) / 'Library' / 'LaunchAgents'


def plist_path(home=None):
    return agents_dir(home) / f'{LABEL}.plist'


def program_arguments(python, root, argv=None):
    """<python> <root>/minis.py start, or `argv` as given (a frozen build: [<executable>, 'start'])."""
    return [str(a) for a in argv] if argv else [str(python), str(Path(root) / 'minis.py'), 'start']


def plist_dict(python, root, argv=None):
    root = Path(root)
    return {
        'Label': LABEL,
        'ProgramArguments': program_arguments(python, root, argv),
        'WorkingDirectory': str(root),
        'RunAtLoad': True,
        'KeepAlive': False,
        'AbandonProcessGroup': True,
        'ProcessType': 'Interactive',
        'StandardOutPath': os.devnull,
        'StandardErrorPath': os.devnull,
    }


def plist_bytes(python, root, argv=None):
    return plistlib.dumps(plist_dict(python, root, argv), fmt=plistlib.FMT_XML, sort_keys=True)


def is_ours(data, root, argv=None):
    """A plist (bytes) is ours when its label is ours and it runs exactly <root>/minis.py start (any python), or exactly
    `argv` when given (a frozen build)."""
    try:
        d = plistlib.loads(data)
    except Exception:
        return False
    args = d.get('ProgramArguments') or []
    if d.get('Label') != LABEL:
        return False
    if argv and not str(argv[-2] if len(argv) > 1 else '').endswith('minis.py'):
        return args == [str(a) for a in argv]
    return len(args) == 3 and args[1:] == [str(Path(root) / 'minis.py'), 'start']


def install(python, root, home=None, argv=None):
    """-> (ok, message).  Writes the plist; refuses to overwrite one that is not ours."""
    p = plist_path(home)
    if p.exists() and not is_ours(p.read_bytes(), root, argv):
        return False, f'{p}: exists and is not ours - left alone'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(plist_bytes(python, root, argv))
    return True, f'wrote {p} (starts Taskbar Fighters at your next login)'


def uninstall(root, home=None, argv=None):
    """-> (ok, message).  Deletes the plist only when it is ours."""
    p = plist_path(home)
    if not p.exists():
        return True, f'{p}: not installed'
    if not is_ours(p.read_bytes(), root, argv):
        return False, f'{p}: not ours - left alone'
    p.unlink()
    return True, f'removed {p}'
