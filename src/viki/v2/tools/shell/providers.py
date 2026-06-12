"""Shell provider abstraction."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ShellResult:
    returncode: int
    stdout: str
    stderr: str


class ShellProvider(ABC):
    """Abstract shell command execution."""

    @abstractmethod
    async def run(self, command: str, workdir: str | None = None, timeout: int = 30) -> ShellResult:
        ...

    @abstractmethod
    async def stream(self, command: str, workdir: str | None = None, callback=None) -> ShellResult:
        ...


class LocalShellProvider(ShellProvider):
    """Local shell provider using asyncio subprocess."""

    def __init__(self):
        import sys

        self._shell = "powershell.exe" if sys.platform == "win32" else "bash"
        self._args = ["-Command"] if sys.platform == "win32" else ["-c"]

    async def run(self, command: str, workdir: str | None = None, timeout: int = 30) -> ShellResult:
        proc = await asyncio.create_subprocess_exec(
            self._shell,
            *self._args,
            command,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ShellResult(returncode=-1, stdout="", stderr=f"Timeout after {timeout}s")

        return ShellResult(
            returncode=proc.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )

    async def stream(self, command: str, workdir: str | None = None, callback=None) -> ShellResult:
        proc = await asyncio.create_subprocess_exec(
            self._shell,
            *self._args,
            command,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_chunks = []
        stderr_chunks = []

        async def read_stream(stream, chunks, prefix=""):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace")
                chunks.append(decoded)
                if callback:
                    await callback(prefix + decoded)

        await asyncio.gather(
            read_stream(proc.stdout, stdout_chunks, "[stdout] "),
            read_stream(proc.stderr, stderr_chunks, "[stderr] "),
        )

        await proc.wait()
        return ShellResult(
            returncode=proc.returncode or 0,
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
        )
