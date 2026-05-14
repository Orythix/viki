import os
import shutil
import tempfile
import asyncio
from typing import Dict, Any, List, Optional
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class MutationPilotSkill(BaseSkill):
    """
    Skill for mutation benchmarking.
    Injects synthetic faults into code to verify that the test suite is capable
    of catching regression or logic errors.
    """
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller

    @property
    def name(self) -> str:
        return "mutation_pilot"

    @property
    def description(self) -> str:
        return "Runs mutation benchmarks to test suite robustness. Actions: benchmark, mutate."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["benchmark", "mutate", "heal"],
                    "description": "Mutation action"
                },
                "path": {
                    "type": "string",
                    "description": "Path to the file to mutate (or heal)"
                },
                "test_command": {
                    "type": "string",
                    "description": "Command to run tests (e.g., 'pytest viki/tests/test_x.py')"
                },
                "error_log": {
                    "type": "string",
                    "description": "The failure log/error message for the heal action"
                }
            },
            "required": ["action", "path"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        path = params.get("path")
        test_cmd = params.get("test_command")
        error_log = params.get("error_log")
        
        if not path:
            return "Error: Path is required."
            
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return f"Error: Path '{path}' not found."

        try:
            if action == "mutate":
                return self._generate_mutant(abs_path)
            elif action == "benchmark":
                if not test_cmd:
                    return "Error: 'test_command' is required for benchmark action."
                return await self._run_benchmark(abs_path, test_cmd)
            elif action == "heal":
                if not error_log:
                    return "Error: 'error_log' is required for heal action."
                return await self._run_heal(abs_path, error_log, test_cmd)
            
            return f"Error: Unknown action '{action}'"
        except Exception as e:
            viki_logger.error(f"MutationPilot Error: {e}")
            return f"Mutation Failed: {str(e)}"

    def _generate_mutant(self, path: str) -> str:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Simple mutations: swap operators
        mutations = [
            (" == ", " != "),
            (" != ", " == "),
            (" > ", " < "),
            (" < ", " > "),
            ("True", "False"),
            ("False", "True"),
            (" and ", " or "),
            (" or ", " and ")
        ]
        
        mutant_content = content
        mutated = False
        for old, new in mutations:
            if old in mutant_content:
                mutant_content = mutant_content.replace(old, new, 1) # Only first one
                mutated = True
                mutation_desc = f"Swapped '{old}' with '{new}'"
                break
        
        if not mutated:
            return "Could not find any candidates for mutation in this file."
            
        # Write to temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".py", prefix="mutant_")
        with os.fdopen(temp_fd, 'w') as f:
            f.write(mutant_content)
            
        return f"MUTANT_CREATED: {temp_path}\nDescription: {mutation_desc}"

    async def _run_benchmark(self, path: str, test_command: str) -> str:
        # 1. Verify tests pass on ORIGINAL file
        viki_logger.info("MutationPilot: Verifying base state...")
        base_proc = await asyncio.create_subprocess_shell(
            test_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await base_proc.communicate()
        if base_proc.returncode != 0:
            return f"Error: Test suite fails on the ORIGINAL file. Fix tests before benchmarking."

        # 2. Generate mutant
        mutant_info = self._generate_mutant(path)
        if "MUTANT_CREATED" not in mutant_info:
            return mutant_info
        
        mutant_path = mutant_info.split(": ")[1].split("\n")[0]
        
        # 3. Swap file and run tests
        backup_path = path + ".bak"
        shutil.copy2(path, backup_path)
        shutil.copy(mutant_path, path) # Use copy instead of copy2 to update timestamp (vital for Python imports)
        
        try:
            viki_logger.info(f"MutationPilot: Testing mutant version of {os.path.basename(path)}...")
            proc = await asyncio.create_subprocess_shell(
                test_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            
            # 4. Results
            if proc.returncode == 0:
                # Mutant SURVIVED (Test suite is weak)
                result = "MUTANT_SURVIVED: The test suite passed even with the bug injected. The tests are NOT robust enough."
            else:
                # Mutant KILLED (Test suite is strong)
                result = "MUTANT_KILLED: The test suite correctly identified the bug. The tests are robust."
            
            return f"--- Mutation Benchmark Result ---\nTarget: {os.path.basename(path)}\n{result}\n\nTest Output Snippet:\n{stdout.decode()[:200]}..."

        finally:
            # Restore original
            shutil.move(backup_path, path)
            if os.path.exists(mutant_path):
                os.remove(mutant_path)

    async def _run_heal(self, path: str, error_log: str, test_command: Optional[str] = None) -> str:
        """Autonomous healing: Propose a patch for a failing file."""
        if not self._controller:
            return "Error: Skill not connected to controller."

        viki_logger.info(f"MutationPilot: Attempting to heal {os.path.basename(path)}...")
        
        # Read the file content
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Build heal prompt
        prompt = (
            f"I need to fix a bug in the following file: {path}\n\n"
            f"FILE CONTENT:\n{content}\n\n"
            f"FAILURE LOG:\n{error_log}\n\n"
            f"Propose a PATCH that fixes the issue. Ground your patch in the failure log. "
            f"Reply with the NEW FILE CONTENT in a code block."
        )

        # Call the deliberation layer (Deep) for reasoning
        try:
            resp = await self._controller.cortex.process(
                prompt,
                model_tier="deep", # Use high-quality model for healing
                is_plan_mode=True
            )
            
            # Extract content from response
            new_content = resp.explanation
            if "```" in new_content:
                # Basic code block extraction
                import re
                blocks = re.findall(r"```(?:\w+)?\n(.*?)```", new_content, re.DOTALL)
                if blocks:
                    new_content = blocks[0]

            if not new_content or new_content.strip() == content.strip():
                return "Heal failed: LLM did not propose a meaningful change."

            # Apply the patch (with backup)
            backup_path = path + ".heal_bak"
            shutil.copy2(path, backup_path)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # Verification
            verify_msg = ""
            if test_command:
                viki_logger.info(f"MutationPilot: Verifying heal for {os.path.basename(path)}...")
                proc = await asyncio.create_subprocess_shell(
                    test_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode == 0:
                    os.remove(backup_path)
                    return f"HEAL_SUCCESS: File {os.path.basename(path)} has been patched and verified."
                else:
                    # Rollback
                    shutil.move(backup_path, path)
                    verify_msg = f"\nVerification FAILED. Code rolled back. Test Output:\n{stdout.decode()[:200]}"
                    return f"HEAL_PROPOSED_BUT_FAILED: The patch did not fix the tests.{verify_msg}"
            
            return f"HEAL_APPLIED: File {os.path.basename(path)} updated. (No verification command provided)."

        except Exception as e:
            viki_logger.error(f"Heal process failed: {e}")
            return f"Heal process failed: {str(e)}"
