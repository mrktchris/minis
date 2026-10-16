# Packaging and releases

How Taskbar Fighters ships. Checked on 2026-10-16 for v1.0.0 (Windows 11, Python 3.14, PyInstaller 6, setuptools 77+).

## What ships

| Download | Built by | How it is made |
| --- | --- | --- |
| `TaskbarFighters-windows.zip` | `.github/workflows/release.yml` (windows-latest) | PyInstaller onedir from `packaging/taskbar_fighters.spec` |
| `taskbar_fighters-<ver>-py3-none-any.whl` + `.tar.gz` | release.yml (ubuntu) | `python -m build` from `pyproject.toml` + `MANIFEST.in` |
| `taskbar-fighters-<ver>-source.zip` | release.yml | `git archive` of the tag |
| `TaskbarFighters-macos.zip` (experimental) | release.yml (macos-latest) | the tag's source; run `scripts/setup_mac.sh` (py2app later) |

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

Verified for v1.0.0 in a clean venv (Python 3.14): `TaskbarFighters-cli.exe --help`, `doctor --headless` (PASS 5 of 5)
and `fighters` (all 13 characters) run from `dist/TaskbarFighters/` with the working directory elsewhere, so the bundle
reads its own `_internal/assets`. `start` from the bundle was not run, because the owner's live copy was running.

### How the frozen build finds itself

All in `minis_core/paths.py` and `minis.py`:

- **Read-only files** (`assets/`, `assets_hd/`, the icon): `paths.bundle_root()` = `sys._MEIPASS` (PyInstaller), else
  `$RESOURCEPATH` when frozen (py2app), else the checkout, else the installed package `taskbar_fighters_assets`.
- **`minis.json`**: `paths.settings_dir()` = next to the executable (or next to the `.app`) when frozen, the checkout
  otherwise. A wheel install has none and runs on defaults plus the CLI toggles.
- **Child processes** re-launch the executable itself (`self_argv()`: `[sys.executable, tail...]` when frozen), and the
  ownership check (`argv_is_ours`) accepts exactly that form. Shortcut, startup and LaunchAgent commands use the same.
- **`qa/` writes** (`arena capture`, `selftest-gui` masks) go to `paths.qa_dir()`, which is `None` in any installed build,
  so they fall back to the data folder and never write inside a bundle or `site-packages`.
- **Help text** names the program as started (`prog_name()`): `python minis.py`, `taskbar-fighters` or the exe name.

### One install at a time

A pip install, the bundle and a git checkout all share `%LOCALAPPDATA%\minis`. Each sees the others' processes as
`foreign` (correct: the ownership check compares exact command lines). If two installs both run `start`, two sets of
fighters draw over the same taskbar. The README and AGENTS.md say so: stop one before starting another.

## The wheel (`pip install taskbar-fighters`)

`pyproject.toml` (setuptools) ships `minis.py` as a top-level module, the packages `minis_core`, `minis_win`,
`minis_platform`, `minis_mac` and `taskbar_fighters_assets`, and the console script `taskbar-fighters = minis:main`. The
extra `taskbar-fighters[mac]` adds PyObjC (`pyobjc-core`, `-Cocoa`, `-Quartz`, `>=11.1,<13`, the pins of
`requirements-mac.txt`) with a `sys_platform == "darwin"` marker, so the extra is a no-op on Windows.

**How the art gets in.** The art stays at the repo root (`assets/`, `assets_hd/`), where `art/build_fighters.py`, the tools
and the tests expect it. `[tool.setuptools.package-dir]` maps those two folders onto the subpackages
`taskbar_fighters_assets.assets` and `taskbar_fighters_assets.assets_hd`, and package data (`**/*.png`, `**/*.json`,
`**/*.ico`) carries every file. Installed, the art lives at `site-packages/taskbar_fighters_assets/assets/...`: never as
generic top-level `site-packages/assets`. `paths.bundle_root()` prefers the checkout only when it really is one
(`minis.py`, `assets/icon`, `minis_core/` and `tests/` side by side), then the package, so a stray `site-packages/assets`
from another project is ignored. `MANIFEST.in` keeps the sdist buildable on its own (the wheel is built from it).

Verified for v1.0.0: `python -m build` gives a wheel with all 162 art files under `taskbar_fighters_assets/` and no
top-level data; in a fresh venv, from a different working directory, `taskbar-fighters --help`, `doctor --headless`
(PASS) and `fighters` (13 characters) run from the installed copy. CI repeats the install check on every push
(`package` job).

`minis.py` is still a top-level module named `minis`. Renaming it would touch every test and the frozen entry point; it is
left for a later release.

**Version.** Bump `version` in `pyproject.toml` together with the tag. The release workflow fails if they differ. PyPI
versions are immutable: a mistake after upload is fixed by the next version, never by re-uploading.

## macOS

The release job zips the tagged source (`scripts/setup_mac.sh` inside); `pip install "taskbar-fighters[mac]"` is the other route. Once `minis.py doctor` passes
on a real Mac, a py2app bundle is the next step. `RESOURCEPATH` is already handled (`paths.bundle_root`); it still needs the
`minis_platform` backends as explicit includes (they are imported with `importlib`, which bundlers cannot see), and
a bundle identifier and signing.

## PyPI

On. The `pypi` job in `release.yml` publishes the wheel and sdist with trusted publishing (the owner registered the
pending publisher: project `taskbar-fighters`, repo `mrktchris/taskbar-fighters`, workflow `release.yml`, environment
`pypi`). It runs only on a `v*` tag, after the GitHub Release job.

## Launch media

`python packaging/launch_media.py` rebuilds `docs/social-preview.png` (1280x640: the 128 px HD sheets' idle frames,
nearest-neighbour upscaled to a fixed on-card height), `docs/demo.gif` and `docs/demo.mp4` (both 1280x720, 7.6 s at
20 fps). The loop has two offline acts at 2x pixel scale: the taskbar strip `tools/doc_images.py` renders (real planner and
renderer, DEMO numbers, 128 px fighters) over a synthetic desktop, ending on round 1's K.O., then an arena desktop-weapon
forge on doc_images' synthetic busy desktop. The mp4 needs ffmpeg. The script never captures the screen.
