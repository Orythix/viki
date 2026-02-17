import subprocess
import asyncio
import re
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger
from viki.core.safety import safe_for_log

class ShellSkill(BaseSkill):
    """
    Execute shell commands (PowerShell/CMD).
    Capabilities: System queries, file operations, network checks.
    
    SECURITY: Uses allowlist for safe commands and requires confirmation for destructive operations.
    """
    
    # --- SECURITY FIX: CRIT-003 - Allowlist-based command filtering ---
    
    # Safe command patterns (read-only, informational)
    SAFE_PATTERNS = [
        # PowerShell Get-* commands (read-only)
        r'^Get-\w+$',
        r'^Get-Service\s',
        r'^Get-Process\s',
        r'^Get-ChildItem',
        r'^Get-Content\s',
        r'^Get-Location$',
        r'^Get-Date$',
        r'^Get-Host$',
        r'^Get-History$',
        r'^Get-Command\s',
        r'^Get-Help\s',
        r'^Get-NetIPAddress',
        r'^Get-NetRoute',
        r'^Get-NetTCPConnection',
        r'^Test-Connection\s',  # Ping
        r'^Test-NetConnection',
        
        # CMD/Unix style read commands
        r'^dir\s',
        r'^ls\s',
        r'^ls$',
        r'^cat\s',
        r'^type\s',
        r'^pwd$',
        r'^cd\s',
        r'^echo\s',
        r'^whoami$',
        r'^hostname$',
        r'^date$',
        r'^time$',
        r'^ping\s',
        r'^ipconfig',
        r'^netstat\s',
        r'^systeminfo',
        r'^tasklist',
        r'^where\s',
        r'^which\s',
        r'^python\s--version',
        r'^python\s-V$',
        r'^node\s--version',
        r'^npm\s--version',
        r'^git\s--version',
        r'^git\sstatus',
        r'^git\sbranch',
        r'^git\slog\s',
        r'^git\sremote\s-v$',
    ]
    
    # Destructive patterns that ALWAYS require confirmation
    DESTRUCTIVE_PATTERNS = [
        # File deletion
        r'Remove-Item', r'del\s', r'rm\s', r'rmdir', r'rd\s',
        r'erase', r'wipe', r'shred',
        # Disk operations
        r'format\s', r'clean\s', r'clear-disk',
        # System modification
        r'Set-Service', r'Stop-Service', r'Start-Service',
        r'Stop-Process', r'kill\s', r'taskkill',
        r'Set-ExecutionPolicy',
        # File writing (could be used maliciously)
        r'Set-Content', r'Add-Content', r'Out-File',
        r'New-Item', r'mkdir\s', r'copy\s', r'move\s',
        r'Rename-Item', r'Move-Item', r'Copy-Item',
        # Network modification
        r'New-NetIPAddress', r'Remove-NetIPAddress',
        # Registry
        r'Reg\sDelete', r'Reg\sAdd',
        # Service control
        r'sc\sdelete', r'sc\sconfig',
        # Process termination
        r'taskkill', r'pkill', r'killall',
    ]
    
    # Always blocked patterns (extremely dangerous)
    FORBIDDEN_PATTERNS = [
        r'rm\s-rf\s/',           # Recursive delete root
        r'rm\s-rf\s\*',          # Recursive delete all
        r'del\s/s\s/q\s[cC]:',   # Force delete drive
        r'rd\s/s\s/q',           # Recursive directory delete
        r'format\s[cC]:',        # Format drive
        r'\|\s*sh',              # Pipe to shell
        r'\|\s*bash',            # Pipe to bash
        r'\|\s*cmd',             # Pipe to cmd
        r'>\s*/dev/',            # Redirect to device
        r'mkfs',                 # Make filesystem
        r'dd\sif=',              # Disk dump
        r':()\s*{\s*:\s*:\s*}',  # Fork bomb
        r'chmod\s-R\s*777',      # Recursive full permissions
        r'chown\s-R',            # Recursive ownership change
    ]

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Execute shell commands with security validation. Use with caution. Action: execute(command, shell='powershell')."

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

    def _classify_command(self, command: str) -> str:
        """Classify command as 'safe', 'destructive', or 'forbidden'."""
        command_lower = command.lower()
        # Check forbidden patterns first (e.g. "x; rm -rf /" must stay forbidden)
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, command_lower, re.IGNORECASE):
                return "forbidden"
        # Command chaining can combine safe + destructive; treat as at least destructive (requires confirmation)
        if ";" in command or "&&" in command or "||" in command or (command.strip() and "|" in command):
            return "destructive"
        # Check if command matches safe patterns
        for pattern in self.SAFE_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return "safe"
        
        # Check destructive patterns
        for pattern in self.DESTRUCTIVE_PATTERNS:
            if re.search(pattern, command_lower, re.IGNORECASE):
                return "destructive"
        
        # Unknown command - treat as medium risk
        return "unknown"

    async def execute(self, params: Dict[str, Any]) -> str:
        command = params.get('command')
        shell_type = params.get('shell', 'powershell')
        skip_confirmation = params.get('skip_confirmation', False)

        if not command:
            return "Error: No command provided."

        # Classify the command
        classification = self._classify_command(command)
        
        if classification == "forbidden":
            viki_logger.warning(f"Shell: Blocked forbidden command pattern: {safe_for_log(command)}")
            return "Safety Block: Command matches forbidden pattern and cannot be executed."
        
        if classification == "destructive" and not skip_confirmation:
            viki_logger.warning(f"Shell: Destructive command requires confirmation: {safe_for_log(command)}")
            return (
                f"SAFETY CONFIRMATION REQUIRED: This command appears to be destructive.\n"
                f"Command: {safe_for_log(command, max_len=200)}\n"
                f"Classification: {classification}\n"
                f"To proceed, the controller must explicitly approve this action."
            )
        
        # Log all shell executions
        viki_logger.info(f"Shell: Executing {classification} command: {safe_for_log(command)}")

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
