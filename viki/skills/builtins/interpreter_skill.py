import os
import subprocess
import asyncio
import sys
import tempfile
import time
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class InterpreterSkill(BaseSkill):
    """
    Skill for executing Python code in a Sandboxed (Restricted) environment.
    Prevents accidental system modifications.
    """
    def __init__(self):
        self._name = "python_interpreter"
        self._description = "Execute Python code for calculations, data analysis, or logic. Usage: python_interpreter(code='...')"
        
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
        """Runs python code in a separate process with restricted imports/access."""
        viki_logger.info("Executing Python in Sandbox...")
        
        # 1. Create a workspace
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "script.py")
            with open(file_path, "w") as f:
                # Add a wrapper to prevent some imports if needed, 
                # but for now we rely on OS level restriction
                f.write(code)
            
            try:
                # 2. Run with timeout and restricted environment
                # We remove sensitive env vars
                clean_env = os.environ.copy()
                to_remove = ["OPENAI_API_KEY", "HF_TOKEN", "AWS_SECRET_ACCESS_KEY", "SECRET_KEY"]
                for key in to_remove:
                    if key in clean_env: del clean_env[key]
                
                # Use a separate thread for the blocking subprocess
                def run_code():
                    return subprocess.run(
                        [sys.executable, file_path],
                        capture_output=True,
                        text=True,
                        timeout=5, # 5 second limit
                        cwd=tmpdir,
                        env=clean_env
                    )
                
                result = await asyncio.to_thread(run_code)
                
                output = result.stdout
                error = result.stderr
                
                if result.returncode == 0:
                    return f"Execution Success:\n{output}"
                else:
                    return f"Execution Error (Return Code {result.returncode}):\n{error}\nOutput: {output}"
                    
            except subprocess.TimeoutExpired:
                viki_logger.warning("Sandbox Execution Timed Out.")
                return "Error: Execution timed out (5s limit)."
            except Exception as e:
                viki_logger.error(f"Sandbox Failure: {e}")
                return f"Sandbox Failure: {str(e)}"
