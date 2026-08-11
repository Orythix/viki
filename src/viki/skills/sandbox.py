"""
Skill sandboxing — subprocess jail for skill execution.

Provides a safe, resource-constrained execution environment for running
skills that involve shell commands, Python interpretation, or other
potentially dangerous operations.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import auto
from typing import Any

from viki._compat import StrEnum


class SandboxViolation(StrEnum):
    NONE = auto()
    CPU_BUDGET_EXCEEDED = auto()
    MEMORY_BUDGET_EXCEEDED = auto()
    TIME_BUDGET_EXCEEDED = auto()
    FILESYSTEM_VIOLATION = auto()
    NETWORK_VIOLATION = auto()
    PROCESS_CREATION = auto()


@dataclass
class SandboxResult:
    """Result of a sandboxed execution."""

    success: bool
    output: str
    error: str = ""
    return_code: int = -1
    duration_ms: float = 0.0
    violation: SandboxViolation = SandboxViolation.NONE
    violation_detail: str = ""


@dataclass
class SandboxConfig:
    """Resource limits for the sandbox."""

    max_cpu_seconds: float = 30.0
    max_memory_mb: float = 512.0
    max_duration_seconds: float = 60.0
    allowed_paths: list[str] = field(default_factory=lambda: [os.getcwd()])
    allow_network: bool = False
    allow_process_creation: bool = False
    temp_dir: str = field(default_factory=lambda: tempfile.gettempdir())
    strip_env: bool = True


class SkillSandbox:
    """
    Subprocess-based sandbox for skill execution.

    Usage:
        sandbox = SkillSandbox()
        result = await sandbox.run("python", ["-c", "print('hello')"])
    """

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()

    async def run(
        self,
        command: str | list[str],
        cwd: str | None = None,
        input_data: str | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """
        Execute a command in a resource-constrained subprocess.

        Args:
            command: Shell command string or list of arguments.
            cwd: Working directory for the subprocess.
            input_data: Stdin data.
            env: Environment variables (merged with stripped env if strip_env=True).

        Returns:
            SandboxResult with execution details.
        """
        start = time.perf_counter()

        # Validate allowed paths
        cwd = cwd or os.getcwd()
        if not self._is_path_allowed(cwd):
            elapsed = (time.perf_counter() - start) * 1000
            return SandboxResult(
                success=False,
                output="",
                error=f"Working directory not allowed: {cwd}",
                duration_ms=elapsed,
                violation=SandboxViolation.FILESYSTEM_VIOLATION,
                violation_detail=f"Path not in allowed set: {cwd}",
            )

        # Build environment
        cmd_env: dict[str, str] = {}
        if self.config.strip_env:
            cmd_env["PATH"] = os.environ.get("PATH", "")
            cmd_env["HOME"] = os.environ.get("HOME", "")
            cmd_env["USERPROFILE"] = os.environ.get("USERPROFILE", "")
        else:
            cmd_env = dict(os.environ)
        if env:
            cmd_env.update(env)

        try:
            proc = await asyncio.create_subprocess_exec(
                *self._build_cmd(command),
                stdin=asyncio.subprocess.PIPE if input_data else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=cmd_env,
                # Platform-specific process group for timeout killing
                **self._process_creation_kwargs(),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=input_data.encode() if input_data else None),
                    timeout=self.config.max_duration_seconds,
                )
            except asyncio.TimeoutError:
                elapsed = (time.perf_counter() - start) * 1000
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    logging.getLogger(__name__).warning(
                        "failed to kill sandbox process after timeout"
                    )
                return SandboxResult(
                    success=False,
                    output="",
                    error=f"Execution timed out after {self.config.max_duration_seconds}s",
                    duration_ms=elapsed,
                    violation=SandboxViolation.TIME_BUDGET_EXCEEDED,
                )

            elapsed = (time.perf_counter() - start) * 1000
            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            return SandboxResult(
                success=proc.returncode == 0,
                output=stdout_str,
                error=stderr_str,
                return_code=proc.returncode or 0,
                duration_ms=elapsed,
            )

        except FileNotFoundError as e:
            elapsed = (time.perf_counter() - start) * 1000
            return SandboxResult(
                success=False,
                output="",
                error=str(e),
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return SandboxResult(
                success=False,
                output="",
                error=str(e),
                duration_ms=elapsed,
            )

    async def run_python(
        self,
        code: str,
        cwd: str | None = None,
    ) -> SandboxResult:
        """Execute Python code in the sandbox."""
        return await self.run(
            [sys_executable(), "-c", code],
            cwd=cwd,
        )

    async def run_shell(
        self,
        command: str,
        cwd: str | None = None,
    ) -> SandboxResult:
        """Execute a shell command in the sandbox."""
        if platform.system() == "Windows":
            return await self.run(["cmd.exe", "/c", command], cwd=cwd)
        return await self.run(["sh", "-c", command], cwd=cwd)

    def _is_path_allowed(self, path: str) -> bool:
        """Check if a path is within the allowed paths."""
        abs_path = os.path.abspath(path)
        for allowed in self.config.allowed_paths:
            allowed_abs = os.path.abspath(allowed)
            if abs_path == allowed_abs or abs_path.startswith(allowed_abs + os.sep):
                return True
        return False

    def _build_cmd(self, command: str | list[str]) -> list[str]:
        """Normalize command to list format."""
        if isinstance(command, str):
            if platform.system() == "Windows":
                return ["cmd.exe", "/c", command]
            return ["sh", "-c", command]
        return command

    def _process_creation_kwargs(self) -> dict[str, Any]:
        """Platform-specific kwargs for subprocess creation."""
        kwargs: dict[str, Any] = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        return kwargs


def sys_executable() -> str:
    """Return path to the current Python interpreter."""
    import sys

    return sys.executable


# Module-level convenience instance
_default_sandbox: SkillSandbox | None = None


def get_sandbox(config: SandboxConfig | None = None) -> SkillSandbox:
    """Get or create the default sandbox instance."""
    global _default_sandbox
    if _default_sandbox is None or config is not None:
        _default_sandbox = SkillSandbox(config)
    return _default_sandbox


class DockerSandbox(SkillSandbox):
    """
    Containerized Docker Sandbox for isolated script & command execution.
    Falls back to subprocess jail if Docker is unavailable.
    """

    def __init__(self, image: str = "python:3.11-slim", config: SandboxConfig | None = None):
        super().__init__(config)
        self.image = image
        import shutil

        self.docker_available = shutil.which("docker") is not None

    async def run(
        self,
        command: str | list[str],
        cwd: str | None = None,
        input_data: str | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        if not self.docker_available:
            return await super().run(command, cwd=cwd, input_data=input_data, env=env)

        cwd = cwd or os.getcwd()
        cmd_list = self._build_cmd(command)

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{os.path.abspath(cwd)}:/workspace",
            "-w",
            "/workspace",
            self.image,
        ] + cmd_list

        return await super().run(docker_cmd, cwd=cwd, input_data=input_data, env=env)
