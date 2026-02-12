import os
import secrets
import pyautogui
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class VisionSkill(BaseSkill):
    """
    Skill to allow VIKI to 'see' the user's screen.
    Uses pyautogui for screenshots.
    """
    def __init__(self, data_dir: str = "./data/vision"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    @property
    def name(self) -> str:
        return "look_at_screen"

    @property
    def description(self) -> str:
        return "Takes a screenshot of the current screen to analyze visual information. Action: look_at_screen(instruction='...')."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "What to look for or analyze in the screenshot (e.g., 'read the error message', 'describe the UI')."
                }
            },
            "required": ["instruction"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        instruction = params.get("instruction", "What's on the screen?")
        
        # 1. Take Screenshot
        filename = f"screenshot_{secrets.token_hex(4)}.png"
        import os
        filepath = os.path.abspath(os.path.join(self.data_dir, filename))
        
        try:
            viki_logger.info(f"Visualizing screen for instruction: {instruction}")
            await asyncio.to_thread(pyautogui.screenshot, filepath)
            
            # Return a formatted string that the Cortex can parse to find image paths
            return f"Screenshot captured successfully at: {filepath}\nInstruction: {instruction}"
            
        except Exception as e:
            viki_logger.error(f"Vision error: {e}")
            return f"Error capturing screen: {str(e)}"
