import os
from typing import Dict, Any, List
from skills.base import BaseSkill
from config.logger import viki_logger

class ContextWeaverSkill(BaseSkill):
    """
    Skill for manually weaving (pinning) specific files or directories into the RAG context.
    Overrides automatic pruning to ensure critical code is always available.
    """
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        self._retriever = None

    def _get_retriever(self):
        if self._retriever:
            return self._retriever
        if self._controller and hasattr(self._controller, "context_retriever"):
            self._retriever = self._controller.context_retriever
            return self._retriever
        return None

    @property
    def name(self) -> str:
        return "context_weaver"

    @property
    def description(self) -> str:
        return "Manages pinned code context for RAG. Actions: pin, unpin, list, clear, expand."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["pin", "unpin", "list", "clear", "expand"],
                    "description": "Context weaving action"
                },
                "path": {
                    "type": "string",
                    "description": "Path to the file or directory to pin/unpin"
                }
            },
            "required": ["action"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        retriever = self._get_retriever()
        
        if not retriever:
            return "Error: ContextRetriever not available in this controller."

        try:
            if action == "pin":
                path = params.get("path")
                if not path:
                    return "Error: Path is required for 'pin' action."
                
                # Resolve path
                abs_path = os.path.abspath(path)
                if not os.path.exists(abs_path):
                    # Try relative to workspace
                    abs_path = os.path.join(retriever.workspace_dir, path)
                    if not os.path.exists(abs_path):
                        return f"Error: Path '{path}' not found."
                
                if abs_path not in retriever.pinned_paths:
                    retriever.pinned_paths.append(abs_path)
                    rel = os.path.relpath(abs_path, retriever.workspace_dir)
                    return f"Successfully pinned '{rel}' to active context."
                else:
                    return f"Path '{path}' is already pinned."

            elif action == "unpin":
                path = params.get("path")
                if not path:
                    return "Error: Path is required for 'unpin' action."
                
                abs_path = os.path.abspath(path)
                found = False
                for p in list(retriever.pinned_paths):
                    if os.path.exists(p) and os.path.exists(abs_path) and os.path.samefile(p, abs_path):
                        retriever.pinned_paths.remove(p)
                        found = True
                        break
                    elif p == path or p == abs_path:
                        retriever.pinned_paths.remove(p)
                        found = True
                        break
                
                return f"Unpinned '{path}'." if found else f"Path '{path}' was not pinned."

            elif action == "list":
                if not retriever.pinned_paths:
                    return "No paths currently pinned to context."
                
                lines = ["--- Currently Pinned Context ---"]
                for p in retriever.pinned_paths:
                    try:
                        rel = os.path.relpath(p, retriever.workspace_dir)
                        lines.append(f" - {rel} ({'DIR' if os.path.isdir(p) else 'FILE'})")
                    except:
                        lines.append(f" - {p} (Invalid Path)")
                return "\n".join(lines)

            elif action == "clear":
                count = len(retriever.pinned_paths)
                retriever.pinned_paths = []
                return f"Cleared {count} pinned paths from context."

            elif action == "expand":
                path = params.get("path")
                if not path:
                    return "Error: Path is required for 'expand' action."
                
                # Resolve path
                abs_path = os.path.abspath(path)
                if not os.path.exists(abs_path):
                    abs_path = os.path.join(retriever.workspace_dir, path)
                    if not os.path.exists(abs_path):
                        return f"Error: Path '{path}' not found."
                
                # Load full content
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(16384) # Expand to 16KB
                    
                    # We inject this into the response. 
                    # The controller/loop will see it as the result of the action.
                    return f"CONTENT EXPANSION for {path}:\n```\n{content}\n```"
                except Exception as e:
                    return f"Error: Could not expand file '{path}': {e}"

            return f"Error: Unknown action '{action}'"

        except Exception as e:
            viki_logger.error(f"ContextWeaver Execution Error: {e}")
            return f"ContextWeaver Error: {str(e)}"
