# Launch checklist (owner)

These are drafts. Nothing here has been posted, tagged or published. Each step is yours to do.

## 0. Before tagging v1.0.0

**On hold (owner, 2026-10-15):** v1.0.0 is tagged only after two more features land: desktop-pixel weapon forging in the
arena, and a jump-animation fix.

Done on master (2026-10-15): the frozen-build path changes (PACKAGING.md items 1-6), the wheel ships the art inside the
package `taskbar_fighters_assets`, the 128 px art and set pieces are in, the README patch is merged, and no franchise names
remain (a `git grep` over the tree is clean). Left for you:

- [ ] After the two features: `python packaging/launch_media.py` (it already renders the 128 px strip), view the card and
      the loop, and commit `docs/social-preview.png`, `docs/demo.gif` and `docs/demo.mp4`. The committed ones still show
      the V6 64 px art.
- [ ] Bring `docs/release-notes/v1.0.0.md` and the CHANGELOG entry up to date with those features.
- [ ] Check `docs/MAC-HANDOFF.md`: the Mac session's DONE items and anything under "Found on Mac".

- [ ] **Double-click the Windows bundle once.** Stop your git-checkout copy first (`python minis.py stop`; both share
      `%LOCALAPPDATA%\minis`), build (`pyinstaller --noconfirm --clean packaging/taskbar_fighters.spec`), double-click
      `dist/TaskbarFighters/TaskbarFighters.exe`, check that fighters appear and that `TaskbarFighters-cli.exe stop`
      removes them, then restart your checkout. `--help`, `doctor --headless` and `fighters` were verified from the bundle;
      `start` from the bundle was not, because the live checkout was running.
- [ ] Read `docs/release-notes/v1.0.0.md`, the tweets below and the README top once more.
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

## 3. Post (drafts, ≤280 characters each; X counts a link as 23)

Media in `docs/`: `demo.mp4` (8 s, 1280x720, best for X), `demo.gif` (the same loop), `social-preview.png` (the
13-fighter card), and `img/roster.png`, `img/arena.gif`, `img/select.png`.

**Tweet A: the hook** (attach `demo.mp4`)

> My AI agents now fight in my taskbar.
>
> Claude Code vs Codex. When one is working, they clash. When one hits its context limit, it gets K.O.'d.
>
> Pixel art, 13 fighters, open source:
> https://github.com/mrktchris/taskbar-fighters

**Tweet B: the roster** (attach `social-preview.png` or `img/roster.png`)

> Every AI coding tool on your PC gets a pixel fighter.
>
> Claude Code is a ronin. Codex is a ninja. Gemini, Cursor, Ollama, LM Studio: each has its own.
>
> They live in your taskbar and fight based on what your agents are actually doing.
>
> https://github.com/mrktchris/taskbar-fighters

**Tweet C: the install** (attach `demo.gif`)

> Install it the 2026 way: paste this into Claude Code or Codex
>
> "Install and run Taskbar Fighters from github.com/mrktchris/taskbar-fighters - follow AGENTS.md"
>
> Your agent sets it up. Then it has to fight.

**Tweet D: the set pieces** (attach `img/arena-setpieces.png`)

> Gave my AI agents' fighters hand-directed sword scenes.
>
> A frozen beat back to back, then the cut lands in slow motion. A blade lock that breaks into a riposte. Flame, water and
> petal trails.
>
> It all plays in your taskbar while your agents work.
>
> https://github.com/mrktchris/taskbar-fighters

**Thread (4 tweets)**

1. (attach `demo.mp4`)
   > I gave my AI coding agents pixel-art fighters that live in my Windows taskbar.
   >
   > They battle based on real usage: clash while one works, hand off when a task finishes, K.O. at the context limit.
   >
   > Open source. 🧵
2. (attach `img/roster.png`)
   > 13 armed fighters.
   >
   > One per program (Claude Code, Codex, Gemini, Cursor, Ollama, LM Studio, plus a generic Agent for aider, Copilot
   > CLI, Grok...) and 6 extras any program can wear.
   >
   > Every frame is generated by a rig from pose data.
3. (attach `img/arena.gif`)
   > Arena mode: the fight breaks out of the taskbar onto a whole monitor. Fighters jump between your windows and
   > "shatter" them.
   >
   > Visual only. Nothing happens to your real windows.
4. (no media, or `social-preview.png`)
   > Privacy: it reads numbers only (token counts, states). No prompts, no file names, no network.
   >
   > Windows .zip, pip install taskbar-fighters, or let your agent install it.
   >
   > https://github.com/mrktchris/taskbar-fighters
   >
   > Star it if your agents deserve a fight.

Counted with X's rules (a link is 23 characters, an emoji is 2): A 204, B 257, C 205, D 270, thread 1 210, 2 231,
3 176, 4 234. Recount after any edit by pasting into the X composer. In the thread, the wrapped lines of tweets 2 and 3 are
one paragraph each.

## 4. After posting

- [ ] Reply to early issues fast. "Detect a new AI program" requests are one-line PRs (CONTRIBUTING.md).
- [ ] Re-run `python packaging/launch_media.py` whenever the art changes, so the card and loop stay current.
