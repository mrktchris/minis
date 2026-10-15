# Testing Taskbar Fighters on a Mac

The macOS port is **experimental**. It was written and unit-tested on Windows with fakes; until someone runs this checklist on
a real Mac, nothing in it has drawn a window on macOS. This page is the checklist for that first run, written so that a Mac
owner, or their AI coding agent, can follow it top to bottom and send the results back.

## What you need

- macOS 13 (Ventura) or newer, Apple silicon or Intel.
- Python 3.12 or newer. The `python3` that comes with macOS or Xcode is too old. Get one from
  <https://www.python.org/downloads/macos/> or with `brew install python@3.12`.
- About 100 MB free for `.venv` (Pillow and PyObjC).

You do **not** need Accessibility, Screen Recording, Input Monitoring or an administrator password. If macOS asks you for any of
them, decline and report it: that is a bug.

## 1. Install and run

```
git clone https://github.com/mrktchris/taskbar-fighters
cd taskbar-fighters
./scripts/setup_mac.sh
```

The script checks your macOS version and chip, finds Python 3.12+, creates `.venv` inside the clone, installs
`requirements-mac.txt`, runs `python minis.py doctor` and then `python minis.py start`. It is safe to run again. Use
`./scripts/setup_mac.sh --no-start` to stop before `start`.

If `./scripts/setup_mac.sh` says "permission denied", run `bash scripts/setup_mac.sh` instead.

To do the same steps by hand:

```
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-mac.txt
.venv/bin/python minis.py doctor
.venv/bin/python minis.py start
```

## 2. What you should see

1. **The doctor** prints the macOS version, chip, Python, Pillow and PyObjC versions, the screen size and Retina scale, where
   it thinks the Dock is (`dock: bottom`, `left`, `right` or `hidden`), the strip the fighters use, the data folder
   (`~/Library/Application Support/minis`), the AI programs it sees, and a test window line. It ends with `PASS` or `FAIL`.
   The test window is a tiny transparent panel that opens for one second; you will not see it.
2. **After `start`**, within about 3 seconds:
   - two pixel fighters stand on the top edge of the Dock (Dock at the bottom), or at the bottom of the screen (Dock on the
     side or auto-hiding). They are 128 px tall by default; `python minis.py size 64` makes them small again.
   - two small HUD plates sit at the left end of the strip and the scoreboard at the right end. On a Retina screen both
     are drawn at 2x (sharp text) and nearly opaque, since they float over app windows rather than a taskbar. Move the
     mouse over a plate and it fades and lets clicks through to the window under it.
   - a Taskbar Fighters icon in the menu bar. Left-click it: the fighter-select screen. Right-click (or Control-click): the
     menu (Pause, Flash effects, Plates, Rival mode, arena, Bout now, Restart, Quit).
     macOS hides menu-bar icons that do not fit: on a MacBook with a notch and a busy menu bar the icon can sit behind the
     notch. `python minis.py status` then prints `menu-bar icon: hidden by macOS`. Right-click a fighter for the same
     controls, or Cmd-drag a few other icons out of the menu bar and restart.
   - no new icon in the Dock, and no app menu bar: it runs as a background (accessory) app.
3. **Clicks:** clicking the empty space around a fighter goes to whatever is behind it. Clicking on a fighter grabs it (drag it
   along the strip); right-click on a fighter opens its menu; double-click plays a victory pose.
4. `python minis.py demo match` starts a best-of-3 match right away.

## 3. Checks to run and send back

Run these from the clone folder (prefix `.venv/bin/` to `python` if the venv is not activated) and paste all the output:

```
.venv/bin/python minis.py doctor
.venv/bin/python minis.py status
.venv/bin/python minis.py monitors
.venv/bin/python minis.py detect
.venv/bin/python minis.py selftest-gui
.venv/bin/python -m unittest discover -s tests
```

- `selftest-gui` shows two fighters at the Dock for 5 seconds (beside any running ones) and prints, for each, the frame it
  asked for and the frame macOS gave it, and `PASS` or `FAIL`. It takes no screenshot.
- The unit tests should end with `OK`; on a Mac two extra tests run that open a real window for half a second.
- The doctor output shows your home folder as `~` and contains no window titles. Check it before pasting anyway.

Then tell your agent, or write in an issue at <https://github.com/mrktchris/taskbar-fighters/issues>:

| question | answer |
| --- | --- |
| Did the fighters appear? Where (on the Dock, floating, at the bottom, off-screen)? | |
| Are they crisp or blurry on your Retina screen? | |
| Can you click things behind and next to them? Can you drag a fighter? | |
| Does right-click on a fighter open a menu, and does a choice work? | |
| Menu-bar icon: visible? Left click opens fighter select? Right click opens the menu? | |
| Do they follow you to other Spaces and stay above full-screen apps' Dock? | |
| Did macOS ask for any permission? | |
| CPU in Activity Monitor for the three `Python` processes while idle and during a match | |

## 4. Stop and uninstall

```
.venv/bin/python minis.py stop
```

`stop` ends only the three processes it started (it checks each one's pid file and exact command line, sends SIGTERM, and
SIGKILL only if the same process is still running after 3 seconds). The menu-bar Quit item does the same.

To remove everything: run `stop`, then `.venv/bin/python minis.py autostart off` if you turned on start-at-login, delete the
clone folder (which holds `.venv`) and delete `~/Library/Application Support/minis`.

## 5. Optional

- **Start at login:** `.venv/bin/python minis.py autostart on` writes one file,
  `~/Library/LaunchAgents/io.github.mrktchris.taskbar-fighters.plist`, that runs `minis.py start` at your next login.
  `python minis.py print-startup` shows the file without writing it. `autostart off` deletes it (only if it is ours).
- **Arena:** `python minis.py arena --monitor 1 --seconds 30`. `--freeze` is not available on macOS (it would need Screen
  Recording). `arena capture` is Windows-only for the same reason.

## What differs from Windows

| | Windows | macOS |
| --- | --- | --- |
| where the fighters stand | inside the taskbar | on the Dock's top edge (or the bottom of the screen) |
| tray icon | notification area | menu-bar status item |
| start at login | `print-startup` (schtasks) | `autostart on` (LaunchAgent) |
| Start-menu shortcut | `shortcut` | none (`shortcut` explains the alternatives) |
| arena `--freeze`, `arena capture` | yes | no (no screen capture, ever) |
| data folder | `%LOCALAPPDATA%\minis` | `~/Library/Application Support/minis` |
| process list | ctypes (Toolhelp) | `/bin/ps` |
| `stop` | taskkill after an argv check | SIGTERM, then SIGKILL only if still ours |
| `selftest-gui` | taskbar-row difference masks | window frames, no capture |

## Known risks (desk-checked, not run)

These calls were checked against the PyObjC / AppKit API by reading, not by running. If something breaks, it is most likely
one of these; the file and function are named so an agent can go straight there.

1. **Run loop** (`minis_mac/shell.py`, `run_loop`): each process runs `NSApplication.run()` and calls its loop body from a
   one-shot `NSTimer` in `NSRunLoopCommonModes`. Stopping posts an `NSEventTypeApplicationDefined` event after `stop_`. If a
   process does not quit on `stop`, the wake-up event is the suspect.
2. **Python attributes on PyObjC objects**: `MinisPanel.minis_owner`, `MinisView.minis_owner`, `MinisTicker.fn`,
   `MinisMenuTarget.picked` are plain Python attributes set on instances of Python subclasses of NSObject. PyObjC allows
   this; if it raises `AttributeError`, switch them to `objc.ivar()`.
3. **Layer-hosting view** (`Overlay.__init__`): `view.setLayer_(CALayer)` then `setWantsLayer_(True)`; frames are set as
   `layer.setContents_(CGImage)` with `kCAFilterNearest`. Implicit animations are disabled with an actions dictionary of
   `NSNull` and a `CATransaction`. If fighters fade between frames or look blurry, look here.
4. **CGImage creation** (`cgimage`): `CGDataProviderCreateWithCFData(NSData)` and
   `CGImageCreate(..., kCGImageAlphaPremultipliedLast | kCGBitmapByteOrderDefault, ...)` with premultiplied RGBA bytes. Wrong
   colours (blue and red swapped) would point to the byte order flag.
5. **Click-through** (`update_hover`, `Overlay.update_ignore`): `setIgnoresMouseEvents_` is toggled from a 30 Hz timer that
   reads `NSEvent.mouseLocation()`. A click within ~33 ms of moving onto a fighter may pass through to the window behind.
6. **NSPanel flags**: `NSWindowStyleMaskNonactivatingPanel`, `setHidesOnDeactivate_(False)` (without it the panels vanish,
   because an accessory app is never active), `setFloatingPanel_(True)`, level `NSStatusWindowLevel` (25, above the Dock's 20)
   and the collection behaviour `CanJoinAllSpaces | Stationary | IgnoresCycle | FullScreenAuxiliary`.
7. **Menus**: `NSMenu.popUpMenuPositioningItem_atLocation_inView_(None, NSEvent.mouseLocation(), None)` for fighter menus and
   `(None, NSMakePoint(0, height + 4), statusButton)` for the menu-bar menu. The status-button point assumes the button's
   coordinates are flipped; if the menu opens above the menu bar, use `NSMakePoint(0, 0)`. The app is activated
   (`activateIgnoringOtherApps_`) before a menu opens so keyboard navigation works; that briefly takes focus from your app.
8. **Status item clicks** (`minis_mac/tray.py`): `button.sendActionOn_(LeftMouseUp | RightMouseUp)` and
   `NSApp.currentEvent().type()` to tell left from right.
9. **Window list** (`window_rects`, `fullscreen_busy`): `CGWindowListCopyWindowInfo(OnScreenOnly | ExcludeDesktopElements)`,
   reading only `kCGWindowNumber`, `kCGWindowLayer`, `kCGWindowBounds`, `kCGWindowOwnerPID`, `kCGWindowAlpha`. Bounds are
   available without Screen Recording; names are not read at all.
10. **Coordinates**: everything above the shell is in points with a top-left origin on the menu-bar screen
    (`minis_mac/geometry.py`). A second monitor arranged left of or above the main one gives negative coordinates, as on
    Windows; the arena on such a monitor is the least-tested path.
11. **Process detection** (`minis_core/sources.py`, `mac_exe` / `mac_bundle`): the executable names of Cursor, Windsurf, LM
    Studio, Ollama, Perplexity, Grok, Codex and Claude on macOS were taken from their app bundle names, not observed.
    `python minis.py detect` shows what matched; a missing program needs one name added to its rule.
12. **`ps` parsing** (`minis_mac/procs.py`): `ps -axo pid=,ppid=,time=,lstart=,comm=` with `LC_ALL=C`; `comm` is the full
    executable path. Ownership checks split `ps -o args=` around the clone's `minis.py` path, so a clone path with spaces
    still compares exactly. The python.org build shows up as `.../Python.app/Contents/MacOS/Python`, which counts as python.
13. **PyObjC versions**: `requirements-mac.txt` asks for 11.1 up to (not including) 13. Python 3.14 needs 11.1 or newer.
    If pip tries to compile PyObjC, upgrade pip first (`python -m pip install --upgrade pip`).
14. **Fonts**: the plates use Arial from `/System/Library/Fonts/Supplemental` when Segoe UI is missing; text metrics differ
    slightly from Windows.
15. **Background launch**: `start` launches the three roles with `start_new_session=True` and stdio on `/dev/null`. They stay
    in your login (GUI) session, so they can open windows after the Terminal window closes; if they do not appear when started
    from an SSH session, that is expected (no window server there).
16. **Non-framework Python** (some pyenv builds): AppKit works, but such a process may not be allowed to take keyboard focus,
    so the fighter-select screen's arrow keys might not work (the mouse still does). The python.org installer and Homebrew
    builds are framework builds.
