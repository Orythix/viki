import asyncio
import os
import shutil
import subprocess
from typing import Any

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


class ReverseEngineeringSkill(BaseSkill):
    """
    Tools for binary analysis and reverse engineering.
    Provides access to strings, ldd, nm, and objdump.
    """

    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller

    @property
    def name(self) -> str:
        return "reverse_engineering"

    @property
    def description(self) -> str:
        return (
            "Tools for binary analysis and reverse engineering.\n"
            "Actions:\n"
            "- strings(path): Extract printable strings from a binary.\n"
            "- ldd(path): List dynamic dependencies.\n"
            "- nm(path): List symbols from object files.\n"
            "- objdump(path, flags): Display information from object files."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["strings", "ldd", "nm", "objdump"],
                    "description": "RE action to perform",
                },
                "path": {"type": "string", "description": "Path to the binary file"},
                "flags": {
                    "type": "string",
                    "description": "Optional flags for objdump (e.g., '-d' for disassemble)",
                },
            },
            "required": ["action", "path"],
        }

    async def execute(self, params: dict[str, Any]) -> str:
        action = params.get("action")
        path = params.get("path")
        flags = params.get("flags", "")

        if not path:
            return "Error: path is required."

        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return f"Error: File '{path}' not found."

        if shutil.which(action) is None:
            return f"Error: Tool '{action}' is not installed on this system."

        try:
            cmd = [action]
            if action == "objdump" and flags:
                cmd.extend(flags.split())
            cmd.append(abs_path)

            viki_logger.info(f"RE: Running {' '.join(cmd)}")
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=30
            )

            output = result.stdout or result.stderr
            if len(output) > 5000:
                output = output[:5000] + "\n... (truncated)"

            return f"RE RESULTS for {action} {path}:\n{output}"

        except Exception as e:
            viki_logger.error(f"ReverseEngineering Error: {e}")
            return f"RE operation failed: {str(e)}"
