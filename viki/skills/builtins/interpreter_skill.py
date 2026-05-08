import os
import subprocess
import asyncio
import sys
import tempfile
from typing import Dict, Any, Optional
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

DEFAULT_INTERPRETER_TIMEOUT = 30
MAX_INTERPRETER_TIMEOUT = 120


class InterpreterSkill(BaseSkill):
    """
    Skill for executing Python code in a Sandboxed (Restricted) environment.
    Prevents accidental system modifications.
    """
    def __init__(self, controller=None):
        self._name = "python_interpreter"
        self._controller = controller
        self._description = "Execute Python code for calculations, data analysis, or logic. Usage: python_interpreter(code='...')"

    def _get_timeout(self) -> int:
        """Timeout in seconds; from settings, env, or default. Capped at MAX_INTERPRETER_TIMEOUT."""
        if self._controller and getattr(self._controller, "settings", None):
            cfg = self._controller.settings.get("skills", {}).get("python_interpreter", {})
            val = cfg.get("timeout_seconds")
            if val is not None:
                return min(MAX_INTERPRETER_TIMEOUT, max(1, int(val)))
        try:
            val = int(os.environ.get("VIKI_INTERPRETER_TIMEOUT", DEFAULT_INTERPRETER_TIMEOUT))
            return min(MAX_INTERPRETER_TIMEOUT, max(1, val))
        except (TypeError, ValueError):
            return DEFAULT_INTERPRETER_TIMEOUT
        
    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    async def execute(self, params: Dict[str, Any]) -> str:
        code = params.get("code")
        if not code:
            return "Error: No 'code' provided."
            
        return await self._execute_sandboxed(code)

    async def _execute_sandboxed(self, code: str) -> str:
        """Runs python code via the configured sandbox backend (docker or subprocess)."""
        from viki.core.sandbox import get_sandbox

        viki_logger.info("Executing Python in Sandbox...")
        timeout_sec = self._get_timeout()
        sandbox = get_sandbox(self._controller)
        result = await sandbox.run_python(code, timeout=timeout_sec)
        if result.timed_out:
            return f"Error: Execution timed out ({timeout_sec}s limit) [{sandbox.backend}]."
        if result.exit_code == 0:
            return f"Execution Success [{sandbox.backend}]:\n{result.stdout}"
        return (
            f"Execution Error (Return Code {result.exit_code}) [{sandbox.backend}]:\n"
            f"{result.stderr}\nOutput: {result.stdout}"
        )
