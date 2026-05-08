"""
Phase 3: tests for PatchVerify (apply edit, run verify, rollback on failure).
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest

from viki.core.patch_verify import PatchVerify


class TestPatchVerify(unittest.TestCase):
    def test_passing_patch_is_kept(self):
        with tempfile.TemporaryDirectory() as ws:
            target = os.path.join(ws, "ok.py")
            with open(target, "w") as f:
                f.write("x = 1\n")
            new_content = "x = 2\n"
            # Verify command always succeeds.
            pv = PatchVerify(workspace_dir=ws, verify_cmd=[sys.executable, "-c", "import sys; sys.exit(0)"])
            result = pv.apply_and_verify(target, new_content)
            self.assertTrue(result.passed)
            self.assertFalse(result.rolled_back)
            with open(target) as f:
                self.assertEqual(f.read(), "x = 2\n")
            # Diff should mention the change.
            self.assertIn("-x = 1", result.diff)
            self.assertIn("+x = 2", result.diff)

    def test_failing_patch_rolls_back(self):
        with tempfile.TemporaryDirectory() as ws:
            target = os.path.join(ws, "ok.py")
            original = "ORIGINAL\n"
            with open(target, "w") as f:
                f.write(original)
            new_content = "BROKEN\n"
            # Verify command always fails (returns 1).
            pv = PatchVerify(workspace_dir=ws, verify_cmd=[sys.executable, "-c", "import sys; sys.exit(1)"])
            result = pv.apply_and_verify(target, new_content)
            self.assertFalse(result.passed)
            self.assertTrue(result.rolled_back)
            with open(target) as f:
                self.assertEqual(f.read(), original)

    def test_path_escape_blocked(self):
        with tempfile.TemporaryDirectory() as ws:
            pv = PatchVerify(workspace_dir=ws, verify_cmd=[sys.executable, "-c", "import sys; sys.exit(0)"])
            with self.assertRaises(PermissionError):
                pv.apply_and_verify(os.path.join("..", "escape.py"), "x = 0")

    def test_new_file_creation_on_success(self):
        with tempfile.TemporaryDirectory() as ws:
            target = os.path.join(ws, "newfile.py")
            pv = PatchVerify(workspace_dir=ws, verify_cmd=[sys.executable, "-c", "import sys; sys.exit(0)"])
            result = pv.apply_and_verify(target, "y = 9\n")
            self.assertTrue(result.passed)
            self.assertTrue(os.path.isfile(target))


if __name__ == "__main__":
    unittest.main()
