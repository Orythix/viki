"""
P1: sandboxed execution backends.

Two paths:

  1. **Docker** (`DockerSandbox`): runs the user code inside a container
     based on `python:3.11-slim` (configurable). Network is disabled, the
     workspace mounts as `/workspace`, and a CPU/memory cap is applied.
     Activated by `VIKI_DOCKER_SANDBOX=1` or `viki.config.settings.skills.python_interpreter.docker = true`.
  2. **Subprocess fallback**: the existing behaviour. Used when Docker isn't
     available or the user disables the sandbox flag.

The runner returns a uniform `SandboxResult` so callers (InterpreterSkill,
ShellSkill) don't have to special-case the backend.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from typing import Dict, List, Optional

from viki.config.logger import viki_logger


@dataclass
class SandboxResult:
    backend: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class _BaseSandbox:
    backend: str = "abstract"

    async def run_python(self, code: str, timeout: int) -> SandboxResult:
        raise NotImplementedError

    async def run_shell(self, command: str, timeout: int) -> SandboxResult:
        raise NotImplementedError


class SubprocessSandbox(_BaseSandbox):
    backend = "subprocess"

    def __init__(self, workspace_dir: Optional[str] = None):
        self.workspace_dir = workspace_dir

    async def run_python(self, code: str, timeout: int) -> SandboxResult:
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "script.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write(code)
            return await self._run([sys.executable, script], timeout, cwd=tmp)

    async def run_shell(self, command: str, timeout: int) -> SandboxResult:
        return await self._run(["bash", "-lc", command], timeout, cwd=self.workspace_dir)

    async def _run(self, argv: List[str], timeout: int, cwd: Optional[str]) -> SandboxResult:
        clean_env = os.environ.copy()
        for key in ("OPENAI_API_KEY", "HF_TOKEN", "AWS_SECRET_ACCESS_KEY", "SECRET_KEY", "VIKI_API_KEY"):
            clean_env.pop(key, None)

        def _run_sync() -> SandboxResult:
            try:
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                    env=clean_env,
                )
                return SandboxResult(self.backend, proc.returncode, proc.stdout, proc.stderr)
            except subprocess.TimeoutExpired as e:
                return SandboxResult(self.backend, 124, e.stdout or "", "timed out", timed_out=True)
            except Exception as e:
                return SandboxResult(self.backend, 1, "", str(e))

        return await asyncio.to_thread(_run_sync)


class DockerSandbox(_BaseSandbox):
    """
    Runs code inside a one-shot container.

    By default we use `python:3.11-slim`, mount the workspace at /workspace,
    drop the network (`--network none`), and cap CPU/memory. The image can
    be customised via the constructor or `VIKI_SANDBOX_IMAGE` env var.
    """

    backend = "docker"

    def __init__(
        self,
        workspace_dir: Optional[str] = None,
        image: Optional[str] = None,
        cpu_limit: float = 1.0,
        memory_limit: str = "512m",
        allow_network: bool = False,
    ):
        self.workspace_dir = workspace_dir
        self.image = image or os.environ.get("VIKI_SANDBOX_IMAGE", "python:3.11-slim")
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.allow_network = allow_network

    @staticmethod
    def is_available() -> bool:
        return shutil.which("docker") is not None

    def _docker_args(self, mount_target: str) -> List[str]:
        args = [
            "docker", "run", "--rm",
            "--cpus", str(self.cpu_limit),
            "--memory", self.memory_limit,
            "--read-only",  # protect host fs; /workspace is rw mount
        ]
        if not self.allow_network:
            args += ["--network", "none"]
        if mount_target:
            args += ["-v", f"{mount_target}:/workspace:rw"]
            args += ["-w", "/workspace"]
        return args

    async def run_python(self, code: str, timeout: int) -> SandboxResult:
        if not self.is_available():
            viki_logger.warning("DockerSandbox: docker not installed; falling back to subprocess.")
            return await SubprocessSandbox(self.workspace_dir).run_python(code, timeout)

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "script.py"), "w", encoding="utf-8") as f:
                f.write(code)
            argv = self._docker_args(tmp) + [self.image, "python", "/workspace/script.py"]
            return await self._run(argv, timeout)

    async def run_shell(self, command: str, timeout: int) -> SandboxResult:
        if not self.is_available():
            return await SubprocessSandbox(self.workspace_dir).run_shell(command, timeout)
        mount = self.workspace_dir or os.getcwd()
        argv = self._docker_args(mount) + [self.image, "bash", "-lc", command]
        return await self._run(argv, timeout)

    async def _run(self, argv: List[str], timeout: int) -> SandboxResult:
        def _run_sync() -> SandboxResult:
            try:
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                return SandboxResult(self.backend, proc.returncode, proc.stdout, proc.stderr)
            except subprocess.TimeoutExpired as e:
                return SandboxResult(self.backend, 124, e.stdout or "", "timed out", timed_out=True)
            except Exception as e:
                return SandboxResult(self.backend, 1, "", str(e))

        return await asyncio.to_thread(_run_sync)


def get_sandbox(controller=None, workspace_dir: Optional[str] = None) -> _BaseSandbox:
    """
    Pick the active sandbox backend.

    Order:
      1. settings.skills.python_interpreter.docker = true / env VIKI_DOCKER_SANDBOX=1
      2. SubprocessSandbox (default; current behaviour).
    """
    use_docker = False
    try:
        if controller is not None:
            cfg = controller.settings.get("skills", {}).get("python_interpreter", {})
            use_docker = bool(cfg.get("docker"))
    except Exception:
        use_docker = False
    if not use_docker and os.environ.get("VIKI_DOCKER_SANDBOX", "").lower() in ("1", "true", "yes"):
        use_docker = True
    if use_docker:
        if DockerSandbox.is_available():
            return DockerSandbox(workspace_dir=workspace_dir)
        viki_logger.warning("get_sandbox: Docker requested but not available; using subprocess.")
    return SubprocessSandbox(workspace_dir=workspace_dir)
