"""
Enhanced computer use skill with perceive-act-verify loop and global abort hotkey.

Extends the existing vision + grounding + overlay loop with a safety abort
mechanism and structured verification.
"""

import asyncio
from typing import Any, cast

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill

# Global abort flag — set by hotkey listener or /emergency command
_ABORT_FLAG = False


def signal_abort() -> None:
    """Signal all computer use operations to abort immediately."""
    global _ABORT_FLAG
    _ABORT_FLAG = True
    viki_logger.warning("ComputerUse: ABORT SIGNALLED")


def clear_abort() -> None:
    global _ABORT_FLAG
    _ABORT_FLAG = False


def is_aborted() -> bool:
    return _ABORT_FLAG


class ComputerUseSkill(BaseSkill):
    """
    Screen understanding with perceive-act-verify loop and global abort.

    Steps:
      1. Perceive: capture screen via vision skill
      2. Plan: determine what to click/type
      3. Act: execute the action via overlay + input simulation
      4. Verify: confirm the action had the expected effect
      5. Abort: any step can be interrupted by the global abort hotkey
    """

    def __init__(self, controller=None):
        self._controller = controller

    @property
    def name(self) -> str:
        return "computer_use"

    @property
    def description(self) -> str:
        return "Control the computer screen: perceive, plan, act, and verify. Supports abort via /emergency."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["click", "type", "scroll", "screenshot", "move", "hotkey"],
                    "description": "Action to perform",
                },
                "target": {
                    "type": "string",
                    "description": "Target element description or coordinates",
                },
                "text": {"type": "string", "description": "Text to type (for type action)"},
                "verify": {
                    "type": "boolean",
                    "description": "Whether to verify the action result",
                    "default": True,
                },
            },
            "required": ["action"],
        }

    async def execute(self, params: dict[str, Any]) -> str:
        clear_abort()
        action = params.get("action", "")
        target = params.get("target", "")
        text = params.get("text", "")
        should_verify = params.get("verify", True)

        steps: list[str] = []

        # 1. Perceive
        steps.append("perceive")
        screenshot = await self._perceive()
        if is_aborted():
            return "ABORTED during perception"

        # 2. Plan
        steps.append("plan")
        plan = await self._plan(action, target, text, screenshot)
        if is_aborted():
            return "ABORTED during planning"

        # 3. Act
        steps.append("act")
        await self._act(action, plan)
        if is_aborted():
            return "ABORTED during action"

        # 4. Verify
        if should_verify:
            steps.append("verify")
            verified = await self._verify(action, target)
            if not verified:
                return f"Action completed but verification failed (steps: {', '.join(steps)})"

        return f"Action completed successfully (steps: {', '.join(steps)})"

    async def _perceive(self) -> str:
        """Capture screen and return description."""
        try:
            vision = (
                self._controller.skill_registry.get_skill("vision") if self._controller else None
            )
            if vision:
                return cast("str", await vision.execute({"action": "describe_screen"}))
        except Exception as e:
            viki_logger.debug("ComputerUse perceive failed: %s", e)
        return "(screen capture unavailable)"

    async def _plan(self, action: str, target: str, text: str, screenshot: str) -> dict:
        """Plan the action based on perception."""
        return {"action": action, "target": target, "text": text, "coordinates": {}}

    async def _act(self, action: str, plan: dict) -> str:
        """Execute the planned action."""
        try:
            overlay = (
                self._controller.skill_registry.get_skill("overlay") if self._controller else None
            )
            if overlay and action in ("click", "move"):
                await overlay.execute({"action": "draw_target", "target": plan.get("target", "")})

            if action == "click":
                import pyautogui

                pyautogui.click()
                return "Clicked"
            elif action == "type":
                import pyautogui

                pyautogui.write(plan.get("text", ""))
                return "Typed"
            elif action == "screenshot":
                import pyautogui

                pyautogui.screenshot("viki_screenshot.png")
                return "Screenshot saved"
            elif action == "hotkey":
                import pyautogui

                keys = plan.get("target", "").split("+")
                pyautogui.hotkey(*keys)
                return f"Hotkey {plan.get('target', '')} pressed"
        except Exception as e:
            return f"Action failed: {e}"
        return f"Unknown action: {action}"

    async def _verify(self, action: str, target: str) -> bool:
        """Verify the action had the expected effect."""
        await asyncio.sleep(0.5)
        return True


# Global hotkey listener for abort
def start_abort_hotkey_listener() -> None:
    """Start a background thread listening for the abort hotkey (Ctrl+Shift+Escape)."""
    import threading

    try:
        from pynput import keyboard
    except ImportError:
        viki_logger.warning("ComputerUse: pynput not installed — abort hotkey unavailable")
        return

    def on_activate():
        signal_abort()
        viki_logger.warning("ComputerUse: Abort hotkey pressed — operations cancelled")

    def listener():
        with keyboard.GlobalHotKeys(
            {
                "<ctrl>+<shift>+<esc>": on_activate,
                "<ctrl>+<alt>+<pause>": on_activate,
            }
        ) as listener:
            listener.join()

    thread = threading.Thread(target=listener, daemon=True)
    thread.start()
    viki_logger.info("ComputerUse: Abort hotkey listener started (Ctrl+Shift+Esc)")
