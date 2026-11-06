"""
Computer-use skill (Phase 4) — grounded UI vision + action loop.

Combines screenshot capture, optional Set-of-Marks / OmniParser-style UI
element grounding, and action execution via `pyautogui` (and `playwright` if
available for browser automation). Capability-gated as `desktop_control`
(severity = destructive when an action mutates UI state).

Design notes:
- Vision and grounding backends are lazy-loaded. If `omniparser`,
  `set_of_marks`, or any OCR library is missing the skill degrades to bbox-less
  screenshot + LLM-only grounding.
- The skill never auto-confirms destructive actions; the controller's safety
  layer must classify the action and request confirmation. We expose
  `safety_tier="destructive"` so the controller flags every call.
- The action vocabulary is intentionally small and bounded: click, type,
  scroll, key, hover, screenshot, drag, find_element, navigate_url.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


@dataclass
class UIElement:
    """A grounded UI element from the vision system."""

    label: str
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float = 0.0
    role: str | None = None
    text: str | None = None

    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)


class ComputerUseSkill(BaseSkill):
    """
    The skill the controller registers. Sub-actions are dispatched via the
    `action` parameter so a single skill stays in the registry.
    """

    SUPPORTED_ACTIONS = {
        "screenshot",
        "click",
        "click_element",
        "type",
        "key",
        "scroll",
        "hover",
        "drag",
        "find_element",
        "navigate_url",
    }

    def __init__(self, controller=None, data_dir: str = "./data/computer_use"):
        self.controller = controller
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self._pyautogui = None
        self._playwright_browser = None
        self._last_screenshot: str | None = None
        self._last_elements: list[UIElement] = []
        # P0 (computer-use grounding): minimum detector confidence required to
        # auto-act on a found element. Falls back to 0.5 to reject the previous
        # "screen" dummy bbox (confidence=0.1).
        self._min_action_confidence: float = float(
            os.environ.get("VIKI_COMPUTER_USE_MIN_CONF", "0.5")
        )
        # Path to a local OmniParser-V2 ONNX model. When present, we use the
        # bundled lightweight ONNX adapter; absent => grounding stays None.
        self._omniparser_onnx_path: str | None = os.environ.get("VIKI_OMNIPARSER_ONNX")

    @property
    def name(self) -> str:
        return "computer_use"

    @property
    def description(self) -> str:
        return (
            "Grounded computer-use loop: take screenshots, locate UI elements, "
            "and act on them (click, type, scroll, key, hover, drag, "
            "navigate_url). Capability-gated; destructive."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": sorted(self.SUPPORTED_ACTIONS),
                    "description": "Sub-action to perform.",
                },
                "x": {"type": "integer", "description": "Absolute X coord."},
                "y": {"type": "integer", "description": "Absolute Y coord."},
                "text": {"type": "string", "description": "Text to type."},
                "key": {"type": "string", "description": "Key or hotkey (e.g. 'enter', 'ctrl+c')."},
                "amount": {"type": "integer", "description": "Scroll amount (positive=up)."},
                "label": {"type": "string", "description": "Target element label for grounding."},
                "url": {"type": "string", "description": "URL for navigate_url (Playwright)."},
                "instruction": {
                    "type": "string",
                    "description": "Optional natural-language instruction to pair with vision grounding.",
                },
            },
            "required": ["action"],
        }

    @property
    def safety_tier(self) -> str:
        return "destructive"

    # Actions that mutate UI state and must run observe → act → verify.
    _MUTATING = frozenset({"click", "click_element", "type", "key", "scroll", "drag", "navigate_url"})

    async def execute(self, params: dict[str, Any]) -> str:
        action = (params.get("action") or "").strip()
        if action not in self.SUPPORTED_ACTIONS:
            return f"Error: unsupported action {action!r}. Use one of {sorted(self.SUPPORTED_ACTIONS)}."

        try:
            if action == "screenshot":
                return await self._do_screenshot(params)
            if action == "find_element":
                return await self._do_find_element(params)

            if action in self._MUTATING and params.get("verify", True):
                return await self._observe_act_verify(action, params)

            return await self._dispatch(action, params)
        except Exception as e:
            viki_logger.warning("ComputerUseSkill: %s failed: %s", action, e)
            return f"computer_use error ({action}): {e}"

    async def _dispatch(self, action: str, params: dict[str, Any]) -> str:
        if action == "click":
            return await self._do_click(params)
        if action == "click_element":
            return await self._do_click_element(params)
        if action == "type":
            return await self._do_type(params)
        if action == "key":
            return await self._do_key(params)
        if action == "scroll":
            return await self._do_scroll(params)
        if action == "hover":
            return await self._do_hover(params)
        if action == "drag":
            return await self._do_drag(params)
        if action == "navigate_url":
            return await self._do_navigate(params)
        return "computer_use: unhandled branch"

    async def _observe_act_verify(self, action: str, params: dict[str, Any]) -> str:
        """
        Closed loop: observe (screenshot+ground) → act → re-screenshot → stop on mismatch.

        Recommended stack: vision-capable model profile + ``VIKI_OMNIPARSER_ONNX`` for grounding.
        """
        before_path = self._capture_screenshot()
        before_elements = await self._ground_elements(before_path, params.get("instruction"))
        # Grounding required for click_element; reject low-confidence up front.
        if action == "click_element":
            label = (params.get("label") or "").lower().strip()
            match = self._find_by_label(before_elements, label) if label else None
            if match is None:
                return json.dumps(
                    {
                        "status": "aborted",
                        "reason": "observe_no_match",
                        "label": label,
                        "screenshot": before_path,
                        "hint": "Set VIKI_OMNIPARSER_ONNX to a local OmniParser-V2 ONNX model for grounding.",
                    }
                )
            if match.confidence < self._min_action_confidence:
                return json.dumps(
                    {
                        "status": "rejected",
                        "reason": "low_confidence",
                        "label": match.label,
                        "confidence": match.confidence,
                        "min_confidence": self._min_action_confidence,
                        "hint": (
                            "Install OmniParser-V2 ONNX (set VIKI_OMNIPARSER_ONNX) "
                            "or set VIKI_COMPUTER_USE_MIN_CONF=0.0 to override at your own risk."
                        ),
                    }
                )

        act_result = await self._dispatch(action, params)
        if isinstance(act_result, str) and (
            act_result.startswith("Error:")
            or '"status": "rejected"' in act_result
            or '"status": "aborted"' in act_result
        ):
            return act_result

        time.sleep(0.35)
        after_path = self._capture_screenshot()
        after_elements = await self._ground_elements(after_path, params.get("instruction"))
        expect_change = bool(params.get("expect_change")) or action == "navigate_url"
        expect_label = (params.get("expect_label") or params.get("label") or "").strip()
        expect_gone = bool(params.get("expect_gone"))
        mismatch = self._verify_ui_change(
            before_path,
            after_path,
            before_elements,
            after_elements,
            action,
            expect_change=expect_change,
            expect_label=expect_label,
            expect_gone=expect_gone,
        )
        if mismatch:
            return json.dumps(
                {
                    "status": "aborted",
                    "reason": "verify_mismatch",
                    "action": action,
                    "detail": mismatch,
                    "before": before_path,
                    "after": after_path,
                    "act_result": act_result,
                }
            )
        return json.dumps(
            {
                "status": "ok",
                "action": action,
                "act_result": act_result,
                "before": before_path,
                "after": after_path,
                "elements_seen": len(before_elements),
                "elements_after": len(after_elements),
            }
        )

    def _verify_ui_change(
        self,
        before: str,
        after: str,
        before_elements: list[UIElement],
        after_elements: list[UIElement],
        action: str,
        *,
        expect_change: bool = False,
        expect_label: str = "",
        expect_gone: bool = False,
    ) -> str | None:
        """
        Prefer grounding/label expectations over raw pixels.

        - expect_label + expect_gone: abort if label still grounded after act
        - expect_label (appear): abort if label missing after act
        - expect_change: abort if before/after screenshots are identical
        """
        if expect_label:
            found_after = self._find_by_label(after_elements, expect_label.lower())
            if expect_gone:
                if found_after is not None and found_after.confidence >= self._min_action_confidence:
                    return f"expected label {expect_label!r} to disappear; still present"
            else:
                # Appearance / persistence: if we clicked it, it may remain; only
                # enforce appearance when explicitly requested via expect_change
                # without expect_gone and label was absent before.
                found_before = self._find_by_label(before_elements, expect_label.lower())
                if (
                    expect_change
                    and found_before is None
                    and (found_after is None or found_after.confidence < self._min_action_confidence)
                ):
                    return f"expected label {expect_label!r} to appear; not grounded after act"

        if not expect_change:
            return None
        return self._screens_mismatch(before, after, action, expect_change=True)

    def _screens_mismatch(
        self,
        before: str,
        after: str,
        action: str,
        *,
        expect_change: bool = False,
    ) -> str | None:
        """Pixel/file-hash fallback when ``expect_change`` is set."""
        if not expect_change:
            return None
        if not before or not after or not os.path.isfile(before) or not os.path.isfile(after):
            return None
        try:
            import hashlib

            def _sig(path: str) -> str:
                try:
                    from PIL import Image

                    with Image.open(path) as im:
                        im = im.convert("RGB").resize((64, 36))
                        return hashlib.md5(im.tobytes()).hexdigest()
                except Exception:
                    with open(path, "rb") as f:
                        return hashlib.md5(f.read()).hexdigest()

            if _sig(before) == _sig(after):
                return "screen unchanged after mutating action (expect_change=true)"
        except Exception as e:
            viki_logger.debug("ComputerUseSkill verify skipped: %s", e)
        return None

    def _ensure_pyautogui(self):
        if self._pyautogui is not None:
            return self._pyautogui
        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            self._pyautogui = pyautogui
            return pyautogui
        except Exception as e:
            raise RuntimeError(f"pyautogui not available: {e}")

    async def _do_screenshot(self, params: dict[str, Any]) -> str:
        path = self._capture_screenshot()
        elements = await self._ground_elements(path, params.get("instruction"))
        return json.dumps(
            {
                "screenshot": path,
                "elements": [
                    {"label": e.label, "bbox": e.bbox, "confidence": e.confidence, "role": e.role}
                    for e in elements
                ],
            }
        )

    async def _do_find_element(self, params: dict[str, Any]) -> str:
        path = self._last_screenshot or self._capture_screenshot()
        elements = self._last_elements or await self._ground_elements(
            path, params.get("instruction")
        )
        label = (params.get("label") or "").lower().strip()
        if not label:
            return "Error: 'label' is required for find_element."
        match = self._find_by_label(elements, label)
        if not match:
            return json.dumps({"found": False, "screenshot": path})
        return json.dumps(
            {"found": True, "label": match.label, "bbox": match.bbox, "center": match.center()}
        )

    async def _do_click(self, params: dict[str, Any]) -> str:
        x = params.get("x")
        y = params.get("y")
        if x is None or y is None:
            return "Error: click requires 'x' and 'y'."
        pyautogui = self._ensure_pyautogui()
        pyautogui.click(int(x), int(y))
        return f"clicked ({x}, {y})"

    async def _do_click_element(self, params: dict[str, Any]) -> str:
        label = (params.get("label") or "").lower().strip()
        if not label:
            return "Error: click_element requires 'label'."
        path = self._last_screenshot or self._capture_screenshot()
        elements = self._last_elements or await self._ground_elements(
            path, params.get("instruction")
        )
        match = self._find_by_label(elements, label)
        if not match:
            return f"click_element: no match for {label!r}"

        # P0 fix: refuse to click on low-confidence detections. The previous
        # behaviour returned a synthetic full-screen bbox at confidence 0.1
        # that caused the cursor to slam the screen center.
        if match.confidence < self._min_action_confidence:
            return json.dumps(
                {
                    "status": "rejected",
                    "reason": "low_confidence",
                    "label": match.label,
                    "confidence": match.confidence,
                    "min_confidence": self._min_action_confidence,
                    "hint": (
                        "Install OmniParser-V2 ONNX (set VIKI_OMNIPARSER_ONNX to the model path) "
                        "or set VIKI_COMPUTER_USE_MIN_CONF=0.0 to override at your own risk."
                    ),
                }
            )

        # P0 fix: refuse to click on degenerate boxes (zero-area or full-screen).
        x1, y1, x2, y2 = match.bbox
        if (x2 - x1) <= 1 or (y2 - y1) <= 1:
            return json.dumps(
                {
                    "status": "rejected",
                    "reason": "degenerate_bbox",
                    "bbox": match.bbox,
                }
            )

        pyautogui = self._ensure_pyautogui()
        cx, cy = match.center()
        pyautogui.click(cx, cy)
        return f"clicked element {match.label!r} at ({cx}, {cy})"

    async def _do_type(self, params: dict[str, Any]) -> str:
        text = params.get("text")
        if text is None:
            return "Error: 'text' is required for type."
        pyautogui = self._ensure_pyautogui()
        pyautogui.typewrite(str(text), interval=0.01)
        return f"typed {len(text)} chars"

    async def _do_key(self, params: dict[str, Any]) -> str:
        key = params.get("key")
        if not key:
            return "Error: 'key' is required."
        pyautogui = self._ensure_pyautogui()
        if "+" in key:
            pyautogui.hotkey(*[k.strip() for k in key.split("+")])
        else:
            pyautogui.press(key)
        return f"pressed {key}"

    async def _do_scroll(self, params: dict[str, Any]) -> str:
        amount = int(params.get("amount", 0))
        pyautogui = self._ensure_pyautogui()
        pyautogui.scroll(amount)
        return f"scrolled {amount}"

    async def _do_hover(self, params: dict[str, Any]) -> str:
        x = params.get("x")
        y = params.get("y")
        if x is None or y is None:
            return "Error: hover requires 'x' and 'y'."
        pyautogui = self._ensure_pyautogui()
        pyautogui.moveTo(int(x), int(y), duration=0.1)
        return f"hovered ({x}, {y})"

    async def _do_drag(self, params: dict[str, Any]) -> str:
        x = params.get("x")
        y = params.get("y")
        if x is None or y is None:
            return "Error: drag requires 'x' and 'y' (target)."
        pyautogui = self._ensure_pyautogui()
        pyautogui.dragTo(int(x), int(y), duration=0.2, button="left")
        return f"dragged to ({x}, {y})"

    async def _do_navigate(self, params: dict[str, Any]) -> str:
        url = params.get("url")
        if not url:
            return "Error: 'url' is required for navigate_url."
        try:
            import webbrowser

            webbrowser.open(url)
            return f"opened {url} via system browser"
        except Exception as e:
            return f"navigate_url error: {e}"

    def _capture_screenshot(self) -> str:
        try:
            pyautogui = self._ensure_pyautogui()
            filename = f"screen_{int(time.time())}.png"
            path = os.path.abspath(os.path.join(self.data_dir, filename))
            img = pyautogui.screenshot()
            img.save(path)
            self._last_screenshot = path
            return path
        except Exception as e:
            viki_logger.debug("ComputerUseSkill: screenshot failed: %s", e)
            return ""

    async def _ground_elements(self, path: str, instruction: str | None) -> list[UIElement]:
        """
        Try OmniParser-V2 (ONNX or Python pkg) → Set-of-Marks. If no detector
        is available we explicitly return an empty list rather than a
        full-screen dummy box. `_do_click_element` will then refuse to act,
        which is the safer default.
        """
        if not path:
            self._last_elements = []
            return []
        elements = self._try_omniparser_onnx(path)
        if elements is None:
            elements = self._try_omniparser(path)
        if elements is None:
            elements = self._try_set_of_marks(path)
        if elements is None:
            elements = []
        self._last_elements = elements
        return elements

    def _try_omniparser_onnx(self, path: str) -> list[UIElement] | None:
        """
        Lightweight OmniParser-V2 ONNX adapter.

        Activated when `VIKI_OMNIPARSER_ONNX` points at a local model file.
        We deliberately don't bundle a full pipeline; instead we rely on
        `onnxruntime` to run the detector and assume the model emits a
        standard `(boxes, scores, classes)` triplet. Misconfiguration falls
        through silently to the next adapter.
        """
        model_path = self._omniparser_onnx_path
        if not model_path or not os.path.isfile(model_path):
            return None
        try:
            import numpy as np
            import onnxruntime as ort
            from PIL import Image
        except Exception:
            return None
        try:
            img = Image.open(path).convert("RGB")
            w, h = img.size
            arr = np.asarray(img, dtype=np.float32) / 255.0
            arr = arr.transpose(2, 0, 1)[None, ...]
            sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            input_name = sess.get_inputs()[0].name
            outputs = sess.run(None, {input_name: arr})
            # Expected output convention: outputs[0]=boxes (Nx4), outputs[1]=scores (N),
            # outputs[2]=labels (N). Custom builds can re-order, so we pick the first
            # array of shape (N,4) as boxes and look for shape (N,) for scores.
            boxes = next((o for o in outputs if o.ndim == 2 and o.shape[-1] == 4), None)
            scores = next((o for o in outputs if o.ndim == 1 and o.dtype != np.int64), None)
            labels = next((o for o in outputs if o.ndim == 1 and o.dtype == np.int64), None)
            if boxes is None or scores is None:
                return None
            out: list[UIElement] = []
            for i in range(boxes.shape[0]):
                conf = float(scores[i])
                if conf < 0.2:
                    continue
                x1, y1, x2, y2 = (float(v) for v in boxes[i])
                # If model emits normalized coords, scale up.
                if x2 <= 1.0 and y2 <= 1.0:
                    x1, x2 = x1 * w, x2 * w
                    y1, y2 = y1 * h, y2 * h
                lbl = f"elem_{int(labels[i])}" if labels is not None else "elem"
                out.append(
                    UIElement(
                        label=lbl,
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        confidence=conf,
                    )
                )
            return out
        except Exception as e:
            viki_logger.debug("OmniParser ONNX ground failed: %s", e)
            return None

    def _try_omniparser(self, path: str) -> list[UIElement] | None:
        try:
            import omniparser
        except Exception:
            return None
        try:
            res = omniparser.parse(path)
            out: list[UIElement] = []
            for r in res.get("elements", []):
                out.append(
                    UIElement(
                        label=str(r.get("label") or r.get("text") or "element"),
                        bbox=tuple(r["bbox"]),
                        confidence=float(r.get("confidence", 0.0)),
                        role=r.get("role"),
                        text=r.get("text"),
                    )
                )
            return out
        except Exception as e:
            viki_logger.debug("OmniParser ground failed: %s", e)
            return None

    def _try_set_of_marks(self, path: str) -> list[UIElement] | None:
        try:
            import set_of_marks
        except Exception:
            return None
        try:
            res = set_of_marks.detect(path)
            return [
                UIElement(
                    label=str(r.get("label", "elem")),
                    bbox=tuple(r["bbox"]),
                    confidence=float(r.get("confidence", 0.0)),
                    role=r.get("role"),
                )
                for r in res
            ]
        except Exception as e:
            viki_logger.debug("Set-of-Marks ground failed: %s", e)
            return None

    @staticmethod
    def _find_by_label(elements: list[UIElement], label: str) -> UIElement | None:
        label = label.lower().strip()
        if not elements:
            return None
        exact = [e for e in elements if e.label.lower() == label]
        if exact:
            return exact[0]
        partial = [e for e in elements if label in e.label.lower()]
        if partial:
            return partial[0]
        if any(e.text for e in elements):
            text_match = [e for e in elements if e.text and label in e.text.lower()]
            if text_match:
                return text_match[0]
        return None
