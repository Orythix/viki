import os
import shutil
from typing import Dict, Any, List, Optional
from viki.skills.base import BaseSkill
from viki.core.utils.path_sandbox import validate_output_path

class DevSkill(BaseSkill):
    """
    Development capabilities: File system exploration, reading, writing, and patching code.
    Paths are restricted to allowed roots (workspace_dir, data_dir).
    """
    def __init__(self, controller=None):
        self._controller = controller

    @property
    def name(self) -> str:
        return "dev_tools"

    @property
    def description(self) -> str:
        return (
            "Developer tools. Usage:\n"
            "- list_files(path='.')\n"
            "- read_file(path='file.py')\n"
            "- write_file(path='file.py', content='...')\n"
            "- patch_file(path='file.py', target='old', replacement='new')"
        )

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_files", "read_file", "write_file", "patch_file"],
                    "description": "The developer file operation to perform."
                },
                "path": {
                    "type": "string",
                    "description": "Path to the target file or directory, relative to the workspace when possible."
                },
                "content": {
                    "type": "string",
                    "description": "Full file contents for write_file."
                },
                "target": {
                    "type": "string",
                    "description": "Existing text to replace when using patch_file."
                },
                "replacement": {
                    "type": "string",
                    "description": "Replacement text for patch_file."
                }
            },
            "required": ["action", "path"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        path = params.get('path', '.')
        if not path:
            path = '.'
        ok, path_or_err = validate_output_path(path, controller=self._controller)
        if not ok:
            return path_or_err
        path = path_or_err

        action = self._resolve_action(params, path)
        if action == "patch_file":
            if 'target' not in params or 'replacement' not in params:
                return "Error: patch_file requires both 'target' and 'replacement'."
            return self._patch_file(path, params['target'], params['replacement'])
        if action == "write_file":
            if 'content' not in params:
                return "Error: write_file requires 'content'."
            return self._write_file(path, params['content'])
        if action == "list_files":
            return self._list_files(path)
        if action == "read_file":
            return self._read_file(path)
        return "Error: Unknown developer action."

    def _resolve_action(self, params: Dict[str, Any], path: str) -> str:
        action = str(params.get("action", "")).strip().lower()
        if action in {"list_files", "read_file", "write_file", "patch_file"}:
            return action

        # Backward compatibility for older prompt formats.
        if 'target' in params and 'replacement' in params:
            return "patch_file"
        if 'content' in params:
            return "write_file"
        if params.get('mode') == 'list' or os.path.isdir(path):
            return "list_files"
        return "read_file"

    def _list_files(self, path: str) -> str:
        try:
            if not os.path.exists(path):
                return f"Error: Path '{path}' not found."
            items = os.listdir(path)
            annotated = [f"[{'DIR' if os.path.isdir(os.path.join(path, i)) else 'FILE'}] {i}" for i in items]
            return f"CONTENTS OF {path}:\n" + "\n".join(annotated)
        except Exception as e:
            return f"List Error: {e}"

    def _read_file(self, path: str) -> str:
        try:
            if not os.path.exists(path):
                return f"Error: File '{path}' not found."
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return f"--- FILE: {path} ---\n{content}\n--- END FILE ---"
        except Exception as e:
            return f"Read Error: {e}"

    def _write_file(self, path: str, content: str) -> str:
        try:
            self._backup_file(path)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content.replace("\\n", "\n"))
            return f"Successfully wrote to {path}."
        except Exception as e:
            return f"Write Error: {e}"

    def _patch_file(self, path: str, target: str, replacement: str) -> str:
        try:
            if not os.path.exists(path): return f"Error: File '{path}' not found."
            with open(path, 'r', encoding='utf-8') as f: content = f.read()
            target = target.replace("\\n", "\n")
            replacement = replacement.replace("\\n", "\n")
            if target not in content: return f"Error: Target text not found in {path}."
            new_content = content.replace(target, replacement)
            self._backup_file(path)
            with open(path, 'w', encoding='utf-8') as f: f.write(new_content)
            return f"Successfully patched {path}."
        except Exception as e:
            return f"Patch Error: {e}"

    def _backup_file(self, path: str):
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
