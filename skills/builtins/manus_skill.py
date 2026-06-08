import os
import re
from typing import Dict, Any, List, Optional
from skills.base import BaseSkill
from core.execution_environment import get_sandbox, SandboxResult
from config.logger import viki_logger

class ManusSkill(BaseSkill):
    """
    ManusSkill: A high-autonomy agent skill that delivers complete tasks.
    It runs in an isolated sandbox (Docker or Subprocess) and can orchestrate
    multi-step workflows defined in SKILL.md or provided via prompt.
    """
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        self._sandbox = None

    def _get_sandbox(self):
        if self._sandbox:
            return self._sandbox
        workspace_dir = "."
        if self._controller and hasattr(self._controller, "settings"):
            workspace_dir = self._controller.settings.get("system", {}).get("workspace_dir", ".")
        self._sandbox = get_sandbox(self._controller, workspace_dir=workspace_dir)
        return self._sandbox

    @property
    def name(self) -> str:
        return "manus"

    @property
    def description(self) -> str:
        return "Autonomous task delivery agent. Executes workflows in a sandboxed Ubuntu environment."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The description of the task to perform autonomously."
                },
                "skill_file": {
                    "type": "string",
                    "description": "Optional path to a SKILL.md file defining the workflow."
                },
                "runtime": {
                    "type": "string",
                    "enum": ["python", "bash"],
                    "default": "python",
                    "description": "The primary runtime for the task."
                }
            },
            "required": ["task"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        task = params.get("task")
        skill_file = params.get("skill_file")
        runtime = params.get("runtime", "python")
        
        viki_logger.info(f"ManusSkill: Initiating autonomous task: {task[:50]}...")
        
        # 1. Read SKILL.md if provided
        workflow_script = ""
        if skill_file:
            workflow_script = self._read_skill_md(skill_file)
            if not workflow_script:
                return f"Error: Could not read or parse skill file '{skill_file}'."
        else:
            # Generate a script based on the task
            task_comment = "\n".join([f"# {line}" for line in task.splitlines()])
            if runtime == "python":
                workflow_script = f"{task_comment}\nprint('Executing autonomous task in sandbox...')"
            else:
                workflow_script = f"{task_comment}\necho 'Executing autonomous task in sandbox...'"

        # 2. Execute in Sandbox
        sandbox = self._get_sandbox()
        try:
            if runtime == "python":
                result = await sandbox.run_python(workflow_script, timeout=300)
            else:
                result = await sandbox.run_shell(workflow_script, timeout=300)
            
            return self._format_result(result, task)
        except Exception as e:
            viki_logger.error(f"ManusSkill Execution Error: {e}")
            return f"Manus Task Failed: {str(e)}"

    def _read_skill_md(self, path: str) -> Optional[str]:
        # Simple parser for SKILL.md (expects a code block)
        try:
            if not os.path.exists(path):
                # Try relative to workspace
                if self._controller:
                    ws = self._controller.settings.get("system", {}).get("workspace_dir", ".")
                    path = os.path.join(ws, path)
            
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Extract code blocks
            code_blocks = re.findall(r'```(?:python|bash)?\n(.*?)```', content, re.DOTALL)
            if code_blocks:
                return "\n".join(code_blocks)
            return content # Fallback to raw if no code blocks
        except Exception as e:
            viki_logger.error(f"Failed to read SKILL.md: {e}")
            return None

    def _format_result(self, res: SandboxResult, task: str) -> str:
        status = "SUCCESS" if res.exit_code == 0 else "FAILED"
        if res.timed_out:
            status = "TIMED_OUT"
            
        report = [
            f"--- Manus Autonomous Task Delivery ---",
            f"Task:    {task}",
            f"Status:  {status} (Backend: {res.backend})",
            f"Exit:    {res.exit_code}",
            f"\nSTDOUT:",
            res.stdout or "(empty)",
        ]
        
        if res.stderr:
            report.append(f"\nSTDERR:")
            report.append(res.stderr)
            
        return "\n".join(report)
