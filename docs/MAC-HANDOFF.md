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

- [ ] **MAC-5 (2026-10-15) Menu-bar menu items.**
  - PC change: the menu is the shared `minis_win/tray.py` logic (Select fighters..., Pause animations, Flash effects,
    Plates, Rival mode, Start/Exit arena, Bout now, Restart Taskbar Fighters, Quit Taskbar Fighters) rendered by
    `minis_mac/tray.py`; the fighter's own right-click menu adds Fighter size, Look and Hide.
  - Test: left click the icon (fighter select opens), right click / Control-click (menu); try every item once; right-click a
    fighter and try *Fighter size*; Restart, then Quit last.
  - Expected: every item works as on Windows; check marks update; Restart brings everything back; Quit leaves no process
    (`python minis.py status`). If the icon is hidden behind the notch, `status` says so and the fighter's right-click menu
    offers the same items.
  - Mac 2026-10-15: still OPEN. The menu builds and opens with all 11 items (in-process probe), the fighter right-click menu works, and
    `status` reports the icon hidden behind the notch on this MacBook. Clicking every item needs the owner: this session has
    no permission to post mouse events (Accessibility not granted, on purpose).

- [ ] **MAC-8 (2026-10-15) Known untested on a real Mac.**
  - Dock on the left / right, and auto-hiding Dock (fallback strip at the bottom); two displays with different scales;
    full-screen apps and Spaces (fighters should hide or stay out of the way); `autostart on|off` across a real login;
    Intel Macs; Python 3.13 / 3.14 with PyObjC 11/12. Report what you can try under "Found on Mac".
  - Mac 2026-10-15: Python 3.14.8 + PyObjC 12.2.2 + Pillow 12.3.0 on Apple silicon, macOS 15.7.4: OK (the CI also runs 3.12 / 3.13).
    Dock side / auto-hide and full-screen Spaces need System Settings changes the owner has to make; no second display or
    Intel Mac here.

## DONE

- [x] **MAC-1 (2026-10-15) DONE 3652546 2026-10-15 Art moved into the wheel package; paths.py resolves every install.**
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
  - Mac 2026-10-15: Test A (fresh clone, `setup_mac.sh --no-start`, `fighters`, `start`/`status`/`stop`) OK; the suite had 2 macOS-only
    failures: `test_arena.VisualOnly7` (imports minis_win.shell: now skipped off Windows, 3652546) and `test_art` (FOUND-1). Test B
    (Homebrew Python 3.14 venv, `pip install "<clone>[mac]"`, run from another folder): PyObjC 12.2.2 pulled in by `[mac]`,
    `doctor` PASS with `code:` = site-packages, `fighters` lists 13, `start`/`stop` clean, icon resolves to
    `site-packages/taskbar_fighters_assets/assets/icon/minis-256.png`.

- [x] **MAC-2 (2026-10-15) DONE 3652546 2026-10-15 fighter_size 128 is the default; selftest-gui draws the configured size.**
  - PC change: `selftest_mac` in `minis.py` now loads the HD library when `fighter_size` > 64 and shrinks to 96 like
    `Fighter.compose`. Test: `tests/test_mac_procs.py::test_mac_selftest_uses_the_configured_fighter_size`.
  - Test: `python minis.py selftest-gui` at the default; then `python minis.py size 96`, `selftest-gui`; `size 64`,
    `selftest-gui`; `size 128` to finish. Also watch the running fighters after each `size` (they restart).
  - Expected: each run prints `fighter size N px` and PASS; the two windows are N points tall with their bottoms on the
    Dock's top edge; the art is crisp on Retina at 128 (not a blurry 2x upscale of the 64 px art).
  - Mac 2026-10-15: `size 128/96/64/128` + `selftest-gui`: each prints `fighter size N px` and PASS, windows N pt tall with bottoms on
    the Dock top (y 1044). Running fighters at 128 checked on a Dock-strip capture: crisp HD art, not an upscale.

- [x] **MAC-3 (2026-10-15) DONE 3652546 2026-10-15 Arena V7 in the macOS arena window.**
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
  - Mac 2026-10-15 (single built-in Retina display, monitor 1): `--rounds 1 --intensity wild --seconds 25`: intro, fight, HP falling,
    clean end; `--intensity calm --no-intro`, `flash off`, `--rounds endless` + `arena stop` all end cleanly, no errors in
    arena.log; `--freeze` refuses with the Screen Recording message. No permission prompt. CPU is over budget (FOUND-2). Not
    checked by me (no full-screen capture, no synthetic input): zoom/letterbox seams, perch/dive visuals, ESC and EXIT clicks.
    The frame upload is ~2x faster per tile (3652546).

- [x] **MAC-4 (2026-10-15) DONE 3652546 2026-10-15 New moves and set pieces at 128 px on Retina.**
  - PC change: V7 art (8-10 weapon moves per character, new reactions, contact sparks) and eight taskbar set pieces
    (`minis_core/setpieces.py`). Files: `assets_hd/*`, `minis_core/choreo.py`, `rounds.py`, `brain.py`, `setpieces.py`.
  - Test: `python minis.py demo match` a few times; `python minis.py fighters set a knight` and `set b kunoichi`, then
    `demo match`; `python minis.py fighters auto` to reset.
  - Expected: throws, juggles, dash-through cuts and set pieces (a frozen beat, then the cut in slow motion) play on the
    Dock strip; both fighters stay in sync (a hit and the reaction land together); nothing is clipped at the top of the
    128-pt windows; sparks and impact frames are sharp, not blurred.
  - Mac 2026-10-15: knight vs kunoichi `demo match`, 24 Dock-strip captures at 0.5 s: ROUND 1 / FIGHT banners, dash-through cuts with
    sparks, aerial frames, hits and reactions landing together, nothing clipped at the 128-pt window top. `fighters auto` after.

- [x] **MAC-6 (2026-10-15) DONE 3652546 2026-10-15 doctor on the integrated build.**
  - Test: `python minis.py doctor` and `python minis.py doctor --headless`, from the clone and from the pip install.
  - Expected: PASS both ways; `code:` shows the clone or `site-packages`; the test window appears and closes in the non-headless
    run; home shown as `~`.
  - Mac 2026-10-15: `doctor` and `doctor --headless` PASS from the clone (`code: ~/taskbar-fighters`) and from the pip install
    (`code:` = site-packages); the test window opens in the non-headless run only. (The backend label still says
    "experimental": FOUND-4.)

- [x] **MAC-7 (2026-10-15) DONE 3652546 2026-10-15 No TaskbarCreated equivalent: menu-bar icon after a menu-bar restart.**
  - PC change: none. Windows re-adds the tray icon on the `TaskbarCreated` broadcast; `minis_mac/tray.py`
    `register_message` returns 0 because macOS has no such broadcast.
  - Test: with fighters running, `killall SystemUIServer` (the menu bar restarts), and separately log out / in with
    `autostart on`.
  - Expected: the status item survives (it belongs to our process, so it should). If it disappears, report it here: the PC
    side will add a re-create on `NSApplicationDidChangeScreenParametersNotification` or a periodic check.
  - Mac 2026-10-15: `killall SystemUIServer` with fighters running: the director keeps the same status-item window (same pid, same
    x) afterwards, no re-create needed. (On this Mac the item stays behind the notch either way; FOUND-3.) Login/logout with
    `autostart on` not tried (needs the owner's yes for a login item).

## Found on Mac

- [ ] FOUND-1 (2026-10-15) `test_art.Sigil.test_left_facing_redraw_never_paints_over_skin_or_hands` fails on macOS only (this Mac and
  macos-latest CI, py3.12 / 3.13; Windows passes): barbarian/ground_slam/1 at (31,13) - the rig's rebuilt parts say hand_f where
  the committed sheet has the trim-hi colour (180, 147, 95). Looks like the rig computes a pixel differently on macOS (float /
  libm); art/ is not the Mac side's to edit. PC/art side: make the rig deterministic across platforms or relax the check.
- [ ] FOUND-2 (2026-10-15) The arena runs at 15-31 % of one core on an Apple silicon MacBook (1710x1107 pt @2x) and logs "cpu over
  budget, 20 fps" within a second, every run. The Mac upload is ~2.5 ms per full frame now (3652546); the rest is the shared
  engine / compositor. PC side: a per-platform budget, or profile `minis_core/arena.py` compose at 30 fps.
- [ ] FOUND-3 (2026-10-15) On a MacBook with a full menu bar the status item is created but macOS keeps it behind the notch (x 743,
  never on screen). `status` says so and the fighter menu has every control. Idea for PC side: a `Select fighters...` /
  `Arena` entry point that does not depend on the icon (e.g. scoreboard name click already opens select).
- [ ] FOUND-4 (2026-10-15) `doctor` / `minis_platform.label()` still print "macOS ... - experimental"; README calls macOS beta. PC side:
  pick one word.
