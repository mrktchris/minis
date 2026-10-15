# AGENTS.md - install and run Taskbar Fighters for your user

You are an AI coding agent. Your user pasted this repository and wants Taskbar Fighters running on their PC: pixel fighters on
the Windows taskbar, one per AI program they use, fighting from real usage. This file is your runbook. Follow it top to bottom,
report each step's result in plain words, and stop at any step that fails.

The command-line tool is `minis.py` ("minis" is the internal short name: packages `minis_core` / `minis_win`, data folder
`%LOCALAPPDATA%\minis`).

## Rules for you, the agent

- **What this app reads:** only numbers and states from local AI-tool transcripts (token counts, timestamps, tool-call states),
  and the process list. Never prompt or reply text, window titles, file or project names. Do not change that.
- **No network.** The app makes no network calls. The only network step in this runbook is `git clone` and `pip install`.
- **Never edit the user's AI tool settings, hooks, status lines or config files** (Claude Code, Codex, Cursor or any other). This
  app needs none of that, and adding it is out of scope.
- **Ask before** adding a startup entry, a Start-menu shortcut, or anything outside the clone folder and `%LOCALAPPDATA%\minis`.
- **Do not** run `selftest-gui`, `arena`, or any screen capture as part of installing. Do not kill processes by name; use
  `python minis.py stop`, which only stops what it started.
- Do not print the contents of the user's transcripts or `%LOCALAPPDATA%\minis` files into the chat.

## 1. Preflight

Run these and check every answer before going on.

| check | command (PowerShell or cmd) | must be |
| --- | --- | --- |
| Windows 11 (10 untested) | `ver` | `Microsoft Windows [Version 10.0.x]`; build 22000 or higher is Windows 11. On Windows 10, tell the user it is untested |
| Python 3.12+ | `python --version` (or `py -3 --version`) | 3.12 or newer. Tested on 3.12 and 3.14. If missing: ask the user to install it from python.org or `winget install Python.Python.3.12` - with their yes |
| pip | `python -m pip --version` | any |
| git | `git --version` | any (or download the ZIP from GitHub) |
| taskbar at the bottom | ask the user, or Settings > Personalization > Taskbar > Taskbar behaviors | bottom; fighters hide when the taskbar is elsewhere or auto-hides |

Only one third-party package is needed: Pillow (see `requirements.txt`). Everything else is the Python standard library and
ctypes.

## 2. Install

```
git clone https://github.com/mrktchris/taskbar-fighters
cd taskbar-fighters
python -m pip install -r requirements.txt
```

## 3. Test

```
python -m unittest discover -s tests
```

Expect `OK` with about 11 tests skipped (the process-level tests only run with `MINIS_INTEGRATION=1`; do not set it). The tests use
synthetic data in a temp folder and never touch the user's real state. If something fails, stop and show the failing test name.

## 4. Start and confirm

```
python minis.py start
python minis.py status
```

`start` launches three windowless processes and after about 3 s prints what is on screen, e.g. `a: Claude Code, b: Sparring bot
asleep`. `status` should begin with a line saying it is running and who is on which side. Tell the user to look at the empty part
of their taskbar, left of the icons.

Then show them the basics: right-click a fighter for the menu, click a name on the scoreboard to pick fighters,
`python minis.py demo match` for a bout right now, `python minis.py pause` / `resume`.

## 5. Optional - only with the user's yes

- **Start at logon:** `python minis.py print-startup` prints (never runs) a `schtasks` command and a shortcut target. Show the user
  what it will add, run it only if they say yes, and tell them the matching `schtasks /Delete` line it prints.
- **Start-menu shortcut:** `python minis.py shortcut` adds "Taskbar Fighters" to the Start menu (`--desktop` also adds one on the
  Desktop). Ask first. Then tell the user to right-click it in Start > **Pin to taskbar** themselves - Windows does not let a
  program pin itself, so do not try. `python minis.py shortcut remove` deletes only the shortcuts it made.
- **Tray icon** (no action needed): while it runs, an icon sits in the notification area. Left-click opens fighter select;
  right-click has Pause, Flash effects, Plates, Rival mode, arena, Bout now, Restart and Quit. `"tray_icon": false` in `minis.json`
  turns it off.
- **Restart:** `python minis.py restart` stops everything and starts it again (use it after editing `minis.json`).
- **Settings:** a `minis.json` next to `minis.py` overrides defaults (see README "Configuration"), e.g. `zone` if the fighters
  overlap the user's taskbar icons, `ignore_sources` to keep a program off the stage.

## 6. Stop and uninstall

```
python minis.py stop
```

To remove everything: run `stop`, `python minis.py shortcut remove` (if a shortcut was added), delete the clone folder, delete `%LOCALAPPDATA%\minis`, and if a startup task was added,
`schtasks /Delete /TN "MinisFighters" /F` (the exact line `print-startup` printed).

## Troubleshooting

| symptom | what to do |
| --- | --- |
| no fighters on the taskbar | `python minis.py status` (running?), then `python minis.py detect` (which AI programs are seen and how). With nothing detected, nothing is shown. Claude Code and Codex need a session file changed in the last 24 h |
| fighters cover taskbar icons / sit in the wrong place | set `"zone": [left, right]` in `minis.json` (screen x of the empty stretch), then `python minis.py restart` |
| nothing visible at all | the taskbar must be at the bottom and not auto-hiding; fullscreen apps hide the fighters |
| tiny or misplaced on a high-DPI display | only 100% scaling has been observed; integer scaling is untested at 150% / 200%. Tell the user and adjust `zone` |
| a program is shown that the user does not want | `"ignore_sources": ["<id from detect>"]` in `minis.json` |
| flashing bothers the user | `python minis.py flash off` |
| `start` says it is already running | `python minis.py restart` |

## Adapt it

- **A new AI program:** add one row to `RULES` in `minis_core/sources.py` - `dict(source='myagent', program='My Agent',
  character='generic', exe=('myagent.exe',), cmd=('myagent', '@scope/myagent'))` (exe = image name, cmd = names matched against an
  interpreter's first arguments). Optionally a short name in `LABEL`. Run the tests; `python minis.py detect` shows whether it is
  seen.
- **A new character:** add a `Body(...)` and an `_c(...)` entry to `art/roster.py` (copy an existing one: proportions, weapon,
  palette, signature strike / special / super / ultimate), then `python art/build_fighters.py --all --only <name>` to build `assets/<name>`
  and `assets_hd/<name>`, and run `python -m unittest tests.test_art`. It appears in the select screen's LOOK grid automatically;
  any program can wear it with `python minis.py skin <program> <name>`.
- Read `README.md` ("How it works") before changing the engine; keep the privacy rules above.
