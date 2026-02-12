import subprocess
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class ShellSkill(BaseSkill):
    """
    Execute shell commands (PowerShell/CMD).
    Capabilities: System queries, file operations, network checks.
    """
    
    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Execute shell commands. Use with caution. Action: execute(command, shell='powershell')."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to execute"
                },
                "shell": {
                    "type": "string",
                    "enum": ["powershell", "cmd"],
                    "description": "Shell to use (default: powershell)",
                    "default": "powershell"
                }
            },
            "required": ["command"]
        }

    @property
    def safety_tier(self) -> str:
        return "destructive"  # High risk

    async def execute(self, params: Dict[str, Any]) -> str:
        command = params.get('command')
        shell_type = params.get('shell', 'powershell')

        if not command:
            return "Error: No command provided."

        # basic safety filter
        forbidden = ["format ", "rm -rf", "del /s /q c:", "rd /s /q c:"]
        if any(f in command.lower() for f in forbidden):
            return f"Safety Block: Command contains forbidden pattern."

        try:
            # Construct the shell invocation
            if shell_type == 'powershell':
                # -NoProfile ensures faster startup
                full_cmd = ["powershell", "-NoProfile", "-Command", command]
            else:
                # cmd /c
                full_cmd = ["cmd", "/c", command]

            # Run strictly with capture
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            output = stdout.decode('utf-8', errors='replace').strip()
            error = stderr.decode('utf-8', errors='replace').strip()
            
            if process.returncode != 0:
                return f"Command Failed (Exit Code {process.returncode}):\n{error}\n{output}"
            
            return output if output else "(Command executed with no output)"

        except Exception as e:
            viki_logger.error(f"Shell execution error: {e}")
            return f"Shell error: {e}"
