"""
Tests for the best-of-N WorktreeRunner. We exercise the in-place fallback
path (no git) and a real-git path when `git` is available on PATH.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import unittest

from core.worktree_runner import WorktreeRunner


def _has_git() -> bool:
    return shutil.which("git") is not None


def _run(coro):
    return asyncio.run(coro)


class TestWorktreeRunnerInplace(unittest.TestCase):
    """Workspace is NOT a git repo → fallback path runs once in-place."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.workspace = self._td.name
        # No `pytest` invocation in CI test workspace; we use `python -c "import sys"` as a no-op verifier.
        self.runner = WorktreeRunner(
            workspace_dir=self.workspace,
            verify_cmd=["python", "-c", "import sys; sys.exit(0)"],
            verify_timeout=30,
        )

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_inplace_attempt_runs_and_passes(self):
        async def attempt(_path):
            return {"score": 0.5}

        winner, results = _run(self.runner.run(attempt, n=3))
        self.assertIsNotNone(winner)
        self.assertEqual(len(results), 1)
        self.assertTrue(winner.passed)
        self.assertGreaterEqual(winner.score, 1.0)


@unittest.skipUnless(_has_git(), "git not on PATH")
class TestWorktreeRunnerGit(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.workspace = self._td.name
        # Initialize a real git repo.
        subprocess.run(["git", "init", "-q"], cwd=self.workspace, check=True)
        subprocess.run(["git", "config", "user.email", "viki@test"], cwd=self.workspace, check=True)
        subprocess.run(["git", "config", "user.name", "viki"], cwd=self.workspace, check=True)
        with open(os.path.join(self.workspace, "main.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=self.workspace, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.workspace, check=True)
        self.runner = WorktreeRunner(
            workspace_dir=self.workspace,
            verify_cmd=["python", "-c", "import sys; sys.exit(0)"],
            verify_timeout=30,
        )

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_parallel_worktree_attempts(self):
        async def attempt(path):
            with open(os.path.join(path, "main.py"), "w", encoding="utf-8") as f:
                f.write("x = 2\n")
            return {"score": 1.0}

        winner, results = _run(self.runner.run(attempt, n=2))
        self.assertIsNotNone(winner)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertTrue(r.passed)


if __name__ == "__main__":
    unittest.main()
