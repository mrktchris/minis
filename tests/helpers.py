"""Shared test isolation: nothing a test does may depend on, or write to, this machine's real state.
- config.data_dir() -> a fresh temp dir (the real %LOCALAPPDATA%\\minis holds a live feed, bus files and pid files)
- CFG = config.DEFAULTS (a real minis.json is ignored)
"""
import os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIS_TESTING", "1")                         # minis.start_arena refuses: no test may launch a real arena
sys.path.insert(0, str(ROOT))
from minis_core import config as cfgmod  # noqa: E402

CFG = dict(cfgmod.DEFAULTS)


class Isolated(unittest.TestCase):
    """data_dir() points at a temp dir for the whole test."""

    def setUp(self):
        super().setUp()
        self.data = Path(tempfile.mkdtemp(prefix='minis-test-'))
        p = mock.patch.object(cfgmod, 'data_dir', lambda: self.data)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.data, True)


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt
        return self.t
