"""
P1: Best-of-N attempts in isolated `git worktree` sandboxes.

For tough coding tasks, running multiple independent attempts in parallel
and merging the winner outperforms a single attempt. This module:

  1. Creates N `git worktree`s off the current HEAD, each on its own branch.
  2. Runs an attempt callback (e.g. `PlanEditSkill.execute`) inside each.
  3. Scores attempts via the project's verify command (default `pytest -q`).
  4. Returns the winning attempt's diff and optionally fast-forwards the
     working tree onto the winning branch.

The runner depends only on `git` being on PATH. It tolerates non-git
workspaces by falling back to a single in-place attempt with a warning.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from viki.config.logger import viki_logger

AttemptFn = Callable[[str], Awaitable[dict[str, Any]]]


@dataclass
class AttemptResult:
    branch: str
    worktree_path: str
    score: float
    passed: bool
    verify_stdout: str = ""
    verify_stderr: str = ""
    verify_exit: int = -1
    diff: str = ""
    duration_seconds: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "worktree_path": self.worktree_path,
            "score": self.score,
            "passed": self.passed,
            "verify_exit": self.verify_exit,
            "verify_stdout": self.verify_stdout[:2000],
            "verify_stderr": self.verify_stderr[:2000],
            "diff": self.diff[:6000],
            "duration_seconds": round(self.duration_seconds, 3),
            "error": self.error,
            "metadata": self.metadata,
        }


class WorktreeRunner:
    """Runs N parallel attempts in `git worktree`s and picks the winner."""

    DEFAULT_VERIFY_CMD = ["pytest", "-q"]

    def __init__(
        self,
        workspace_dir: str,
        verify_cmd: list[str] | None = None,
        verify_timeout: int = 600,
        worktree_root: str | None = None,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.verify_cmd = verify_cmd or self.DEFAULT_VERIFY_CMD
        self.verify_timeout = verify_timeout
        self.worktree_root = worktree_root or os.path.join(tempfile.gettempdir(), "viki_worktrees")
        os.makedirs(self.worktree_root, exist_ok=True)

    # --- git plumbing ---
    def _git(self, args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd or self.workspace_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def _is_git_repo(self) -> bool:
        if shutil.which("git") is None:
            return False
        rc, _, _ = self._git(["rev-parse", "--is-inside-work-tree"])
        return rc == 0

    def _create_worktree(self, branch: str) -> str | None:
        wt_path = os.path.join(self.worktree_root, f"viki_{branch}_{uuid.uuid4().hex[:6]}")
        rc, _, err = self._git(["worktree", "add", "-b", branch, wt_path, "HEAD"])
        if rc != 0:
            viki_logger.debug("WorktreeRunner: failed to create %s: %s", wt_path, err)
            return None
        return wt_path

    def _remove_worktree(self, wt_path: str) -> None:
        try:
            self._git(["worktree", "remove", "--force", wt_path])
        except Exception:
            try:
                shutil.rmtree(wt_path, ignore_errors=True)
            except Exception:
                pass

    # --- verification ---
    def _run_verify(self, wt_path: str) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                self.verify_cmd,
                cwd=wt_path,
                capture_output=True,
                text=True,
                timeout=self.verify_timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            return 124, e.stdout or "", "verify timed out"
        except Exception as e:
            return 1, "", str(e)

    def _diff(self, wt_path: str) -> str:
        rc, out, _ = self._git(["diff", "HEAD"], cwd=wt_path)
        return out if rc == 0 else ""

    # --- public API ---
    async def run(
        self,
        attempt: AttemptFn,
        n: int = 3,
        merge_winner: bool = False,
    ) -> tuple[AttemptResult | None, list[AttemptResult]]:
        """
        Run `n` attempts in parallel; return (winner, all_results).
        Each attempt is invoked as `await attempt(worktree_path)` and is
        expected to mutate files inside that worktree.

        When `merge_winner=True` and the workspace is a git repo, the winning
        branch is fast-forward-merged into the current branch.
        """
        if not self._is_git_repo():
            viki_logger.warning(
                "WorktreeRunner: %s is not a git repo; running 1 in-place attempt.",
                self.workspace_dir,
            )
            return await self._run_inplace(attempt)

        n = max(1, int(n))
        worktrees: list[tuple[str, str]] = []  # (branch, path)
        for i in range(n):
            branch = f"viki/attempt-{int(time.time())}-{i}-{uuid.uuid4().hex[:4]}"
            path = self._create_worktree(branch)
            if path is not None:
                worktrees.append((branch, path))

        if not worktrees:
            viki_logger.warning("WorktreeRunner: no worktrees could be created.")
            return await self._run_inplace(attempt)

        async def _one(branch: str, path: str) -> AttemptResult:
            t0 = time.perf_counter()
            err: str | None = None
            meta: dict[str, Any] = {}
            try:
                meta = await attempt(path) or {}
            except Exception as e:
                err = str(e)
                viki_logger.debug("attempt failed in %s: %s", path, e)
            rc, out, errlog = self._run_verify(path)
            diff_text = self._diff(path)
            score = float(meta.get("score", 0.0)) + (1.0 if rc == 0 else 0.0)
            return AttemptResult(
                branch=branch,
                worktree_path=path,
                score=score,
                passed=(rc == 0),
                verify_stdout=out,
                verify_stderr=errlog,
                verify_exit=rc,
                diff=diff_text,
                duration_seconds=time.perf_counter() - t0,
                error=err,
                metadata=meta,
            )

        results = await asyncio.gather(*[_one(b, p) for b, p in worktrees])
        winner = max(results, key=lambda r: (r.passed, r.score), default=None)

        if merge_winner and winner and winner.passed:
            self._git(["merge", "--ff-only", winner.branch])

        # Cleanup losers; keep winner's branch around for inspection.
        for r in results:
            if winner is None or r.branch != winner.branch:
                self._remove_worktree(r.worktree_path)
                self._git(["branch", "-D", r.branch])

        return winner, results

    async def _run_inplace(
        self, attempt: AttemptFn
    ) -> tuple[AttemptResult | None, list[AttemptResult]]:
        t0 = time.perf_counter()
        err: str | None = None
        meta: dict[str, Any] = {}
        try:
            meta = await attempt(self.workspace_dir) or {}
        except Exception as e:
            err = str(e)
        rc, out, errlog = self._run_verify(self.workspace_dir)
        score = float(meta.get("score", 0.0)) + (1.0 if rc == 0 else 0.0)
        result = AttemptResult(
            branch="inplace",
            worktree_path=self.workspace_dir,
            score=score,
            passed=(rc == 0),
            verify_stdout=out,
            verify_stderr=errlog,
            verify_exit=rc,
            diff="",
            duration_seconds=time.perf_counter() - t0,
            error=err,
            metadata=meta,
        )
        return result, [result]
