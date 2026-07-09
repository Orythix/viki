"""
Kubernetes control skill (dynamic / Phase 4).

Read-only `kubectl get/describe/logs` wrapper. Shells out to kubectl
(reusing the user's local config) so the agent does not need a Python
kubernetes client. Write/apply operations are explicitly rejected; promote to
"shell_exec" capability if you need full control.
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from viki.skills.base import BaseSkill

_ALLOWED_VERBS = {"get", "describe", "logs", "top", "version", "explain"}


class KubernetesCtlSkill(BaseSkill):
    """Read-only kubectl wrapper."""

    def __init__(self, controller=None):
        self.controller = controller

    @property
    def name(self) -> str:
        return "kubernetes_ctl"

    @property
    def description(self) -> str:
        return (
            "Read-only kubectl bridge. Params: verb (get|describe|logs|top|version|explain), "
            "args (list[str], optional), namespace (str, optional)."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "verb": {"type": "string", "enum": sorted(_ALLOWED_VERBS)},
                "args": {"type": "array", "items": {"type": "string"}},
                "namespace": {"type": "string"},
            },
            "required": ["verb"],
        }

    @property
    def safety_tier(self) -> str:
        return "safe"

    async def execute(self, params: dict[str, Any]) -> str:
        verb = (params.get("verb") or "").strip().lower()
        if verb not in _ALLOWED_VERBS:
            return f"Error: verb must be one of {sorted(_ALLOWED_VERBS)}."
        args = params.get("args") or []
        if not isinstance(args, list) or not all(isinstance(a, str | int | float) for a in args):
            return "Error: 'args' must be a list of strings/numbers."
        namespace = params.get("namespace")
        follow = bool(params.get("follow", False))
        try:
            tail_lines = int(params.get("tail_lines", 200))
        except (TypeError, ValueError):
            tail_lines = 200
        try:
            timeout = max(1, min(int(params.get("timeout", 30)), 600))
        except (TypeError, ValueError):
            timeout = 30
        try:
            max_bytes = max(1024, min(int(params.get("max_bytes", 60_000)), 200_000))
        except (TypeError, ValueError):
            max_bytes = 60_000

        kubectl = shutil.which("kubectl")
        if kubectl is None:
            return "Error: kubectl not found on PATH."

        cmd = [kubectl, verb] + [str(a) for a in args]
        if verb == "logs":
            cmd += ["--tail", str(max(1, tail_lines))]
            if follow:
                cmd += ["--follow"]
        if namespace:
            cmd += ["-n", str(namespace)]

        try:
            if verb == "logs" and follow:
                return await self._stream(cmd, timeout=timeout, max_bytes=max_bytes)
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out = stdout.decode("utf-8", "ignore")
            err = stderr.decode("utf-8", "ignore")
            ok = proc.returncode == 0
            tail = out if ok else (out + "\n" + err)
            return (
                tail[:max_bytes] if tail else ("ok" if ok else f"kubectl exited {proc.returncode}")
            )
        except TimeoutError:
            return "kubernetes_ctl error: kubectl command timed out."
        except Exception as e:
            return f"kubernetes_ctl error: {e}"

    @staticmethod
    async def _stream(cmd, timeout: int, max_bytes: int) -> str:
        """Bounded streaming reader for `kubectl logs --follow`."""
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        chunks = []
        total = 0
        try:

            async def reader():
                nonlocal total
                assert proc.stdout is not None
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    chunks.append(line.decode("utf-8", "ignore"))
                    total += len(line)
                    if total >= max_bytes:
                        break

            await asyncio.wait_for(reader(), timeout=timeout)
        except TimeoutError:
            chunks.append("\n[stream truncated by timeout]")
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except Exception:
                pass
        return ("".join(chunks))[:max_bytes]
