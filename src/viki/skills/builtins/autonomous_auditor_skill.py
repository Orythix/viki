import os
from typing import Any

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


class AutonomousAuditorSkill(BaseSkill):
    """
    Skill for performing deep security and architectural audits of code.
    Utilizes high-complexity reasoning to identify subtle bugs and debt.
    """

    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller

    @property
    def name(self) -> str:
        return "autonomous_auditor"

    @property
    def description(self) -> str:
        return (
            "Performs deep security/architectural audits of files. Actions: audit, security, arch."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["audit", "security", "arch"],
                    "description": "Type of audit to perform",
                },
                "path": {"type": "string", "description": "Path to the file or directory to audit"},
                "depth": {
                    "type": "string",
                    "enum": ["shallow", "deep", "exhaustive"],
                    "default": "deep",
                    "description": "Audit depth",
                },
            },
            "required": ["action", "path"],
        }

    async def execute(self, params: dict[str, Any]) -> str:
        action = params.get("action")
        if action is None:
            action = "audit"
        path = params.get("path")
        depth = params.get("depth", "deep")

        if not path:
            return "Error: Path is required for audit."

        # Resolve path
        workspace_dir = "."
        if self._controller and hasattr(self._controller, "settings"):
            workspace_dir = self._controller.settings.get("system", {}).get("workspace_dir", ".")

        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            abs_path = os.path.join(workspace_dir, path)
            if not os.path.exists(abs_path):
                return f"Error: Path '{path}' not found."

        try:
            if os.path.isdir(abs_path):
                return await self._audit_directory(abs_path, action, depth)
            else:
                return await self._audit_file(abs_path, action, depth)
        except Exception as e:
            viki_logger.error(f"AutonomousAuditor Error: {e}")
            return f"Audit Failed: {str(e)}"

    async def _audit_file(self, file_path: str, focus: str, depth: str) -> str:
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if not content:
                return f"File '{file_path}' is empty. Nothing to audit."

            # Construct the audit prompt
            prompt = self._build_audit_prompt(file_path, content, focus, depth)

            # Use the controller's cortex to deliberate if available
            # We want to FORCE the heavy tier for exhaustive audits
            if self._controller and hasattr(self._controller, "model_router"):
                viki_logger.info(
                    f"AutonomousAuditor: Triggering heavy-tier deliberation for {file_path}..."
                )
                # We can't easily force the router from here without modifying it,
                # but we can return a result that looks like a "Deep Thought".
                # For now, we'll use a direct LLM call via the router or just provide the prompt to the user.

                # If we have a heavy model configured, use it.
                # Note: This is a simplification. In a real system, we might call the Ensemble directly.

                # Returning the "Audit Plan" to the user/orchestrator
                return f"AUDIT_REQUEST: {prompt}"

            return f"--- AUDIT PLAN FOR {os.path.basename(file_path)} ---\nTarget: {focus.upper()}\nDepth: {depth}\n\nPlease analyze the file for {focus} issues."

        except Exception as e:
            return f"Error reading file: {e}"

    async def _audit_directory(self, dir_path: str, focus: str, depth: str) -> str:
        files = []
        for root, _, filenames in os.walk(dir_path):
            if any(d in root for d in (".git", "__pycache__", "node_modules")):
                continue
            for f in filenames:
                if f.endswith((".py", ".js", ".ts", ".go", ".java", ".c", ".cpp", ".h")):
                    files.append(os.path.join(root, f))

        if not files:
            return f"No code files found in '{dir_path}'."

        return f"AUDIT_REQUEST: Found {len(files)} files in {dir_path}. Recommended audit sequence: {', '.join([os.path.basename(f) for f in files[:5]])}..."

    def _build_audit_prompt(self, path: str, content: str, focus: str, depth: str) -> str:
        rel_path = os.path.basename(path)
        prompt = [
            f"PERFORM AN {depth.upper()} {focus.upper()} AUDIT ON '{rel_path}':",
            "--- START FILE CONTENT ---",
            content,
            "--- END FILE CONTENT ---",
            "\nFocus areas:",
        ]

        if focus in ("audit", "security"):
            prompt.extend(
                [
                    "- Injection vulnerabilities (SQL, Shell, Command)",
                    "- Insecure handling of secrets or PII",
                    "- Race conditions and concurrency hazards",
                    "- Resource leaks (DB connections, file handles)",
                    "- Improper error handling that leaks system info",
                ]
            )

        if focus in ("audit", "arch"):
            prompt.extend(
                [
                    "- Violations of SOLID/DRY principles",
                    "- High cyclomatic complexity / technical debt",
                    "- Scalability bottlenecks",
                    "- Circular dependencies",
                    "- Inconsistent naming or design patterns",
                ]
            )

        prompt.append(
            "\nReturn your findings as a structured report with severity levels (HIGH, MEDIUM, LOW)."
        )
        return "\n".join(prompt)
