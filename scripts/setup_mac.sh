#!/usr/bin/env bash
# Taskbar Fighters - macOS setup (EXPERIMENTAL). Safe to run again: every step checks before it acts.
#   ./scripts/setup_mac.sh            check, install into .venv, run the doctor, start the fighters
#   ./scripts/setup_mac.sh --no-start same, but do not start them
# It installs nothing outside this folder (.venv), never asks for a password, and adds no login item.
set -euo pipefail

cd "$(dirname "$0")/.."
START=1
[ "${1:-}" = "--no-start" ] && START=0

say()  { printf '\n==> %s\n' "$*"; }
fail() { printf '\nSTOP: %s\n' "$*" >&2; exit 1; }

say "Checking this Mac"
[ "$(uname -s)" = "Darwin" ] || fail "this script is for macOS (on Windows follow AGENTS.md)."
MACOS="$(sw_vers -productVersion)"
MAJOR="${MACOS%%.*}"
ARCH="$(uname -m)"
echo "macOS $MACOS on $ARCH"
if [ "$MAJOR" -lt 13 ]; then
  fail "macOS 13 (Ventura) or newer is needed; this is $MACOS."
fi

say "Finding Python 3.12 or newer"
PY=""
for c in python3.14 python3.13 python3.12 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      PY="$(command -v "$c")"
      break
    fi
  fi
done
if [ -z "$PY" ]; then
  cat >&2 <<'MSG'

STOP: no Python 3.12+ found (the python3 that ships with macOS / Xcode is too old).
Get one of these, then run this script again:
  - the installer from https://www.python.org/downloads/macos/  (choose 3.12 or newer), or
  - Homebrew:  brew install python@3.12
MSG
  exit 1
fi
echo "using $PY ($("$PY" --version 2>&1))"

say "Creating .venv (skipped if it is already there)"
if [ ! -x .venv/bin/python ]; then
  "$PY" -m venv .venv
fi
VPY=".venv/bin/python"
"$VPY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || fail ".venv uses an old Python: delete the .venv folder and run again."

say "Installing Pillow and PyObjC into .venv"
"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet -r requirements-mac.txt

say "Running the doctor (paste its output to your AI agent if anything says FAIL)"
DOCTOR_RC=0
"$VPY" minis.py doctor || DOCTOR_RC=$?
if [ "$DOCTOR_RC" -ne 0 ]; then
  fail "the doctor reported a problem (above). Nothing was started. See docs/MAC-TESTING.md."
fi

if [ "$START" -eq 1 ]; then
  say "Starting Taskbar Fighters"
  "$VPY" minis.py start || fail "start reported a problem (above). Run: $VPY minis.py status"
  cat <<'MSG'

Look just above your Dock: two pixel fighters, and a Taskbar Fighters icon in the menu bar.
  stop:     .venv/bin/python minis.py stop
  status:   .venv/bin/python minis.py status
  check:    .venv/bin/python minis.py selftest-gui    (shows two fighters for 5 s and reports where they landed)
MSG
fi
