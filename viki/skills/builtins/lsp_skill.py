from typing import Dict, Any, List, Optional
from viki.skills.base import BaseSkill
from viki.integrations.lsp_bridge import LSPBridge
from viki.config.logger import viki_logger
import os

class LspSkill(BaseSkill):
    """
    Language Server Protocol (LSP) integration for IDE-grade code analysis.
    Provides diagnostics, hover information, and symbol references.
    """
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        workspace_dir = "."
        if controller and hasattr(controller, "settings"):
            workspace_dir = controller.settings.get("system", {}).get("workspace_dir", ".")
        
        self.bridge = LSPBridge(workspace_dir)

    @property
    def name(self) -> str:
        return "lsp_tools"

    @property
    def description(self) -> str:
        return (
            "IDE-grade code analysis using LSP. Actions:\n"
            "- diagnose(path='file.py'): Get linting errors and warnings.\n"
            "- hover(path='file.py', line=10, character=5): Get type information and documentation.\n"
            "- definition(path='file.py', line=10, character=5): Jump to definition.\n"
            "- references(path='file.py', line=10, character=5): Find all usages."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["diagnose", "hover", "definition", "references"],
                    "description": "LSP action to perform"
                },
                "path": {
                    "type": "string",
                    "description": "Path to the file"
                },
                "line": {
                    "type": "integer",
                    "description": "0-based line number"
                },
                "character": {
                    "type": "integer",
                    "description": "0-based character offset"
                }
            },
            "required": ["action", "path"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        path = params.get("path")
        
        if not path:
            return "Error: path is required."
            
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return f"Error: File '{path}' not found."

        try:
            if action == "diagnose":
                session = await self.bridge.session_for(abs_path)
                if session is None:
                    spec = self.bridge._spec_for_path(abs_path)
                    if spec:
                        return f"LSP {spec.name} is not installed. To enable diagnostics, please run: npm install -g {spec.name}-langserver (or equivalent for your OS)."
                    return "No LSP server configured for this file type."

                diags = await self.bridge.diagnose_file(abs_path)
                if not diags:
                    return f"No issues found in {path}."
                
                formatted = []
                for d in diags:
                    severity = d.get("severity", "info")
                    msg = d.get("message", "")
                    range_info = d.get("range", {}).get("start", {})
                    line = range_info.get("line", "?")
                    char = range_info.get("character", "?")
                    formatted.append(f"[{severity.upper()}] L{line}:C{char} - {msg}")
                
                return f"Diagnostics for {path}:\n" + "\n".join(formatted[:20]) # Limit output
                
            elif action == "hover":
                session = await self.bridge.session_for(abs_path)
                if session is None: return "LSP not available for this file."
                
                line = params.get("line", 0)
                char = params.get("character", 0)
                info = await self.bridge.hover(abs_path, line, char)
                if not info or not info.get("text"):
                    return f"No information found at L{line}:C{char}."
                return f"Hover Info at L{line}:C{char}:\n{info['text']}"
                
            elif action in ("definition", "references"):
                session = await self.bridge.session_for(abs_path)
                if session is None: return "LSP not available for this file."

                line = params.get("line", 0)
                char = params.get("character", 0)
                if action == "definition":
                    results = await self.bridge.definition(abs_path, line, char)
                else:
                    results = await self.bridge.references(abs_path, line, char)
                
                if not results:
                    return f"No {action} found."
                
                formatted = []
                for r in results:
                    uri = r.get("uri", "")
                    range_info = r.get("range", {}).get("start", {})
                    line_res = range_info.get("line", "?")
                    formatted.append(f"{uri}#L{line_res}")
                
                return f"{action.capitalize()} for L{line}:C{char}:\n" + "\n".join(formatted[:10])

            return f"Error: Unknown action '{action}'"
            
        except Exception as e:
            viki_logger.error(f"LSPSkill Error: {e}")
            return f"LSP operation failed: {str(e)}"
            
    async def shutdown(self):
        await self.bridge.shutdown()
