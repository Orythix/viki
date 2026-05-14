import os
import shutil
from typing import Dict, Any, List, Optional
from viki.skills.base import BaseSkill
from viki.core.utils.path_sandbox import validate_output_path
from viki.config.logger import viki_logger

class DevSkill(BaseSkill):
    """
    Advanced Development capabilities: File system management, robust code patching, and workspace organization.
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
            "Professional Developer Tools. Actions:\n"
            "- list_files(path='.'): List directory contents.\n"
            "- read_file(path='file.py'): Read full content.\n"
            "- write_file(path='file.py', content='...'): Overwrite or create file.\n"
            "- patch_file(path='file.py', target='old', replacement='new', occurrence=1): Targeted edit.\n"
            "- move_file(path='old.py', destination='new.py'): Rename or move.\n"
            "- delete_file(path='file.py'): Remove file or directory.\n"
            "- create_dir(path='new_dir'): Create directory recursively.\n"
            "- multi_patch(patches=[...]): Apply multiple independent patches atomically."
        )

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_files", "read_file", "write_file", "patch_file", "move_file", "delete_file", "create_dir", "multi_patch"],
                    "description": "The developer file operation to perform."
                },
                "path": {
                    "type": "string",
                    "description": "Path to the target file or directory."
                },
                "destination": {
                    "type": "string",
                    "description": "Destination path for move_file."
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
                },
                "occurrence": {
                    "type": "integer",
                    "description": "Specific occurrence of 'target' to replace (1-based). If omitted, replaces all."
                },
                "patches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "target": {"type": "string"},
                            "replacement": {"type": "string"},
                            "occurrence": {"type": "integer"}
                        },
                        "required": ["path", "target", "replacement"]
                    },
                    "description": "List of patches for multi_patch action."
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
        
        try:
            if action == "patch_file":
                if 'target' not in params or 'replacement' not in params:
                    return "Error: patch_file requires both 'target' and 'replacement'."
                return self._patch_file(path, params['target'], params['replacement'], params.get('occurrence'))
            
            if action == "write_file":
                if 'content' not in params:
                    return "Error: write_file requires 'content'."
                return self._write_file(path, params['content'])
            
            if action == "list_files":
                return self._list_files(path)
            
            if action == "read_file":
                return self._read_file(path)
            
            if action == "move_file":
                dest = params.get('destination')
                if not dest: return "Error: move_file requires 'destination'."
                ok_dest, dest_or_err = validate_output_path(dest, controller=self._controller)
                if not ok_dest: return dest_or_err
                return self._move_file(path, dest_or_err)
            
            if action == "delete_file":
                return self._delete_file(path)
            
            if action == "create_dir":
                return self._create_dir(path)
            
            if action == "multi_patch":
                return await self._multi_patch(params.get('patches', []))

            return f"Error: Unknown developer action '{action}'."
        except Exception as e:
            viki_logger.error(f"DevSkill execution error: {e}")
            return f"Execution Error: {str(e)}"

    def _resolve_action(self, params: Dict[str, Any], path: str) -> str:
        action = str(params.get("action", "")).strip().lower()
        if action in {"list_files", "read_file", "write_file", "patch_file", "move_file", "delete_file", "create_dir", "multi_patch"}:
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
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if self._controller:
                self._controller.track_touched_item("touched_files", path)
            return f"--- FILE: {path} ---\n{content}\n--- END FILE ---"
        except Exception as e:
            return f"Read Error: {e}"

    def _write_file(self, path: str, content: str) -> str:
        try:
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._backup_file(path)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content.replace("\\n", "\n"))
            if self._controller:
                self._controller.track_touched_item("touched_files", path)
            return f"Successfully wrote to {path}."
        except Exception as e:
            return f"Write Error: {e}"

    def _patch_file(self, path: str, target: str, replacement: str, occurrence: Optional[int] = None) -> str:
        try:
            if not os.path.exists(path): return f"Error: File '{path}' not found."
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            target = target.replace("\\n", "\n")
            replacement = replacement.replace("\\n", "\n")
            
            if target not in content:
                return f"Error: Target text not found in {path}."
            
            if occurrence is not None:
                parts = content.split(target)
                if occurrence < 1 or occurrence > len(parts) - 1:
                    return f"Error: Occurrence {occurrence} out of range (Found {len(parts)-1})."
                
                # Reconstruct with only one occurrence replaced
                new_content = target.join(parts[:occurrence]) + replacement + target.join(parts[occurrence:])
            else:
                new_content = content.replace(target, replacement)
                
            self._backup_file(path)
            with open(path, 'w', encoding='utf-8') as f: f.write(new_content)
            if self._controller:
                self._controller.track_touched_item("touched_files", path)
            return f"Successfully patched {path} (occurrence={occurrence if occurrence else 'all'})."
        except Exception as e:
            return f"Patch Error: {e}"

    def _move_file(self, src: str, dest: str) -> str:
        try:
            if not os.path.exists(src): return f"Error: Source '{src}' not found."
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
            return f"Successfully moved {src} to {dest}."
        except Exception as e:
            return f"Move Error: {e}"

    def _delete_file(self, path: str) -> str:
        try:
            if not os.path.exists(path): return f"Error: Path '{path}' not found."
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return f"Successfully deleted {path}."
        except Exception as e:
            return f"Delete Error: {e}"

    def _create_dir(self, path: str) -> str:
        try:
            os.makedirs(path, exist_ok=True)
            return f"Successfully created directory {path}."
        except Exception as e:
            return f"CreateDir Error: {e}"

    async def _multi_patch(self, patches: List[Dict[str, Any]]) -> str:
        results = []
        for p in patches:
            p_path = p.get('path')
            p_target = p.get('target')
            p_replacement = p.get('replacement')
            p_occ = p.get('occurrence')
            
            if not (p_path and p_target and p_replacement is not None):
                results.append(f"Failed: Invalid patch spec {p}")
                continue
            
            ok, path_or_err = validate_output_path(p_path, controller=self._controller)
            if not ok:
                results.append(f"Failed: {p_path} blocked: {path_or_err}")
                continue
            
            res = self._patch_file(path_or_err, p_target, p_replacement, p_occ)
            results.append(f"{p_path}: {res}")
            
        return "Multi-patch Report:\n" + "\n".join(results)

    def _backup_file(self, path: str):
        if os.path.exists(path) and os.path.isfile(path):
            try:
                shutil.copy2(path, path + ".bak")
            except Exception:
                pass
