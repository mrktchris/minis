# Mac handoff (PC side <-> Mac session)

This file is the only channel between the PC side and the owner's Mac Claude session. The Mac session cannot receive
messages; it pulls the repo.

**Mac session: on every start run `git pull` on master, read this file, and work every OPEN item top-down on real macOS.
Commit fixes, mark the item DONE with the commit hash and the date, and push. Add NEW items under "Found on Mac" for
anything the PC side must know** (a bug you could not fix, a behaviour that differs from Windows, a question). Keep each
item short: what you ran, what you saw, what you changed.

Rules that still apply on the Mac: no screen capture (no Screen Recording permission, ever), never touch other apps'
windows, never edit AI tool settings, `python minis.py stop` before switching between a clone and a pip install (they share
`~/Library/Application Support/minis`).

Item format: `- [ ] MAC-<n> (<date>)` = OPEN, `- [x] MAC-<n> (<date>) DONE <hash> <date>` = done.

## OPEN

- [ ] **MAC-1 (2026-10-15) Art moved into the wheel package; paths.py resolves every install.**
  - PC change: the wheel ships `assets/` and `assets_hd/` inside the package `taskbar_fighters_assets` (pyproject
    `package-dir` mapping; the repo layout is unchanged). `minis_core/paths.py` picks a real checkout first, then the
    installed package. Files: `pyproject.toml`, `MANIFEST.in`, `taskbar_fighters_assets/__init__.py`, `minis_core/paths.py`,
    `tests/test_paths.py`.
  - Test A, fresh clone: `git clone https://github.com/mrktchris/taskbar-fighters /tmp/tf && cd /tmp/tf &&
    ./scripts/setup_mac.sh --no-start`, then `.venv/bin/python -m unittest discover -s tests`,
    `.venv/bin/python minis.py fighters`, `.venv/bin/python minis.py start`.
  - Test B, pip: in a new venv (`python3.12 -m venv /tmp/tfv`) run `/tmp/tfv/bin/pip install "taskbar-fighters[mac]"`
    (before the release exists on PyPI: `pip install "/path/to/clone[mac]"` or a wheel from `python -m build`), then from
    another folder `taskbar-fighters doctor`, `taskbar-fighters fighters`, `taskbar-fighters start`, `taskbar-fighters stop`.
  - Expected: tests OK; `fighters` lists 13 characters; doctor PASS; the menu-bar icon and both fighters appear (the icon
    is `taskbar_fighters_assets/assets/icon/minis-256.png` in the pip case); PyObjC was pulled in by the `[mac]` extra.

- [ ] **MAC-2 (2026-10-15) fighter_size 128 is the default; selftest-gui draws the configured size.**
  - PC change: `selftest_mac` in `minis.py` now loads the HD library when `fighter_size` > 64 and shrinks to 96 like
    `Fighter.compose`. Test: `tests/test_mac_procs.py::test_mac_selftest_uses_the_configured_fighter_size`.
  - Test: `python minis.py selftest-gui` at the default; then `python minis.py size 96`, `selftest-gui`; `size 64`,
    `selftest-gui`; `size 128` to finish. Also watch the running fighters after each `size` (they restart).
  - Expected: each run prints `fighter size N px` and PASS; the two windows are N points tall with their bottoms on the
    Dock's top edge; the art is crisp on Retina at 128 (not a blurry 2x upscale of the 64 px art).

- [ ] **MAC-3 (2026-10-15) Arena V7 in the macOS arena window.**
  - PC change: the arena now has a zoom punch (a lens region rewritten every frame), letterbox bars, colour / white flashes,
    ink frames, speed lines, beam clashes, set pieces and an intro / outro. They all reach `minis_mac/arena_window.py`
    through the same `write` / `flush` / `offset` calls as on Windows; full-screen flash frames re-upload every 256-pt tile.
    New CLI flags: `arena --rounds 1|3|5|endless --endless --intensity calm|normal|wild --seconds S --no-intro --no-outro`.
  - Test (needs a second display, or the main one): `python minis.py monitors`, then
    `python minis.py arena --monitor N --rounds 1 --intensity wild --seconds 60`; again with `--intensity calm --no-intro`;
    `python minis.py flash off` and once more; ESC and the EXIT button; `python minis.py arena stop`.
  - Expected: VS card (unless `--no-intro`), the fight across window tops, zoom and letterbox ease in and out without seams
    or tearing, the winner perches on the highest window, both dive back to the Dock strip; with `flash off` no full-screen
    frame at all; ESC / EXIT end it; no permission prompt; frame rate stays usable (report rough fps or stutter, and
    `~/Library/Application Support/minis/logs` lines about the CPU budget). `--freeze` must still refuse on macOS.
    The automated visual-only proof (`VisualOnly7`) records the Win32 backend and is skipped on macOS, so also confirm by eye
    that no other app's window moves, resizes or takes focus during a match.

- [ ] **MAC-4 (2026-10-15) New moves and set pieces at 128 px on Retina.**
  - PC change: V7 art (8-10 weapon moves per character, new reactions, contact sparks) and eight taskbar set pieces
    (`minis_core/setpieces.py`). Files: `assets_hd/*`, `minis_core/choreo.py`, `rounds.py`, `brain.py`, `setpieces.py`.
  - Test: `python minis.py demo match` a few times; `python minis.py fighters set a knight` and `set b kunoichi`, then
    `demo match`; `python minis.py fighters auto` to reset.
  - Expected: throws, juggles, dash-through cuts and set pieces (a frozen beat, then the cut in slow motion) play on the
    Dock strip; both fighters stay in sync (a hit and the reaction land together); nothing is clipped at the top of the
    128-pt windows; sparks and impact frames are sharp, not blurred.

- [ ] **MAC-5 (2026-10-15) Menu-bar menu items.**
  - PC change: the menu is the shared `minis_win/tray.py` logic (Select fighters..., Pause animations, Flash effects,
    Plates, Rival mode, Start/Exit arena, Bout now, Restart Taskbar Fighters, Quit Taskbar Fighters) rendered by
    `minis_mac/tray.py`; the fighter's own right-click menu adds Fighter size, Look and Hide.
  - Test: left click the icon (fighter select opens), right click / Control-click (menu); try every item once; right-click a
    fighter and try *Fighter size*; Restart, then Quit last.
  - Expected: every item works as on Windows; check marks update; Restart brings everything back; Quit leaves no process
    (`python minis.py status`). If the icon is hidden behind the notch, `status` says so and the fighter's right-click menu
    offers the same items.

- [ ] **MAC-6 (2026-10-15) doctor on the integrated build.**
  - Test: `python minis.py doctor` and `python minis.py doctor --headless`, from the clone and from the pip install.
  - Expected: PASS both ways; `code:` shows the clone or `site-packages`; the test window appears and closes in the non-headless
    run; home shown as `~`.

- [ ] **MAC-7 (2026-10-15) No TaskbarCreated equivalent: menu-bar icon after a menu-bar restart.**
  - PC change: none. Windows re-adds the tray icon on the `TaskbarCreated` broadcast; `minis_mac/tray.py`
    `register_message` returns 0 because macOS has no such broadcast.
  - Test: with fighters running, `killall SystemUIServer` (the menu bar restarts), and separately log out / in with
    `autostart on`.
  - Expected: the status item survives (it belongs to our process, so it should). If it disappears, report it here: the PC
    side will add a re-create on `NSApplicationDidChangeScreenParametersNotification` or a periodic check.

- [ ] **MAC-9 (2026-10-15) Art renders one pixel differently on macOS.**
  - PC change: `tests/test_art.py` `test_left_facing_redraw_never_paints_over_skin_or_hands` failed on the macOS runners
    (barbarian/ground_slam/1, pixel (31,13)): the rig re-rendered skin where the committed (Windows-built) sheet has the
    sigil colour. Off Windows the test now skips pixels where the committed right-facing frame disagrees.
  - Test: `python art/build_fighters.py --all` into a scratch copy (`--out /tmp/tf-art`), then compare with the committed
    `assets/` (`cmp` or a pixel diff); report how many frames differ and by how much.
  - Expected: no visible difference; if whole frames differ, the rig depends on float rounding the PC side should remove.

- [ ] **MAC-8 (2026-10-15) Known untested on a real Mac.**
  - Dock on the left / right, and auto-hiding Dock (fallback strip at the bottom); two displays with different scales;
    full-screen apps and Spaces (fighters should hide or stay out of the way); `autostart on|off` across a real login;
    Intel Macs; Python 3.13 / 3.14 with PyObjC 11/12. Report what you can try under "Found on Mac".

## DONE

(none yet)

## Found on Mac

(the Mac session adds items here: `- [ ] FOUND-<n> (<date>) <what you saw> <what the PC side should do>`)
