# Changelog

Taskbar Fighters (internal short name: minis). Summarised from the git history and the build logs in [RESULT.md](RESULT.md).

## V6 - 2026-10-15 (`744d818`)

- **Armed roster.** The seven program fighters redrawn as taller (~4.5 heads), armed characters: ronin (Claude), ninja (Codex),
  twin-blade dancer (Gemini), lancer (Cursor), monk-brute (Ollama), white cyber samurai (LM Studio), archer-ranger (Agent). Six
  selectable extras: Kunoichi, Knight, Barbarian, Monk, Nomad, Oni. Real HD (1 px outline, 5 tones), weapon crescents and streak
  smears, longer wind-ups and holds, impact frames transparent outside the figure.
- **Fighter select.** `control.json` lineup (program per side, look per program), `minis.py fighters set|pin|auto|reset`, `pick`,
  `skin`, right-click submenus and a Smash-style select screen (WHO row, LOOK grid, VS card).
- **Fight feel.** 30 fps during fights, knockdown get-up fix, a 3.4 s KO finisher beat (was 6 s), ultimates 1.7 -> 0.3 per match,
  spacing from sprite reach, brace on charge-ups, TIME banner, comebacks, task-finished super. Arena: same rules, pacing fixed (KO
  rounds 52% -> 85%).
- **UX and safety.** Readable scoreboard with a result line and per-program records, undoable hide, *Quit minis*, `flash on|off`,
  `start` reports what is on screen; `arena capture` refuses `--freeze` and writes only under `qa/` or the data folder;
  non-blocking `arena stop`, absolute-argv ownership check, director watchdog, config errors logged, fps clamped.
- **Tray, shortcut and icon (2026-10-15).** App icon (`assets/icon/`, `art/build_icon.py`), a notification-area icon (left click:
  select; right click: menu with Restart / Quit), `minis.py shortcut [--desktop] | shortcut remove`, `minis.py restart`,
  `tray_icon` setting; user-visible name Taskbar Fighters in menus and tooltips.
- **Docs (2026-10-15).** Renamed to Taskbar Fighters; README rewritten with fresh annotated images from `tools/doc_images.py`;
  AGENTS.md install runbook, CLAUDE.md, llms.txt, requirements.txt, this changelog.

## V5.1 - 2026-10-14 (`ef6dec7` .. `66d08d7`)

- Character redesign (silhouette feature, accent colour, HD rim light per character) and a beam FX overhaul (`grow`, `flash`).
- **Dormant partner:** a program that went quiet keeps its slot asleep for 24 h; **sparring bot** fills an empty side;
  **rival mode** wakes a sleeping partner for a match every 8-15 min.
- `minis.py detect`; four more programs (Copilot CLI, Qwen Code, Perplexity, Grok); `ignore_sources`.
- Animation notes from two fight-animation studies (impact frames, holds, travel, streak smears); tests can no longer launch a real
  arena.

## V5 - 2026-10-14 (`bf5d090`)

- **Choreography:** a seeded no-repeat move picker (`minis_core/choreo.py`), openers, combos, defence, spacing, specials, a super
  meter and one ultimate per match; the same planner drives the taskbar, the arena and the simulator.
- **Beam playback:** beams extend from the hands, hitstop freezes both fighters on contact, an ultimate landing flashes the frame.

## V4 - 2026-10-13 (`886f116`)

- Best-of-3 **matches** with HP, banners, effects and one ultimate per character; `winners decided|random`; `record.json`.
- **HD** sheets (128 px), effects library with procedural stand-ins.
- **Scoreboard widget** with W-L, HP bars, a 7-day context sparkline and three buttons.
- **Arena mode:** a full-monitor click-through overlay with window-ledge platforms, cracks, shatter, letters and explosions; the
  optional `--freeze` backdrop stays in RAM.
- Reset countdown on the plate, loud `waiting?`, pupils that follow the cursor, dizzy after a fast drag, Shift-drag throw.
- First public commit, with build logs, move list, comparison, credits and an MIT licence (`ce9ac6e`, `d416fc9`).

## V3 / V3.1 - 2026-10-13

- **Any AI program, two slots:** a director plus fighter slots `a` and `b`; Claude Code and Codex from transcripts, other programs
  from the process table; bouts start from usage (clash, spar, ranged duel, handoff, KO + console); `pause` / `resume`.
- V3.1: fighters walk back to their own half, plates fixed at the left end of the zone, any awake pair interacts, `demo`, `plates
  on|off`.

## V1 / V2 - 2026-10-12

- Two rig-generated pixel fighters, Claude and Codex, on the Windows taskbar: 48 moves each, per-pixel-alpha windows, HUD plate with
  real context %, spar / ranged duel / handoff / console from telemetry, pid-checked `stop`, a headless simulator for tests and
  previews.
