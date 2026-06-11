import asyncio
import os
import re
import shutil
import tempfile
from typing import Any

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


class MutationPilotSkill(BaseSkill):
    """
    Skill for mutation benchmarking and autonomous healing.
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
        return (
            "Mutation testing and autonomous healing. Actions:\n"
            "- benchmark(path=..., test_command=...): Inject bug and verify test suite catch rate.\n"
            "- mutate(path=...): Generate a mutant file for manual inspection.\n"
            "- heal(path=..., error_log=..., test_command=...): Use LLM to automatically fix a failing file."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["benchmark", "mutate", "heal"],
                    "description": "Mutation action",
                },
                "path": {"type": "string", "description": "Path to the file to mutate (or heal)"},
                "test_command": {
                    "type": "string",
                    "description": "Command to run tests (e.g., 'pytest viki/tests/test_x.py')",
                },
                "error_log": {
                    "type": "string",
                    "description": "The failure log/error message for the heal action",
                },
            },
            "required": ["action", "path"],
        }

    async def execute(self, params: dict[str, Any]) -> str:
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
        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Industrial mutations: swap operators, invert logic, or break returns
        mutations = [
            (r" == ", " != "),
            (r" != ", " == "),
            (r" > ", " < "),
            (r" < ", " > "),
            (r"True", "False"),
            (r"False", "True"),
            (r" and ", " or "),
            (r" or ", " and "),
            (r" \+ ", " - "),
            (r" - ", " + "),
            (r" \* ", " / "),
            (r" / ", " * "),
            (r"if ", "if not "),
        ]

        mutated_content = content
        mutated = False
        mutation_desc = ""

        # Try a few candidates
        import random

        candidates = list(range(len(mutations)))
        random.shuffle(candidates)

        for idx in candidates:
            old, new = mutations[idx]
            if re.search(old, mutated_content):
                mutated_content = re.sub(old, new, mutated_content, count=1)
                mutated = True
                mutation_desc = f"Applied mutation: '{old.strip()}' -> '{new.strip()}'"
                break

        if not mutated:
            # Fallback: break a return statement
            if "return " in mutated_content:
                mutated_content = mutated_content.replace("return ", "return None # MUTATED: ", 1)
                mutated = True
                mutation_desc = "Applied mutation: Broken return statement (returning None)."

        if not mutated:
            return "Could not find any candidates for mutation in this file."

        # Write to temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".py", prefix="mutant_")
        with os.fdopen(temp_fd, "w") as f:
            f.write(mutated_content)

        return f"MUTANT_CREATED: {temp_path}\nDescription: {mutation_desc}"

    @staticmethod
    def _purge_pycache(directory: str):
        """Remove all __pycache__ dirs under *directory* so Python reimports from source."""
        for root, dirs, _ in os.walk(directory):
            for d in dirs:
                if d == "__pycache__":
                    shutil.rmtree(os.path.join(root, d), ignore_errors=True)

    async def _run_benchmark(self, path: str, test_command: str) -> str:
        target_dir = os.path.dirname(path)
        clean_env = os.environ.copy()
        clean_env["PYTHONDONTWRITEBYTECODE"] = "1"

        # 1. Verify tests pass on ORIGINAL file
        viki_logger.info("MutationPilot: Verifying base state...")
        self._purge_pycache(target_dir)
        base_proc = await asyncio.create_subprocess_shell(
            test_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=clean_env,
        )
        await base_proc.communicate()
        if base_proc.returncode != 0:
            return "Error: Test suite fails on the ORIGINAL file. Fix tests before benchmarking."

        # 2. Generate mutant
        mutant_info = self._generate_mutant(path)
        if "MUTANT_CREATED" not in mutant_info:
            return mutant_info

        mutant_path = mutant_info.split(": ")[1].split("\n")[0]

        # 3. Swap file and run tests
        backup_path = path + ".mutant_bak"
        shutil.copy2(path, backup_path)
        self._purge_pycache(target_dir)
        shutil.copy(mutant_path, path)

        try:
            viki_logger.info(
                f"MutationPilot: Testing mutant version of {os.path.basename(path)}..."
            )
            proc = await asyncio.create_subprocess_shell(
                test_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=clean_env,
            )
            stdout, _ = await proc.communicate()

            # 4. Results
            if proc.returncode == 0:
                result = "MUTANT_SURVIVED: The test suite passed even with the bug injected. The tests are NOT robust enough."
            else:
                result = "MUTANT_KILLED: The test suite correctly identified the bug. The tests are robust."

            return f"--- Mutation Benchmark Result ---\nTarget: {os.path.basename(path)}\n{result}\n\nTest Output Snippet:\n{stdout.decode()[:400]}..."

        finally:
            # Restore original
            if os.path.exists(backup_path):
                shutil.move(backup_path, path)
            if os.path.exists(mutant_path):
                os.remove(mutant_path)

    async def _run_heal(self, path: str, error_log: str, test_command: str | None = None) -> str:
        """Autonomous healing: Propose and apply a patch for a failing file."""
        if not self._controller:
            return "Error: Skill not connected to controller."

        viki_logger.info(f"MutationPilot: Attempting to heal {os.path.basename(path)}...")

        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        prompt = (
            f"I need to fix a bug in the following file: {path}\n\n"
            f"FILE CONTENT:\n{content}\n\n"
            f"FAILURE LOG:\n{error_log}\n\n"
            f"Propose a fix that resolves the issue. Ground your patch in the failure log. "
            f"Reply with the COMPLETE NEW FILE CONTENT in a code block."
        )

        try:
            resp = await self._controller.cortex.process(
                prompt, model_tier="deep", is_plan_mode=True
            )

            # Robust extraction
            new_content = ""
            raw_explanation = resp.explanation
            blocks = re.findall(r"```(?:\w+)?\n(.*?)```", raw_explanation, re.DOTALL)
            if blocks:
                # Use the longest block (likely the file content)
                new_content = max(blocks, key=len)

            if not new_content or new_content.strip() == content.strip():
                # Try fallback: maybe it didn't use code blocks?
                if len(raw_explanation) > len(content) * 0.5:
                    new_content = raw_explanation  # Risky fallback
                else:
                    return "Heal failed: LLM did not propose a meaningful change."

            # Apply the patch (with backup)
            backup_path = path + ".heal_bak"
            shutil.copy2(path, backup_path)

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Verification
            if test_command:
                viki_logger.info(f"MutationPilot: Verifying heal for {os.path.basename(path)}...")
                proc = await asyncio.create_subprocess_shell(
                    test_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()

                if proc.returncode == 0:
                    os.remove(backup_path)
                    return f"HEAL_SUCCESS: File {os.path.basename(path)} has been patched and verified."
                else:
                    # Rollback
                    shutil.move(backup_path, path)
                    return f"HEAL_PROPOSED_BUT_FAILED: The patch did not fix the tests. Test Output:\n{stdout.decode()[:400]}"

            return f"HEAL_APPLIED: File {os.path.basename(path)} updated. (No verification command provided)."

        except Exception as e:
            viki_logger.error(f"Heal process failed: {e}")
            return f"Heal process failed: {str(e)}"
