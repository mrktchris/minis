"""Menu specs, platform-neutral.  The same normalisation as minis_win.shell.menu_entries (kept there unchanged for Windows;
tests/test_mac_platform.py proves the two agree), used by the macOS backend to build NSMenus."""
from __future__ import annotations


def menu_entries(items):
    """Normalise a menu spec: -> [('sep',) | ('sub', label, items) | ('item', id, label, opts)].  Pure."""
    out = []
    for it in items or ():
        if it is None or it == '-':
            out.append(('sep',))
        elif len(it) >= 2 and isinstance(it[1], (list, tuple)) and not isinstance(it[0], int):
            out.append(('sub', str(it[0]), list(it[1])))
        else:
            opt = it[2] if len(it) > 2 and isinstance(it[2], dict) else {}
            out.append(('item', int(it[0]), str(it[1]), opt))
    return out
