"""
Screen / image vision skill.

When a vision-capable model profile is available via the controller's model
router, returns a VLM description (and optional Set-of-Marks hints). When no
VLM is available, returns an honest stub — never pretends a PNG path alone is
a successful analysis.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from typing import Any

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


class VisionSkill(BaseSkill):
    """
    Skill to allow VIKI to 'see' the user's screen.
    Uses pyautogui for screenshots + optional VLM description.
    """

    def __init__(self, data_dir: str = "./data/vision", controller: Any = None):
        self.data_dir = data_dir
        self.controller = controller
        os.makedirs(self.data_dir, exist_ok=True)

    @property
    def name(self) -> str:
        return "look_at_screen"

    @property
    def description(self) -> str:
        return (
            "Takes a screenshot (or analyzes provided images) and describes visual "
            "information via a vision-capable model when available. "
            "Action: look_at_screen(instruction='...')."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": (
                        "What to look for or analyze in the screenshot "
                        "(e.g., 'read the error message', 'describe the UI')."
                    ),
                },
                "image_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: existing image paths instead of a new screenshot.",
                },
                "action": {
                    "type": "string",
                    "description": "Optional alias (describe_screen) for computer-use callers.",
                },
            },
            "required": [],
        }

    def _resolve_controller(self) -> Any:
        return self.controller

    def _get_vision_model(self) -> Any | None:
        ctrl = self._resolve_controller()
        router = getattr(ctrl, "model_router", None) if ctrl is not None else None
        if router is None:
            return None
        try:
            model = router.get_model(capabilities=["vision"])
            # Reject models that do not advertise vision/multimodal.
            caps = set(getattr(model, "capabilities", None) or [])
            if caps and not (caps & {"vision", "multimodal", "image"}):
                return None
            return model
        except Exception as e:
            viki_logger.debug("VisionSkill: no vision model: %s", e)
            return None

    async def _describe_with_vlm(self, image_path: str, instruction: str) -> str | None:
        model = self._get_vision_model()
        if model is None:
            return None
        messages = [
            {
                "role": "system",
                "content": (
                    "You are VIKI's vision module. Describe the image accurately. "
                    "If asked to locate UI elements, list labels and approximate positions."
                ),
            },
            {"role": "user", "content": instruction or "Describe what you see."},
        ]
        try:
            if hasattr(model, "chat"):
                # Prefer image_path kwarg (local/api multimodal providers).
                try:
                    return await model.chat(messages, temperature=0.2, image_path=image_path)
                except TypeError:
                    return await model.chat(messages, temperature=0.2)
        except Exception as e:
            viki_logger.warning("VisionSkill: VLM describe failed: %s", e)
        return None

    async def execute(self, params: dict[str, Any]) -> str:
        instruction = params.get("instruction") or "What's on the screen?"
        if (params.get("action") or "").strip() == "describe_screen":
            instruction = instruction or "Describe the current screen and notable UI elements."

        image_paths: list[str] = []
        input_images = params.get("image_paths", []) or []
        preamble: list[str] = []

        if input_images:
            for path in input_images:
                if os.path.exists(path):
                    image_paths.append(path)
                    preamble.append(f"Analyzing provided image: {path}")
                else:
                    preamble.append(f"Image not found: {path}")
        else:
            filename = f"screenshot_{secrets.token_hex(4)}.png"
            filepath = os.path.abspath(os.path.join(self.data_dir, filename))
            try:
                import pyautogui

                viki_logger.info("Visualizing screen for instruction: %s", instruction)
                await asyncio.to_thread(pyautogui.screenshot, filepath)
                image_paths.append(filepath)
                preamble.append(f"Screenshot captured successfully at: {filepath}")
            except Exception as e:
                viki_logger.error("Vision error: %s", e)
                return f"Error capturing screen: {e}"

        if not image_paths:
            return "\n".join(preamble) + "\n[vision stub] No readable image path available."

        primary = image_paths[0]
        description = await self._describe_with_vlm(primary, instruction)
        if description:
            return (
                "\n".join(preamble)
                + f"\nInstruction: {instruction}\n"
                + "--- VLM description ---\n"
                + description.strip()
            )

        # Honest stub — path alone is not a successful visual analysis.
        return (
            "\n".join(preamble)
            + f"\nInstruction: {instruction}\n"
            + "[vision stub] No vision-capable model is configured. "
            "Load a multimodal profile (capabilities include vision) in config/models.yaml "
            "or set a cloud vision provider. Screenshot path is available for grounding "
            f"via OmniParser (VIKI_OMNIPARSER_ONNX) at: {primary}"
        )
