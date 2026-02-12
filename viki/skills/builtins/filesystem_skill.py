import os
from typing import Dict, Any
from viki.skills.base import BaseSkill

class FileSystemSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "filesystem_skill"

    @property
    def description(self) -> str:
        return "Performs file operations. Actions: list_dir, read_file, write_file."

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

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        path = params.get("path")
        
        if not action or not path:
            return "Error: strict parameters 'action' and 'path' required."

        try:
            if action == "list_dir":
                items = os.listdir(path)
                return f"Contents of {path}: {', '.join(items)}"
            
            elif action == "read_file":
                with open(path, 'r', encoding='utf-8') as f:
                    # Non-blocking read would be nicer but os.read is fine for small files in this context
                    content = f.read(2048) # Limit read size
                return content

            elif action == "write_file":
                content = params.get("content")
                if not content: return "Error: No content provided."
                with open(path, "w", encoding='utf-8') as f:
                    f.write(content)
                return f"File written successfully to {path}"
                
            return f"Error: Unknown action '{action}'"
            
        except Exception as e:
            return f"FileSystem Error: {str(e)}"
