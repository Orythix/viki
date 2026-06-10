import pyperclip
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class ClipboardSkill(BaseSkill):
    """
    Read and write to the system clipboard.
    Useful for copying text from the user or pasting content.
    """
    
    @property
    def name(self) -> str:
        return "clipboard"

    @property
    def description(self) -> str:
        return "Read/Write system clipboard. Actions: copy(text), paste()."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["copy", "paste"],
                    "description": "Action to perform on clipboard"
                },
                "text": {
                    "type": "string",
                    "description": "Text to copy to clipboard (required for copy action)"
                }
            },
            "required": ["action"]
        }

    @property
    def safety_tier(self) -> str:
        return "safe"

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get('action', 'paste')
        
        try:
            if action == 'copy':
                text = params.get('text')
                if not text:
                    return "Error: No text provided to copy."
                await asyncio.to_thread(pyperclip.copy, text)
                return "Text copied to clipboard."
            
            elif action == 'paste':
                content = await asyncio.to_thread(pyperclip.paste)
                return f"Clipboard Content:\n{content}"
            
            else:
                return f"Unknown clipboard action: {action}"
                
        except Exception as e:
            viki_logger.error(f"Clipboard error: {e}")
            return f"Clipboard failed: {str(e)}"
