# Packaging and releases

How Taskbar Fighters ships, and the small code changes the frozen builds still need. Everything here was checked on
2026-10-15 against commit `4a5b363` plus the in-progress mac port (`minis_platform/`, `minis_mac/`).

## What ships

| Download | Built by | How it is made |
| --- | --- | --- |
| `TaskbarFighters-windows.zip` | `.github/workflows/release.yml` (windows-latest) | PyInstaller onedir from `packaging/taskbar_fighters.spec` |
| `taskbar_fighters-<ver>-py3-none-any.whl` + `.tar.gz` | release.yml (ubuntu) | `python -m build` from `pyproject.toml` + `MANIFEST.in` |
| `taskbar-fighters-<ver>-source.zip` | release.yml | `git archive` of the tag |
| `TaskbarFighters-macos.zip` (experimental) | release.yml (macos-latest) | the tag's source + `setup_mac.sh` when present (py2app later) |

Release = push a tag `vX.Y.Z` whose `pyproject.toml` version is `X.Y.Z` and whose `docs/release-notes/vX.Y.Z.md` exists.
The workflow refuses a version mismatch and a missing notes file.

## The Windows bundle

```
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean packaging/taskbar_fighters.spec
```

`dist/TaskbarFighters/` holds two executables that share one `_internal/` (Python runtime, the code, `assets/`,
`assets_hd/`, `assets/icon/`):

- `TaskbarFighters.exe` - windowed. Double-click with no arguments runs `start` (`packaging/tf_launcher.py`). With
  arguments it is the same CLI as `python minis.py`.
- `TaskbarFighters-cli.exe` - the console twin, so `status`, `stop`, `detect` and `--help` print somewhere.

Verified locally (Python 3.12, PyInstaller 6.22.3, 55 MB unzipped): `--help`, `status`, `detect` and `fighters` run from
the bundle. Moving `_internal/assets` away changes the `fighters` output, which shows the bundle reads its own art.
`start` was deliberately not run, because the owner's live copy was running.

### Code changes the frozen build still needs

These are not applied yet because other agents are editing these files. Apply them after the mac port lands. The spec
already assumes them.

1. **Child processes must re-launch the exe, not `python minis.py`.** This is the blocker: until it lands, `start` in the
   bundle launches nothing. `minis.py` builds `[python_exe(), ROOT / 'minis.py', ...]` in `role_argv`, in
   `start_arena`, and in `quit_all` / `restart_all` (the tray's Quit and Restart). `argv_is_ours` then refuses anything whose `argv[0]`
   basename is not in `PYTHONS`. In a frozen build `sys.executable` is `TaskbarFighters.exe` and there is no
   `minis.py` file, so `launch_role` returns False. Suggested change:

   ```python
   FROZEN = getattr(sys, 'frozen', False)

   def self_argv():
       """The command prefix that runs this program again: [pythonw, ROOT/minis.py] or, frozen, [TaskbarFighters.exe]."""
       if FROZEN:
           exe = Path(sys.executable)
           gui = exe.with_name('TaskbarFighters.exe')        # children never get a console, even when started from the -cli twin
           return [str(gui if gui.exists() else exe)]
       return [str(python_exe()), str(ROOT / 'minis.py')]

   def role_argv(role):
       return self_argv() + expected_tail(role)
   ```

   Use `self_argv()` at every `[str(python_exe()), str(ROOT / 'minis.py')]` site, including `start_arena`, `quit_all`, `restart_all`,
   `shortcut_spec` and `cmd_print_startup`. In `argv_is_ours` the frozen form has the tail at `argv[1:]`, so
   compare `argv[:len(prefix)]` with `self_argv()` (normcase, normpath) and then the tail. Keep the absolute-path rule.
   Also accept the frozen exe name in place of `PYTHONS` when `FROZEN`.

2. **ROOT (read-only files) from the bundle.** Under PyInstaller 6 onedir, a module's `__file__` already points inside
   `_internal/`, so the bundle finds `assets/` today (verified). py2app and a onefile build do not do this (their
   modules live in a zip or a temp dir), so make it explicit in each of these files:

   | File | Line today | Change to |
   | --- | --- | --- |
   | `minis.py` | `ROOT = Path(__file__).resolve().parent` | `ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))` |
   | `minis_core/atlas.py` | `ROOT = Path(__file__).resolve().parent.parent` | `ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))` (needs `import sys`) |
   | `minis_core/config.py` | `ROOT = Path(__file__).resolve().parent.parent` | same pattern (needs `import sys`) |
   | `minis_core/fx.py` | `ROOT = Path(__file__).resolve().parent.parent` | same pattern (needs `import sys`) |
   | `minis_win/shell.py` | `ICON_PATH = Path(__file__).resolve().parent.parent / 'assets' / 'icon' / 'minis.ico'` | `ICON_PATH = atlas.ROOT / 'assets' / 'icon' / 'minis.ico'` (one ROOT for the whole program), or the `_MEIPASS` pattern |

   Better still, define `ROOT` once (for example in `minis_core/config.py`) and import it everywhere else.

   For py2app, set `sys._MEIPASS`-equivalent from `os.environ.get('RESOURCEPATH')`. Put the line in one helper:
   `getattr(sys, '_MEIPASS', None) or os.environ.get('RESOURCEPATH') or <dev path>`.

3. **`minis.json` belongs next to the exe, not in `_internal/`.** `config.load()` and `minis.load_config()` read
   `ROOT / 'minis.json'`. In a frozen build use `Path(sys.executable).parent / 'minis.json'` (still optional). The data
   directory (`%LOCALAPPDATA%\minis`) is unaffected and stays shared between a source checkout, a pip install and the
   bundle.
4. **`qa/` writes.** `capture_allowed` (for `arena capture`) and `selftest-gui` write under `ROOT / 'qa'`. Frozen, that is inside the bundle.
   Keep the data-folder branch and drop `ROOT / 'qa'` when `FROZEN`.
5. **Shortcut and startup commands** (`shortcut_spec`, `shortcut_is_ours`, `cmd_print_startup`, `cmd_shortcut`'s icon
   check) name `pythonw minis.py start`. Frozen, they should name `TaskbarFighters.exe start`. Item 1's `self_argv()`
   covers this.
6. **Help text** says `python minis.py ...`. Optional: when frozen, print `TaskbarFighters-cli.exe ...` instead
   (`ap.prog`).

### One install at a time

A pip install, the bundle and a git checkout all share `%LOCALAPPDATA%\minis`. Each sees the others' processes as
`foreign` (correct: the ownership check compares exact command lines). If two installs both run `start`, two sets of
fighters draw over the same taskbar. The README should say: stop one before starting another.

## The wheel (`pip install taskbar-fighters`)

`pyproject.toml` (setuptools) ships `minis.py` as a top-level module, the packages `minis_core`, `minis_win`,
`minis_platform` and `minis_mac` (each only if it exists at build time), and the art. The console script is
`taskbar-fighters = minis:main`. The extra `taskbar-fighters[mac]` adds pyobjc.

**How the art gets in.** `assets/` and `assets_hd/` are listed as data-only namespace directories
(`packages.find include = [..., "assets*", "assets_hd*"]`, package data `*.png *.json *.ico`, `MANIFEST.in` for the
sdist). They install next to `minis.py` in `site-packages`, which is where every `ROOT = Path(__file__)...` lookup
already looks. No code change is needed, and it is verified: in a clean 3.12 venv, `taskbar-fighters --help` and
`taskbar-fighters status` run and `atlas.ASSETS` resolves to `site-packages/assets` with all 162 art files. The
`[tool.setuptools.data-files]` route was rejected because it installs under `sys.prefix`, not `site-packages`, so ROOT
would miss it.

**Before PyPI.** Top-level `site-packages/assets` and `site-packages/assets_hd` are generic names that another
careless package could overwrite. That is fine for the GitHub-release wheel. Before publishing to PyPI, move the art
under the package: `minis_core/assets` (or a `taskbar_fighters/` package), point `atlas.ASSETS`, `fx.CANDIDATES` and
`shell.ICON_PATH` at it, and drop `assets*` from `packages.find`. Do the same for `minis.py`, which is a top-level
module named `minis`.

**Version.** Bump `version` in `pyproject.toml` together with the tag. The release workflow fails if they differ.

## macOS

The release job zips the tagged source (plus `setup_mac.sh` when the mac port adds it). Once `minis.py doctor` passes
on a real Mac, a py2app bundle is the next step. It needs `RESOURCEPATH` handling (item 2 above), the
`minis_platform` backends as explicit includes (they are imported with `importlib`, which bundlers cannot see), and
`requirements-mac.txt` pins in `pyproject.toml`'s `mac` extra.

## PyPI

This is off. `release.yml` has a commented-out trusted-publishing job, and its header lists the three owner steps:
a pending publisher on pypi.org, a `pypi` environment on GitHub, and uncommenting the job.

## Launch media

`python packaging/launch_media.py` rebuilds `docs/social-preview.png` (1280x640, the sprite sheets' idle frames
nearest-neighbour upscaled to a fixed on-card height, so it follows the art at any cell size), `docs/demo.gif` and `docs/demo.mp4`. The gif and mp4 are an 8 s window of the same
offline taskbar render `tools/doc_images.py` uses, at 20 fps, with DEMO numbers. The mp4 needs ffmpeg. The script
never captures the screen.
