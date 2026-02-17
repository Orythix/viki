"""
Smart home: Philips Hue, Eight Sleep (optional). Config: hue bridge IP, API keys in env.
"""
import os
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger


class SmartHomeSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "smart_home"

    @property
    def description(self) -> str:
        return "Control lights (Hue) or bed (Eight Sleep). Actions: lights on/off/brightness, bed temperature. Set VIKI_HUE_BRIDGE_IP and pair for Hue."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["lights_on", "lights_off", "brightness", "bed_temp"], "description": "Action."},
                "value": {"type": "number", "description": "Brightness 0-254 or temperature."},
            },
            "required": ["action"],
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = (params.get("action") or "").lower()
        bridge_ip = os.environ.get("VIKI_HUE_BRIDGE_IP")
        if not bridge_ip and action.startswith("lights"):
            return "Set VIKI_HUE_BRIDGE_IP and pair (phue or aiohue) for Philips Hue."
        if action == "lights_on":
            try:
                import aiohttp
                # Hue API: put /api/<user>/lights/1/state {"on": true}
                user = os.environ.get("VIKI_HUE_USER") or ""
                if not user:
                    return "Set VIKI_HUE_USER (create user via Hue API once)."
                async with aiohttp.ClientSession() as session:
                    async with session.put(
                        f"http://{bridge_ip}/api/{user}/lights/1/state",
                        json={"on": True},
                    ) as resp:
                        if resp.status in (200, 204):
                            return "Lights on."
                        return f"Hue API: {resp.status}"
            except Exception as e:
                return f"Hue error: {e}"
        if action == "lights_off":
            try:
                import aiohttp
                user = os.environ.get("VIKI_HUE_USER") or ""
                if not user:
                    return "Set VIKI_HUE_USER."
                async with aiohttp.ClientSession() as session:
                    async with session.put(
                        f"http://{bridge_ip}/api/{user}/lights/1/state",
                        json={"on": False},
                    ) as resp:
                        if resp.status in (200, 204):
                            return "Lights off."
                        return f"Hue API: {resp.status}"
            except Exception as e:
                return f"Hue error: {e}"
        if action == "brightness":
            val = int(params.get("value", 200))
            val = max(0, min(254, val))
            try:
                import aiohttp
                user = os.environ.get("VIKI_HUE_USER") or ""
                if not user:
                    return "Set VIKI_HUE_USER."
                async with aiohttp.ClientSession() as session:
                    async with session.put(
                        f"http://{bridge_ip}/api/{user}/lights/1/state",
                        json={"on": True, "bri": val},
                    ) as resp:
                        if resp.status in (200, 204):
                            return f"Brightness set to {val}."
                        return f"Hue API: {resp.status}"
            except Exception as e:
                return f"Hue error: {e}"
        if action == "bed_temp":
            return "Eight Sleep: set VIKI_EIGHTSLEEP_* for bed control."
        return "Unknown action. Use lights_on, lights_off, brightness, bed_temp."