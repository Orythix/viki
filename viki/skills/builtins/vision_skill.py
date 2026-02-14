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
                },
                "image_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: List of existing image paths to analyze instead of taking a new screenshot."
                }
            },
            "required": ["instruction"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        instruction = params.get("instruction", "What's on the screen?")
        image_lines = []
        
        # 1. Check for provided images
        input_images = params.get("image_paths", [])
        
        if input_images:
             for path in input_images:
                  if os.path.exists(path):
                       image_lines.append(f"Analyzing provided image: {path}")
                  else:
                       image_lines.append(f"Image not found: {path}")
        else:
             # 2. Take Screenshot if no images provided
             filename = f"screenshot_{secrets.token_hex(4)}.png"
             filepath = os.path.abspath(os.path.join(self.data_dir, filename))
             
             try:
                 viki_logger.info(f"Visualizing screen for instruction: {instruction}")
                 await asyncio.to_thread(pyautogui.screenshot, filepath)
                 image_lines.append(f"Screenshot captured successfully at: {filepath}")
             except Exception as e:
                 viki_logger.error(f"Vision error: {e}")
                 return f"Error capturing screen: {str(e)}"

        # Return formatted context for Cortex
        # The Cortex logic screens this string for "Screenshot captured successfully at:"
        # We also want it to find provided images.
        return "\n".join(image_lines) + f"\nInstruction: {instruction}"
