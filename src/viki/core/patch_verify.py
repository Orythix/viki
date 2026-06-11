"""
Phase 3: Patch-and-verify loop.

Every code edit produces a unified diff, runs the project's verification
command (default `pytest -q`), and either commits the change to the
workspace or rolls it back on failure.

Usage from the controller / planner-executor:

    pv = PatchVerify(workspace_dir, verify_cmd=["pytest", "-q"])
    result = pv.apply_and_verify(path, new_content)
    if result.passed:
        # change committed
    else:
        # automatically rolled back; result.diff describes what was tried.
"""

from __future__ import annotations

import difflib
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from viki.config.logger import viki_logger


@dataclass
class PatchResult:
    path: str
    passed: bool
    diff: str
    verify_stdout: str = ""
    verify_stderr: str = ""
    verify_exit: int = -1
    duration_seconds: float = 0.0
    rolled_back: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "passed": self.passed,
            "rolled_back": self.rolled_back,
            "diff": self.diff[:6000],
            "verify_stdout": self.verify_stdout[:2000],
            "verify_stderr": self.verify_stderr[:2000],
            "verify_exit": self.verify_exit,
            "duration_seconds": round(self.duration_seconds, 3),
            "metadata": self.metadata,
        }


class PatchVerify:
    DEFAULT_VERIFY_CMD = ["pytest", "-q", "--tb=short"]

    def __init__(
        self,
        workspace_dir: str,
        verify_cmd: list[str] | None = None,
        timeout_seconds: int = 180,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.verify_cmd = verify_cmd or self.DEFAULT_VERIFY_CMD
        self.timeout_seconds = int(timeout_seconds)

    def _safe_path(self, path: str) -> str:
        target = os.path.abspath(
            path if os.path.isabs(path) else os.path.join(self.workspace_dir, path)
        )
        rel = os.path.relpath(target, self.workspace_dir)
        if rel.startswith(".."):
            raise PermissionError(f"Path '{path}' escapes workspace.")
        return target

    @staticmethod
    def _read_text(path: str) -> str:
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _write_text(path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _diff(old: str, new: str, path: str) -> str:
        return "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=3,
            )
        )

    def apply_and_verify(
        self, path: str, new_content: str, verify_cmd: list[str] | None = None
    ) -> PatchResult:
        t0 = time.perf_counter()
        target = self._safe_path(path)
        old_content = self._read_text(target)
        diff = self._diff(old_content, new_content, os.path.relpath(target, self.workspace_dir))

        backup_path = target + ".viki_pv_backup"
        if os.path.isfile(target):
            shutil.copy2(target, backup_path)
        try:
            self._write_text(target, new_content)
            verify = self._run_verify(verify_cmd or self.verify_cmd)
            passed = verify["exit"] == 0
            if not passed:
                self._rollback(target, backup_path, old_content)
                return PatchResult(
                    path=target,
                    passed=False,
                    diff=diff,
                    verify_stdout=verify["stdout"],
                    verify_stderr=verify["stderr"],
                    verify_exit=verify["exit"],
                    duration_seconds=time.perf_counter() - t0,
                    rolled_back=True,
                )
            return PatchResult(
                path=target,
                passed=True,
                diff=diff,
                verify_stdout=verify["stdout"],
                verify_stderr=verify["stderr"],
                verify_exit=verify["exit"],
                duration_seconds=time.perf_counter() - t0,
            )
        except Exception as e:
            self._rollback(target, backup_path, old_content)
            return PatchResult(
                path=target,
                passed=False,
                diff=diff,
                verify_stderr=f"Patch failed: {e}",
                verify_exit=-1,
                duration_seconds=time.perf_counter() - t0,
                rolled_back=True,
            )
        finally:
            if os.path.isfile(backup_path):
                try:
                    os.unlink(backup_path)
                except OSError:
                    pass

    def _run_verify(self, cmd: list[str]) -> dict[str, Any]:
        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        viki_logger.info("PatchVerify: running `%s` in %s", cmd_str, self.workspace_dir)
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            return {
                "exit": proc.returncode,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
            }
        except subprocess.TimeoutExpired:
            return {
                "exit": -1,
                "stdout": "",
                "stderr": f"verify timeout after {self.timeout_seconds}s",
            }
        except FileNotFoundError as e:
            return {"exit": -1, "stdout": "", "stderr": f"verify command not found: {e}"}

    def _rollback(self, target: str, backup_path: str, old_content: str) -> None:
        try:
            if os.path.isfile(backup_path):
                shutil.copy2(backup_path, target)
            else:
                # File didn't exist before — remove what we wrote.
                if os.path.isfile(target) and not old_content:
                    os.unlink(target)
                else:
                    self._write_text(target, old_content)
            viki_logger.info("PatchVerify: rolled back %s", target)
        except Exception as e:
            viki_logger.error("PatchVerify: rollback failed for %s: %s", target, e)
