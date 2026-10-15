# Security and privacy

Taskbar Fighters runs on your machine next to your AI coding tools, so this page sets out what it reads and what it
never does.

## What it reads

- **Process table.** It reads image names and the first command-line arguments of running processes, only to recognise
  known AI programs (`python minis.py detect` shows the matches).
- **Claude Code and Codex session transcripts** (`~/.claude/projects`, `~/.codex/sessions`). It reads numbers and states
  only: token counts, timestamps, and whether a tool call is running. It never reads prompt or reply text.
- **Its own files.** It reads and writes its own data in `%LOCALAPPDATA%\minis` on Windows (the mac port has its own
  data folder), and an optional `minis.json` you create.

## What it never does

- **No network.** It makes no network calls, sends no telemetry and has no update checks.
- It never reads prompt or reply text, window titles, or file or project names.
- It never edits your AI tools' settings, hooks, status lines or config files.
- It never sends input to, moves, or closes another program's windows. Arena mode only looks like it does.
- It never kills processes by name. `stop` ends only processes it started itself, after checking each one's exact
  command line.
- Screen capture runs only when you ask for it (`arena --freeze`, `arena capture`, `selftest-gui`). Captures stay in
  RAM, or are written only under `qa/` or the data folder.

## Supported versions

Only the latest release gets security fixes.

## Reporting a vulnerability

Please report it privately. Do not open a public issue.

- Use GitHub's **[Report a vulnerability](../../security/advisories/new)** button on the Security tab. It opens a
  private advisory that only the maintainer can see.

Include what you found, how to reproduce it, and which version or commit you used. You should get an answer within a
week. A confirmed issue gets a fix and a credited advisory, unless you prefer to stay anonymous.

Examples of security bugs here: a way to make the app read message content or file names, a network call, a path that
lets `stop` kill a process it did not start, or a write outside the data folder or `qa/`.
