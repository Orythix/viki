import os
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.core.utils.path_sandbox import get_allowed_roots, BLOCKED_PATHS

class FileSystemSkill(BaseSkill):
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        # Prefer workspace_dir and data_dir from settings; fall back to __file__-relative and home dirs
        if controller and getattr(controller, "settings", None):
            sys_cfg = controller.settings.get("system", {})
            if sys_cfg.get("workspace_dir") or sys_cfg.get("data_dir"):
                self.allowed_roots = get_allowed_roots(controller)
            else:
                self._set_fallback_roots()
        else:
            self._set_fallback_roots()
        self.blocked_paths = list(BLOCKED_PATHS)

    def _set_fallback_roots(self) -> None:
        """Roots when controller/settings are not available (align with original behavior)."""
        self.allowed_roots = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "workspace")),
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Desktop"),
        ]
    
    @property
    def name(self) -> str:
        return "filesystem_skill"

    @property
    def description(self) -> str:
        return "Performs file operations within allowed directories. Actions: list_dir, read_file, write_file."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_dir", "read_file", "write_file"],
                    "description": "File operation to perform"
                },
                "path": {
                    "type": "string",
                    "description": "Path to the file or directory"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write_file action)"
                }
            },
            "required": ["action", "path"]
        }
    
    def _validate_path(self, path: str) -> tuple[bool, str]:
        """Validate path is within allowed directories and not blocked."""
        try:
            # Normalize and resolve the path
            real_path = os.path.realpath(os.path.abspath(path))
            
            # Check if path starts with any blocked directory
            for blocked in self.blocked_paths:
                if real_path.startswith(os.path.realpath(blocked)):
                    return False, f"Access denied: {path} is in a protected system directory"
            
            # Check if path is within allowed roots
            for allowed_root in self.allowed_roots:
                if real_path.startswith(os.path.realpath(allowed_root)):
                    return True, real_path
            
            return False, f"Access denied: {path} is outside allowed directories"
        
        except Exception as e:
            return False, f"Path validation error: {str(e)}"

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        path = params.get("path")
        
        if not action or not path:
            return "Error: strict parameters 'action' and 'path' required."
        
        # Validate path before any operation
        is_valid, validated_path = self._validate_path(path)
        if not is_valid:
            return validated_path  # Returns error message

        try:
            if action == "list_dir":
                items = os.listdir(validated_path)
                return f"Contents of {validated_path}: {', '.join(items[:50])}"  # Limit output
            
            elif action == "read_file":
                with open(validated_path, 'r', encoding='utf-8') as f:
                    content = f.read(2048)  # Limit read size
                return content

            elif action == "write_file":
                content = params.get("content")
                if not content: 
                    return "Error: No content provided."
                # Additional length check to prevent abuse
                if len(content) > 100000:  # 100KB limit
                    return "Error: Content too large (max 100KB)"
                with open(validated_path, "w", encoding='utf-8') as f:
                    f.write(content)
                return f"File written successfully to {validated_path}"
                
            return f"Error: Unknown action '{action}'"
            
        except Exception as e:
            return f"FileSystem Error: {str(e)}"
