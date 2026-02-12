import asyncio
import pyautogui
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class MediaControlSkill(BaseSkill):
    """
    Real media control using OS-level key simulation.
    Works with YouTube (browser), Spotify, VLC, and any media player.
    """
    
    @property
    def name(self) -> str:
        return "media_control"
    
    @property 
    def description(self) -> str:
        return (
            "Control media playback on the system. "
            "Actions: play_pause, next_track, prev_track, "
            "volume_up, volume_down, mute, stop."
        )
    
    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play_pause", "next_track", "prev_track", "volume_up", "volume_down", "mute", "stop"],
                    "description": "The media action to perform"
                },
                "amount": {
                    "type": "integer",
                    "description": "Number of volume steps (default: 5)",
                    "default": 5
                }
            },
            "required": ["action"]
        }

    @property
    def safety_tier(self) -> str:
        return "safe"

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get('action', 'play_pause')
        
        try:
            if action in ['play_pause', 'pause', 'play', 'toggle']:
                await asyncio.to_thread(pyautogui.press, 'playpause')
                return "Media toggled (play/pause)."
            
            elif action in ['next', 'next_track', 'skip']:
                await asyncio.to_thread(pyautogui.press, 'nexttrack')
                return "Skipped to next track."
            
            elif action in ['prev', 'prev_track', 'previous']:
                await asyncio.to_thread(pyautogui.press, 'prevtrack')
                return "Went to previous track."
            
            elif action in ['volume_up', 'louder']:
                presses = int(params.get('amount', 5))
                for _ in range(presses):
                    await asyncio.to_thread(pyautogui.press, 'volumeup')
                return f"Volume increased by {presses} steps."
            
            elif action in ['volume_down', 'quieter', 'softer']:
                presses = int(params.get('amount', 5))
                for _ in range(presses):
                    await asyncio.to_thread(pyautogui.press, 'volumedown')
                return f"Volume decreased by {presses} steps."
            
            elif action in ['mute', 'unmute']:
                await asyncio.to_thread(pyautogui.press, 'volumemute')
                return "Volume mute toggled."
            
            elif action in ['stop']:
                await asyncio.to_thread(pyautogui.press, 'stop')
                return "Media stopped."
            
            else:
                return f"Unknown media action: '{action}'. Supported: play_pause, next_track, prev_track, volume_up, volume_down, mute, stop."
                
        except Exception as e:
            viki_logger.error(f"Media control failed: {e}")
            return f"Media control error: {e}"
