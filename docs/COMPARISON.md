# Minis vs. the field (research pass, 2026-10-13)

Read-only research against official repos/pages. Stars as fetched today; GitHub pages rarely show a last-commit date, so "activity" is what the page or press stated. Ideas only; no code or art copied, licences noted.

## Closest projects

| # | Project | What it does | Platform | Licence | Stars | Activity |
|---|---|---|---|---|---|---|
| 1 | [Clawd on Desk](https://github.com/rullerzhou-afk/clawd-on-desk) | Electron pixel pet reacting to 20+ coding agents via hooks; permission bubbles; quota rings | Win/mac/Linux | AGPL-3.0 (art separate) | ~6.4k | active 2026 |
| 2 | [AgentPet](https://github.com/ntd4996/agentpet) | Pixel pet + menu-bar agent monitor; XP/evolution fed by real tokens; Claude/Codex limits HUD | mac/Win/Linux | MIT (app only) | 380 | active |
| 3 | [OpenPets](https://github.com/OpenPetsHQ/openpets) | Local-first pet platform; MCP `react`/`say`; plugin SDK; one pet per workspace | mac/Win/Linux | MIT | 1.3k | active |
| 4 | [Codex Pets](https://developers.openai.com/codex/app/settings#codex-pets) (built-in) | `/pet` overlay, 4 states; `/hatch` makes a pet from an image; 8 built-ins | Win/mac | proprietary | n/a | May 2026 ([Engadget](https://engadget.com/2162796/openai-introduces-ai-generated-pets-for-its-codex-app)) |
| 5 | [VS Code "Blobby"](https://code.visualstudio.com/docs/agents/reference/chat-pet) (built-in) | Pet above chat box; 6 agent states; drag/throw/dizzy; achievements | VS Code | proprietary | n/a | current |
| 6 | [claude-code-mascot-statusline](https://github.com/TeXmeijin/claude-code-mascot-statusline) | Pixel pet in the Claude Code status line; 9 hook states; fur reddens with context % | terminal | MIT | 29 | 2026 |
| 7 | [vscode-pets](https://github.com/tonybaloney/vscode-pets) | Pets in an editor panel; 20+ species, themes, throw ball | VS Code | MIT | ~4.2k | active |
| 8 | [BongoCat](https://github.com/ayangweb/BongoCat) | Live2D cat mirrors keyboard/mouse/gamepad; custom models | Win/mac | Apache-2.0 | ~23.9k | active |
| 9 | [desktopPet (eSheep)](https://github.com/Adrianotiger/desktopPet) | Sheep walks on window edges, multi-monitor; XML pets + editor | Windows | MIT | ~1.2k | Oct 2026 |
| 10 | [Shijima-Qt](https://github.com/pixelomer/shijima-qt) / Shimeji-ee | Shimeji mascots, frontmost-window tracking, HTTP API | mac/Linux/Win | GPL-3.0 | 200 | archived Apr 2026 |
| 11 | [Desktop Goose](https://samperson.itch.io/desktop-goose) | Goose steals cursor, drags notepads, tracks mud, memes; mod API | Win/mac | closed, pay-what-you-want | n/a | v0.31 |
| 12 | [ccusage](https://github.com/ryoppippi/ccusage) | CLI usage/cost reports for 18 agent CLIs; 5-hour blocks; statusline hook | CLI | MIT | ~19k | active |
| 13 | [CodexBar](https://github.com/steipete/CodexBar) / [Win-CodexBar](https://github.com/nesszer/Win-CodexBar) | Tray quota bars for 100+ providers, reset countdowns, burndown charts | mac / Win port | MIT | 22.5k / 1.2k | active |
| 14 | [Casual Desktop Game](https://danielbrendel.itch.io/casual-desktop-game) | Desktop Destroyer remake: hammer, guns, nukes on a frozen screenshot; mods | Windows | closed | n/a | Dec 2025 |

Not found: any maintained open-source window-crack/shatter overlay. [TrustMeBro](https://www.producthunt.com/p/trustmebro-harmless-prank-application/trustmebro-2) (Python GDI glitching) is the only open chaos toy surfaced and does no cracks. No Codex "work-pets" plugin exists under that name; the real thing is built-in Codex Pets plus [awesome-codex-pets](https://github.com/gennadi-kuzmin/awesome-codex-pets) packs.

## Gap read

| Project | It does, minis doesn't | Minis does, it doesn't |
|---|---|---|
| Clawd on Desk | 20+ agents via hooks, approve/deny bubbles, Telegram mirror | Two agents interacting; zero config; taskbar; arena |
| AgentPet | XP/evolution, achievements, web dashboard, leaderboard | Fights/handoffs; no sign-in; local Codex plan window |
| OpenPets | Plugin SDK, MCP so agents talk back | Live context %; auto-detection; agent config untouched |
| Codex Pets | AI-generated pets from a photo; first-party | Cross-vendor; Claude and Codex side by side with numbers |
| Blobby | Throw/dizzy/achievements, accessories | Outside the editor; real telemetry; two fighters |
| mascot-statusline | Colour drifts with context (same idea as our bar) | Desktop pixel art, not 8 text cells; bouts |
| vscode-pets | 20+ species, backgrounds, many pets at once | A pet means a program actually running |
| BongoCat | Live2D smoothness, huge model library | Any telemetry; no input hooking |
| eSheep | Walks real window edges, multi-monitor, pet editor | Agent awareness; HUD; fights |
| Shijima | Climbs windows, big pack ecosystem | Maintained; no Java |
| Desktop Goose | Memorable chaos (cursor theft, dragged windows) | Harmless: never touches input or windows |
| ccusage | USD cost, daily/weekly/monthly history | Live visual, not a report |
| CodexBar | Reset countdowns, burndown, 100+ providers, alerts | Characters; taskbar; Claude context % from transcript |
| Casual Desktop Game | 30+ tools, Workshop mods, 7-year community | Wrecking driven by live usage; nothing real touched |

## To be clearly better (prioritised)

1. **Reset countdowns on the plate** ("5h 35% - 2h10m") next to plan %, as CodexBar does; minis already parses `resets_at`.
2. **Make `waiting?` loud.** Permission-needed is the headline state in Clawd, Codex Pets and Blobby: distinct pose + plate colour. Approve/deny stays out of scope (we never send input).
3. **Burndown sparkline in the scoreboard**: 7-day context/plan trend from local numbers only (AgentPet/CodexBar), no network.
4. **Micro-interactions**: pupils follow the cursor, dizzy on fast drags, Shift-drag throw (Blobby). Cheap, high delight.
5. **Pet-pack import**: read the Codex `pet.json` + spritesheet format so users' pets can fight (AgentPet proves it is reusable); licence per pack.
6. **Multi-monitor and DPI before arena**: eSheep handles both; our README still says 100% DPI only.
7. **Persistent record + achievements** off `record.json` (AgentPet): streaks, "survived 90% ctx", first KO.
8. **Window-edge awareness in arena** (eSheep walks rects): land on title bars, not only top edges; optional sound, off by default.
9. **Say the config-free part out loud**: every rival writes hooks into agent config; minis touches nothing.

## Where minis is weaker

Coverage and ecosystem. Clawd on Desk knows 20+ agents through hooks and gets exact states; minis has real states for two and a CPU heuristic for the rest. AgentPet and CodexBar show reset timers, history and burndown; minis shows one number now. BongoCat and Shimeji have enormous community art libraries; minis has seven generated rigs and no import path. Rivals run on mac/Linux; minis is Windows 11, bottom taskbar, 100% DPI. The edge is narrower but real: two live agents interacting from real usage, no config touched, no network, and the only one in the taskbar or an arena.
