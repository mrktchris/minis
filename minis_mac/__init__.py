"""macOS backend (EXPERIMENTAL - written on Windows, untested on real Mac hardware until docs/MAC-TESTING.md is run).

Pure modules (importable anywhere, unit-tested on Windows): geometry, procs, launchd.
AppKit modules (import PyObjC; macOS only): shell, tray, arena_window.  Nothing in this __init__ imports AppKit.
"""
