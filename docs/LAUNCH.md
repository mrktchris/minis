# Launch checklist (owner)

These are drafts. Nothing here has been posted, tagged or published. Each step is yours to do.

## 0. Before tagging v1.0.0

The two features the tag was held for (desktop weapons forged in the arena, and the jump rebuild) are on master, with
lock-on and HUD clearance at 128 px. Done on master (2026-10-16): README, CHANGELOG, RESULT and
`docs/release-notes/v1.0.0.md` describe what ships; the card and the loop are rebuilt from the 128 px art
(`python packaging/launch_media.py`); the wheel, sdist and the PyInstaller bundle were built and smoke-tested locally;
`twine check` passes; no franchise names remain (a `git grep` over the tree is clean). Left for you:

- [ ] **Double-click the Windows bundle once.** Stop your git-checkout copy first (`python minis.py stop`; both share
      `%LOCALAPPDATA%\minis`), build (`pyinstaller --noconfirm --clean packaging/taskbar_fighters.spec`), double-click
      `dist/TaskbarFighters/TaskbarFighters.exe`, check that fighters appear and that `TaskbarFighters-cli.exe stop`
      removes them, then restart your checkout. `--help`, `doctor --headless` and `fighters` were verified from the bundle;
      `start` from the bundle was not, because the live checkout was running.
- [ ] Watch `docs/demo.mp4` and `docs/demo.gif` once, and read `docs/release-notes/v1.0.0.md`, the tweets below and the
      README top.
- [ ] Check `docs/MAC-HANDOFF.md`: MAC-5, MAC-8 and MAC-13..21 are still OPEN (real-Mac checks). They do not block the
      tag; the release notes call macOS experimental and list them as known limits.
- [ ] CI is green on master, both the Windows and the macOS jobs.

## 1. Repo settings (the API cannot set these)

- [ ] **Social preview**: Settings > General > Social preview > Edit > upload `docs/social-preview.png`.
- [ ] **Private vulnerability reporting**: Settings > Code security > Private vulnerability reporting > Enable.
      SECURITY.md, CODE_OF_CONDUCT.md and the issue chooser link to it.
- [ ] **Pin the repo** on your profile: profile > Customize your pins.
- [ ] Description, already set: "Pixel-art fighters for your AI coding agents, living in the Windows 11 taskbar..."
      Consider adding "and macOS (experimental)" once the mac job is green.
- [ ] Topics are set: claude, claude-code, codex, ai-agents, pixel-art, taskbar, windows, macos, desktop-pet, python,
      game, llm.
- [ ] Optional: turn on Discussions (Settings > Features) for "show your fight" posts.
- [ ] Optional: fill in `.github/FUNDING.yml` to show a Sponsor button.

## 2. Release

- [ ] `pyproject.toml` has `version = "1.0.0"`, and `docs/release-notes/v1.0.0.md` reads right.
- [ ] Tag and push: `git tag v1.0.0 && git push origin v1.0.0`. The Release workflow tests, builds the Windows zip,
      wheel, sdist, source zip and mac zip, then publishes the release with those notes.
- [ ] Download `TaskbarFighters-windows.zip` from the release on a clean Windows profile or VM and double-click it.
- [ ] PyPI publishes on the tag (trusted publishing, `pypi` environment). PyPI versions are immutable: if anything in the
      wheel is wrong after upload, the fix is 1.0.1, never a re-upload. Check https://pypi.org/project/taskbar-fighters/
      and `pip install taskbar-fighters` in a fresh venv afterwards.

## 3. Post (drafts, ≤280 characters each; X counts a link as 23 and an emoji as 2)

Drafts only: nothing here is posted or scheduled. Media in `docs/`: `demo.mp4` (7.6 s, 1280x720: a taskbar K.O., then an
arena forge, both on a synthetic desktop; best for X), `demo.gif` (the same loop), `social-preview.png` (the 13-fighter
card), and `img/arena-forge.gif`, `img/live-bout.gif`, `img/roster.png`.

**Tweet A: the hook** (attach `docs/demo.mp4`)

> My AI agents fight in my taskbar now.
>
> Claude Code vs Codex. When one works, they clash. When one hits its context limit, it gets K.O.'d.
>
> In arena mode they cut weapons out of my open windows.
>
> Open source, v1.0.0:
> https://github.com/mrktchris/taskbar-fighters

**Tweet B: desktop weapons** (attach `docs/img/arena-forge.gif`)

> New in Taskbar Fighters v1.0.0: desktop weapons.
>
> A fighter slices a title bar out of a window. It shatters into pixels and re-forms as a blade in its hand. Every hit cracks it.
>
> Visual only: your windows are untouched and the screen grab stays in RAM.
>
> https://github.com/mrktchris/taskbar-fighters

**Tweet C: the roster and the install** (attach `docs/social-preview.png`)

> Every AI coding tool on your PC gets a pixel fighter.
>
> Claude Code is a ronin. Codex is a ninja. Gemini, Cursor, Ollama, LM Studio: each has its own. 13 in all, 128 px HD.
>
> Windows zip, or:
> pip install taskbar-fighters
>
> https://github.com/mrktchris/taskbar-fighters

**Thread (4 tweets)**

1. (attach `docs/demo.mp4`)
   > I gave my AI coding agents pixel-art fighters that live in my taskbar.
   >
   > They battle from real usage: clash while one works, hand off when a task finishes, K.O. at the context limit.
   >
   > Taskbar Fighters v1.0.0 is out, open source. 🧵
2. (attach `docs/img/live-bout.gif`)
   > They lock on and actually fight: 3-hit strings, throws, juggles, dash-through cuts, and hand-directed sword set pieces at the dramatic moments.
   >
   > 13 armed fighters, one per program (Claude Code, Codex, Gemini, Cursor, Ollama, LM Studio...) plus 6 extras.
3. (attach `docs/img/arena-forge.gif`)
   > Arena mode: the fight breaks out onto a whole monitor. Window edges become ledges, glass cracks, and fighters forge weapons out of your windows' pixels.
   >
   > Visual only. The screen grab stays in RAM, is never saved, and "forge off" turns it off before you screen-share.
4. (no media, or `docs/social-preview.png`)
   > Privacy: it reads numbers only (token counts, states). No prompts, no file names, no network.
   >
   > Windows: one-click zip. Or pip install taskbar-fighters (macOS experimental).
   >
   > https://github.com/mrktchris/taskbar-fighters
   >
   > Star it if your agents deserve a fight.

Counted with X's rules (a link is 23 characters, an emoji is 2): A 239, B 277, C 243, thread 1 230, 2 253,
3 266, 4 238. Recount after any edit by pasting into the X composer. No franchise names, and every claim is in the README.

## 4. After posting

- [ ] Reply to early issues fast. "Detect a new AI program" requests are one-line PRs (CONTRIBUTING.md).
- [ ] Re-run `python packaging/launch_media.py` whenever the art changes, so the card and loop stay current.
