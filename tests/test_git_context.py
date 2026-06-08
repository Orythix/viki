import os
import shutil
import subprocess
import tempfile
import unittest

from core import git_context


class TestGitContext(unittest.TestCase):
    def tearDown(self):
        git_context.clear_git_context_cache()

    def test_non_repo_returns_empty(self):
        d = tempfile.mkdtemp()
        try:
            self.assertEqual(git_context.get_git_workspace_snapshot(d, ttl_seconds=0.0), "")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_repo_returns_block(self):
        d = tempfile.mkdtemp()
        try:
            r = subprocess.run(["git", "init"], cwd=d, capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                self.skipTest("git init not available")
            subprocess.run(
                ["git", "config", "user.email", "viki@test.local"],
                cwd=d,
                capture_output=True,
                timeout=5,
                check=False,
            )
            subprocess.run(
                ["git", "config", "user.name", "VIKI Test"],
                cwd=d,
                capture_output=True,
                timeout=5,
                check=False,
            )
            with open(os.path.join(d, "f.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            subprocess.run(["git", "add", "f.txt"], cwd=d, capture_output=True, timeout=5, check=False)
            subprocess.run(["git", "commit", "-m", "init"], cwd=d, capture_output=True, timeout=10, check=False)

            out = git_context.get_git_workspace_snapshot(d, ttl_seconds=0.0)
            self.assertIn("Git snapshot", out)
            self.assertIn("Current branch", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
