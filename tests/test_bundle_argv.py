"""Frozen bundle ownership: a double-click starts TaskbarFighters.exe, and `TaskbarFighters-cli.exe status|stop` must
recognise those processes (they were reported 'foreign' and could not be stopped).  Only the two launchers of the SAME
bundle folder count."""
import os, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import Isolated  # noqa: E402,F401  (sets MINIS_TESTING)
import minis  # noqa: E402

BUNDLE = os.path.join('C:' + os.sep, 'Apps', 'TaskbarFighters')
GUI = os.path.join(BUNDLE, 'TaskbarFighters.exe')
CLI = os.path.join(BUNDLE, 'TaskbarFighters-cli.exe')


class SiblingLaunchers(unittest.TestCase):
    def ours(self, argv, role, exe):
        return minis._frozen_argv_is_ours(argv, minis.expected_tail(role), role, exe=exe)

    def test_the_cli_recognises_a_double_click_launch_and_back(self):
        self.assertTrue(self.ours([GUI, 'run', 'a'], 'a', exe=CLI))
        self.assertTrue(self.ours([GUI, 'director'], 'director', exe=CLI))
        self.assertTrue(self.ours([CLI, 'run', 'b'], 'b', exe=GUI))
        self.assertTrue(self.ours([CLI, 'run', 'b'], 'b', exe=CLI))

    def test_another_folder_or_another_program_never_counts(self):
        other = os.path.join('C:' + os.sep, 'Elsewhere', 'TaskbarFighters.exe')
        self.assertFalse(self.ours([other, 'run', 'a'], 'a', exe=CLI))
        self.assertFalse(self.ours([os.path.join(BUNDLE, 'evil.exe'), 'run', 'a'], 'a', exe=CLI))
        self.assertFalse(self.ours([GUI, 'run', 'b'], 'a', exe=CLI))              # wrong role
        self.assertFalse(self.ours([GUI, 'run', 'a', '--x'], 'a', exe=CLI))       # extra args on a slot


if __name__ == '__main__':
    unittest.main()
