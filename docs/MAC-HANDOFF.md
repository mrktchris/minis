# Mac handoff (PC side <-> Mac session)

This file is the only channel between the PC side and the owner's Mac Claude session. The Mac session cannot receive
messages; it pulls the repo.

**Mac session: on every start run `git pull` on master, read this file, and work every OPEN item top-down on real macOS.
Commit fixes, mark the item DONE with the commit hash and the date, and push. Add NEW items under "Found on Mac" for
anything the PC side must know** (a bug you could not fix, a behaviour that differs from Windows, a question). Keep each
item short: what you ran, what you saw, what you changed.

Rules that still apply on the Mac: the Mac session takes no screen capture itself and never grants Screen Recording on its
own (the app's desktop weapons may use the permission only if the OWNER has granted it; the app never requests it: MAC-13),
never touch other apps' windows, never edit AI tool settings, `python minis.py stop` before switching between a clone and a pip install (they share
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

- [ ] **MAC-17 (2026-10-15) Fighter windows are taller: jump headroom above the cell.**
  - PC change: a fighter now really leaves the ground (anim.json `air` curves, drawn by the engine every redraw), so each
    fighter window reaches `headroom_px(size)` = 30 x size/64 points above its cell (128 px fighters: 60 pt). `Fighter.geometry`
    moves the window's `y` up by that much; `render.compose` draws the cell at the bottom of the taller image. Files: `minis.py`
    (`Fighter.geometry`), `minis_core/config.py` (`JUMP_HEADROOM`, `headroom_px`), `minis_core/render.py`, `minis_core/brain.py`.
  - Test: `python minis.py selftest-gui` at sizes 128, 96 and 64 (`python minis.py size N`), then `python minis.py demo match`
    a few times at 128. Click on an app window just above a fighter's head while it stands still.
  - Expected: feet still on the Dock's top edge at every size (unchanged), PASS; in a match the fighters jump visibly above
    their standing height and are never cut off at the top; the transparent headroom does not swallow clicks meant for the
    window behind it (if it does, report it: macOS hit-testing may need `update_ignore` to treat alpha 0 as click-through).

- [ ] **MAC-18 (2026-10-15) The fight zone and a hard clip now scale with fighter_size.**
  - PC change: `config.fight_zone(cfg, size)` keeps a whole sprite (34 x size/64) plus 4 px between any hip and a plate /
    the scoreboard, and every fighter frame is clipped to `config.fight_band` (plate strip end .. scoreboard left edge), so a
    knocked-down 128 px fighter, a beam or a spark can no longer paint over the right plate (seen live on Windows). Files:
    `minis_core/config.py`, `minis_core/brain.py` (`band`, `view['clip']`), `minis_core/render.py`, `minis.py` (`logic_zone`).
  - Test: at 64, 96 and 128 run `python minis.py demo match` twice; watch the knockdowns near the ends of the strip.
  - Expected: no fighter, weapon, spark or beam ever overlaps a plate or the scoreboard. On the Mac the scoreboard sits at
    the right end of the strip (`Scoreboard.left` uses the screen width), not at `scoreboard.left_x(cfg)`: if a fighter's
    beam is cut off far from the widget, or reaches over it, report where (the band is computed from cfg, not the moved widget).

- [ ] **MAC-19 (2026-10-15) Own-window dump for docs (`tools/own_capture.py`).**
  - PC change: every fighter / plate / scoreboard window writes its own image only while
    `~/Library/Application Support/minis/dump/request.json` is active (`minis_core/dump.py`, one `dump.watch(...)` line per
    window in `minis.py`); with no request the cost is one stat every 0.5 s and one idle thread per process. Retina HUD images
    carry `density: 2` (png twice the window size; `w`/`h` in points). The tool reads the Dock band from
    `minis_mac.shell.taskbar_rect()` (an AppKit query, not a capture). No Screen Recording permission is involved.
  - Test: `python minis.py start`, then `python tools/own_capture.py --out /tmp/cap --seconds 10 --demo spar --keep`; check the
    plate / scoreboard records in the dump folder (`density` 2, `w`/`h` = on-screen size); once more with `minis.py plates menubar`.
  - Expected: no permission prompt; `/tmp/cap/live-bout.gif` and `live-taskbar.png` show whole fighters over flat grey with a
    dark bar at the Dock band, plates sharp and correctly sized; `request.json` is gone afterwards. Risk: the tool assumes
    `Overlay.x/y` and `taskbar_rect()` share one top-left, y-down coordinate system; if windows land off the bar, say so.

- [ ] **MAC-20 (2026-10-15) Lock-on and the new jumps (shared engine, look only).**
  - PC change: inside a bout each fighter replays its opponent's row of the shared timeline (`brain.Track`) and faces it on
    every redraw (a short `turn` pivot on the ground); bouts stay inside the zone; strikes close in to their own reach;
    projectiles climb to an airborne opponent; jump / juggle / vault rows rebuilt with take-off, hang and landing.
  - Test: `python minis.py fighters set a generic`, `set b codex`, then `python minis.py demo match` three times; `fighters auto`.
  - Expected: no fighter ever aims its bow or swings at empty space with its back to the other one, except the dash-through
    pass (back turned until its cut lands) and the walk home; jumps arc smoothly with a squash on landing; both fighters
    stay in sync (a hit and its reaction land together).

- [ ] **MAC-13 (2026-10-15) Desktop weapons: Screen Recording preflight, real pixels, no prompt.**
  - PC change: the arena forges weapons from a screen grab taken ONCE into RAM at start (minis_core/forge.py; on by default,
    `python minis.py forge off|on`, menu *Desktop weapons*). On macOS `minis_mac/shell.py` `grab_screen(rect)` calls
    `CGWindowListCreateImage(rect, OnScreenOnly, kCGNullWindowID, kCGWindowImageNominalResolution)` (fallback
    `CGDisplayCreateImageForRect`) and `pil_from_cgimage` only when `screen_capture_allowed()` (`CGPreflightScreenCaptureAccess`)
    is true. `CGRequestScreenCaptureAccess` is never called. PIL's ImageGrab is not used on macOS (it writes a temp file).
  - Test A (no permission, the normal state): `python minis.py doctor` -> the line `desktop weapons: on, from window SHAPES ...
    For real pixels: System Settings > ...`. Then `python minis.py arena --rounds 1 --seconds 60`. Expected: NO permission
    prompt at any point; 1-4 forges a match (an outline cuts a window piece, a dark hole is left, the piece morphs into a
    frosted-glass / steel weapon); `~/Library/Application Support/minis/arena.json` while it runs has `"screen_pixels": false`;
    `logs/arena.log` says `forge=True pixels=False`.
  - Test B (only if the OWNER chooses to grant Screen Recording to the terminal / Python that runs it): doctor says `from real
    screen pixels`; the arena's weapons carry the windows' real colours; arena.json shows `"screen_pixels": true` and, after
    `python minis.py forge off`, `false` within ~2 s while the weapons vanish. Report whether the grab is at points size
    (1710x1107 on a 14" MacBook) or needed the Retina downscale, and whether a moved window's pieces come out as glass.
    Never grant the permission yourself; if the owner does not want to, skip Test B and say so.
  - Expected for both: no file appears anywhere with screen content (`find ~/Library/Application Support/minis /tmp -newer
    <start marker> -type f` lists only logs / json), `python minis.py arena capture` is refused on macOS as before.

- [ ] **MAC-14 (2026-10-15) Arena CPU (FOUND-2): measure the V8 macOS window.**
  - PC change: `minis_mac/arena_window.py` uses 128-pt tiles (was 256), skips fully transparent tiles (contents nil, no
    conversion), shows colour / white flashes as a GPU tint layer (no full-canvas re-upload), keeps the canvas at 1 px per
    point (Core Animation scales it on Retina), and counts tiles and upload time. `run_arena` logs a profile line every 5 s
    with `MINIS_ARENA_PROFILE=1`. On the PC the simulated mac work dropped from ~583 k to ~261 k pixels per frame
    (docs/ARENA.md Performance).
  - Test: `MINIS_ARENA_PROFILE=1 python minis.py arena --rounds 3 --intensity normal --seconds 60` (repeat with `calm`, `wild`,
    and once with `python minis.py forge off`); meanwhile `top -pid <arena pid> -stats pid,cpu -l 30` (the pid is in arena.json).
    Copy the `arena profile:` lines from `~/Library/Application Support/minis/logs/arena.log`.
  - Expected: CPU <= 10 % of a core at normal (was 15-31 %), no `cpu over budget, 20 fps` line, flashes still visible (a
    full-screen tint), no tearing between tiles. Report the profile numbers: if `upload` dominates, the next step is bigger
    tiles for big dirty rects (a per-rect tile size); if `render` dominates, it is the shared compositor; if neither and CPU
    is still high, it is the AppKit run loop (hover polling at 30 Hz over every panel).

- [ ] **MAC-15 (2026-10-15) Menu-bar icon behind the notch (FOUND-3): the fallback badge.**
  - PC change: macOS cannot be told where to put a status item; it hides whatever does not fit. `minis_mac/tray.py` now
    gives the item an `autosaveName` (a Cmd-drag to a visible spot is remembered) and checks every 5 s
    (`menubar_icon_shown`, bounds only) whether it is shown. While it is hidden, a 22-pt badge with the same icon appears in
    the free stretch just left of the notch (`geometry.menubar_badge_origin`; left of the HUD plates when they are in the
    menu bar): left click = fighter select, right click = the tray menu (opens at the mouse). It disappears when the item is
    visible again.
  - Test: on the notched MacBook with the full menu bar: `python minis.py start`; within ~5 s look left of the notch.
    Left-click the badge (select opens), right-click it (menu with *Desktop weapons*), try `python minis.py plates menubar`
    (badge moves left of the plates after a restart). Then make room (quit a few menu-bar apps): the badge goes away and the
    icon shows. `python minis.py status` should keep reporting the icon's state.
  - Expected: badge visible and clickable, crisp on Retina, never over the notch or the app menus' text when the free
    stretch exists; no permission prompt. Report if `status_item_shown` mistakes the badge for the icon (the badge sits at
    y >= 2 for exactly that reason).

- [ ] **MAC-16 (2026-10-15) Menu items: Desktop weapons.**
  - PC change: the tray menu and every fighter's right-click menu have a *Desktop weapons* checkmark (control.json `forge`).
  - Test: untick it in the menu-bar menu, check `python minis.py status` says `desktop weapons: off`; tick it again from a
    fighter's right-click menu.
  - Expected: the check mark follows the state in both menus.

- [ ] **MAC-20 (2026-10-16) The forged weapon is held in the hand, frame by frame (Retina check).**
  - PC change: while a fighter holds a forged weapon the arena draws it from its unarmed sheet (`Atlas.unarmed_frame`) and
    attaches the weapon at that frame's `grip` (and `grip2` for dual-wielders: gemini, codex, kunoichi, monk, nomad,
    generic), rotated to the grip angle with the pivot at the grip point (`forge.Forge.placement`, `held`); the smear is a
    crescent along the tip positions the art really drew, only around a strike's contact. When it shatters, the next frame
    is the armed sheet again. Files: `minis_core/forge.py`, `minis_core/arena.py` (`drawables`, `_sprite(unarmed=)`).
  - Test: `python minis.py arena --rounds 1 --intensity wild --seconds 90` (wild: 5-7 forges), once at the default fighters
    and once with `python minis.py fighters set a knight` / `set b kunoichi` (`fighters auto` after). Watch a forged
    weapon through a few strikes, a jump, a hit and its shatter.
  - Expected on Retina (the canvas is 1 px per point, scaled 2x with nearest filtering): the weapon's grip stays inside the
    closed hand on every frame (no 1-pt gap or jitter between hand and weapon at 2x), the fighter's own weapon is never
    drawn at the same time (no double weapon), a dual-wielder holds one in each hand with the back one behind the body,
    the rotated weapon edges are crisp (nearest, no blur) and the rim reads on light and dark windows; the smear appears
    only on the cut, not when the arm returns to guard; after the shatter the own weapon is back on the very next frame.
    Report any frame where the weapon floats off the hand (character, move, roughly when): that is a grip in the art.

## DONE

- [x] **MAC-9 (2026-10-15) DONE 58b3fdd 2026-10-15 Art renders one pixel differently on macOS.**
  - PC change: `tests/test_art.py` `test_left_facing_redraw_never_paints_over_skin_or_hands` failed on the macOS runners
    (barbarian/ground_slam/1, pixel (31,13)): the rig re-rendered skin where the committed (Windows-built) sheet has the
    sigil colour. Off Windows the test now skips pixels where the committed right-facing frame disagrees.
  - Test: `python art/build_fighters.py --all` into a scratch copy (`--out /tmp/tf-art`), then compare with the committed
    `assets/` (`cmp` or a pixel diff); report how many frames differ and by how much.
  - Expected: no visible difference; if whole frames differ, the rig depends on float rounding the PC side should remove.
  - Mac 2026-10-15: `build_fighters.py --res 1` and `--res 2` into scratch folders (Python 3.14.8, Pillow 12.3.0, Apple silicon),
    compared with the committed art. anim.json / fx.json: identical content (line endings only). PNGs are not identical:
    assets/ 802 px differ over 53 sheets (barbarian 123 px in 2 cells, knight 3 px, ...), assets_hd/ 7,661 px (claude 228 px
    in 26 cells, gemini 731 px in 18 cells, ...). Single-pixel rounding differences between platforms, no visible change in
    the Dock-strip captures (MAC-4). (This item was dropped from the file by a Mac-side rebase and is restored here.)

- [x] **MAC-1 (2026-10-15) DONE 58b3fdd 2026-10-15 Art moved into the wheel package; paths.py resolves every install.**
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
    failures: `test_arena.VisualOnly7` (imports minis_win.shell: now skipped off Windows, 58b3fdd) and `test_art` (FOUND-1). Test B
    (Homebrew Python 3.14 venv, `pip install "<clone>[mac]"`, run from another folder): PyObjC 12.2.2 pulled in by `[mac]`,
    `doctor` PASS with `code:` = site-packages, `fighters` lists 13, `start`/`stop` clean, icon resolves to
    `site-packages/taskbar_fighters_assets/assets/icon/minis-256.png`.

- [x] **MAC-2 (2026-10-15) DONE 58b3fdd 2026-10-15 fighter_size 128 is the default; selftest-gui draws the configured size.**
  - PC change: `selftest_mac` in `minis.py` now loads the HD library when `fighter_size` > 64 and shrinks to 96 like
    `Fighter.compose`. Test: `tests/test_mac_procs.py::test_mac_selftest_uses_the_configured_fighter_size`.
  - Test: `python minis.py selftest-gui` at the default; then `python minis.py size 96`, `selftest-gui`; `size 64`,
    `selftest-gui`; `size 128` to finish. Also watch the running fighters after each `size` (they restart).
  - Expected: each run prints `fighter size N px` and PASS; the two windows are N points tall with their bottoms on the
    Dock's top edge; the art is crisp on Retina at 128 (not a blurry 2x upscale of the 64 px art).
  - Mac 2026-10-15: `size 128/96/64/128` + `selftest-gui`: each prints `fighter size N px` and PASS, windows N pt tall with bottoms on
    the Dock top (y 1044). Running fighters at 128 checked on a Dock-strip capture: crisp HD art, not an upscale.

- [x] **MAC-3 (2026-10-15) DONE 58b3fdd 2026-10-15 Arena V7 in the macOS arena window.**
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
    The frame upload is ~2x faster per tile (58b3fdd).

- [x] **MAC-4 (2026-10-15) DONE 58b3fdd 2026-10-15 New moves and set pieces at 128 px on Retina.**
  - PC change: V7 art (8-10 weapon moves per character, new reactions, contact sparks) and eight taskbar set pieces
    (`minis_core/setpieces.py`). Files: `assets_hd/*`, `minis_core/choreo.py`, `rounds.py`, `brain.py`, `setpieces.py`.
  - Test: `python minis.py demo match` a few times; `python minis.py fighters set a knight` and `set b kunoichi`, then
    `demo match`; `python minis.py fighters auto` to reset.
  - Expected: throws, juggles, dash-through cuts and set pieces (a frozen beat, then the cut in slow motion) play on the
    Dock strip; both fighters stay in sync (a hit and the reaction land together); nothing is clipped at the top of the
    128-pt windows; sparks and impact frames are sharp, not blurred.
  - Mac 2026-10-15: knight vs kunoichi `demo match`, 24 Dock-strip captures at 0.5 s: ROUND 1 / FIGHT banners, dash-through cuts with
    sparks, aerial frames, hits and reactions landing together, nothing clipped at the 128-pt window top. `fighters auto` after.

- [x] **MAC-6 (2026-10-15) DONE 58b3fdd 2026-10-15 doctor on the integrated build.**
  - Test: `python minis.py doctor` and `python minis.py doctor --headless`, from the clone and from the pip install.
  - Expected: PASS both ways; `code:` shows the clone or `site-packages`; the test window appears and closes in the non-headless
    run; home shown as `~`.
  - Mac 2026-10-15: `doctor` and `doctor --headless` PASS from the clone (`code: ~/taskbar-fighters`) and from the pip install
    (`code:` = site-packages); the test window opens in the non-headless run only. (The backend label still says
    "experimental": FOUND-4.)

- [x] **MAC-7 (2026-10-15) DONE 58b3fdd 2026-10-15 No TaskbarCreated equivalent: menu-bar icon after a menu-bar restart.**
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
  - PC 2026-10-15: relaxed (96e40c4): off Windows the check compares only skin pixels whose four neighbours are skin. Making
    the rig bit-identical across platforms stays open for the art side.
- [ ] FOUND-2 (2026-10-15) The arena runs at 15-31 % of one core on an Apple silicon MacBook (1710x1107 pt @2x) and logs "cpu over
  budget, 20 fps" within a second, every run. The Mac upload is ~2.5 ms per full frame now (58b3fdd); the rest is the shared
  engine / compositor. PC side: a per-platform budget, or profile `minis_core/arena.py` compose at 30 fps.
  - PC 2026-10-15: the macOS window work is cut (128-pt tiles, empty tiles skipped, GPU flash layer) and a profiler added;
    measuring on the Mac is MAC-14.
- [ ] FOUND-3 (2026-10-15) On a MacBook with a full menu bar the status item is created but macOS keeps it behind the notch (x 743,
  never on screen). `status` says so and the fighter menu has every control. Idea for PC side: a `Select fighters...` /
  `Arena` entry point that does not depend on the icon (e.g. scoreboard name click already opens select).
  - PC 2026-10-15: autosaveName + a fallback badge left of the notch while the icon is hidden (MAC-15).
- [x] FOUND-4 (2026-10-15) DONE (PC, 2026-10-15: one word, "experimental"; the README badges no longer say beta) `doctor` / `minis_platform.label()` still print "macOS ... - experimental"; README calls macOS beta. PC side:
  pick one word.
