"""Image analysis skill: OCR, properties, format conversion, and vision-LLM forwarding.

Provides four capabilities:
  1. **ocr** – Extract text from images via pytesseract (requires Tesseract system package).
  2. **properties** – Dimensions, format, mode, file size, DPI.
  3. **describe** – Forward image to a vision LLM for description/analysis.
  4. **convert** – Convert between image formats (PNG, JPEG, WebP, etc.).

Degrades gracefully when optional dependencies (Pillow, pytesseract) are missing.
"""

from __future__ import annotations

import os
from typing import Any

from viki.skills.base import BaseSkill

_HAS_PIL = False
_HAS_TESSERACT = False

try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:
    pass

try:
    import pytesseract

    _HAS_TESSERACT = True
except ImportError:
    pass


def _get_tesseract_version() -> str:
    if not _HAS_TESSERACT:
        return ""
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return ""


def _check_tesseract_binary() -> bool:
    if not _HAS_TESSERACT:
        return False
    try:
        ver = _get_tesseract_version()
        return bool(ver)
    except Exception:
        return False


def _extract_ocr(image_path: str, lang: str = "eng") -> str:
    if not _HAS_PIL:
        return "OCR unavailable: Pillow not installed. Install with: pip install Pillow"
    if not _check_tesseract_binary():
        return "OCR unavailable: pytesseract or Tesseract system package not found. Install with: pip install pytesseract && (apt install tesseract-ocr / brew install tesseract / choco install tesseract)"
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=lang)
        return text.strip() or "(no text detected)"
    except Exception as e:
        return f"OCR error: {e}"


def _extract_properties(image_path: str) -> dict[str, Any]:
    if not _HAS_PIL:
        return {"error": "Pillow not installed. Install with: pip install Pillow"}
    try:
        img = Image.open(image_path)
        info: dict[str, Any] = {
            "format": img.format or "unknown",
            "mode": img.mode,
            "width": img.width,
            "height": img.height,
            "file_size_bytes": os.path.getsize(image_path),
        }
        if hasattr(img, "info") and img.info:
            dpi = img.info.get("dpi")
            if dpi:
                info["dpi"] = dpi
        return info
    except Exception as e:
        return {"error": f"Failed to read properties: {e}"}


def _convert_image(image_path: str, output_format: str, output_dir: str | None = None) -> str:
    if not _HAS_PIL:
        return "Conversion unavailable: Pillow not installed. Install with: pip install Pillow"
    try:
        img = Image.open(image_path)
        base, _ = os.path.splitext(os.path.basename(image_path))
        out_dir = output_dir or os.path.dirname(os.path.abspath(image_path)) or "."
        out_path = os.path.join(out_dir, f"{base}.{output_format.lower()}")
        rgb = img.convert("RGB") if output_format.upper() in ("JPEG", "JPG") else img
        rgb.save(out_path, format=output_format.upper())
        return out_path
    except Exception as e:
        return f"Conversion error: {e}"


class ImageAnalysisSkill(BaseSkill):
    """Analyze image files: OCR text extraction, properties, vision LLM description, format conversion."""

    @property
    def name(self) -> str:
        return "analyze_image"

    @property
    def description(self) -> str:
        return (
            "Analyze an image file: extract text (OCR), read properties (dimensions/format/size), "
            "describe contents via vision LLM, or convert between image formats. "
            "Action: analyze_image(path='...', task='ocr'|'properties'|'describe'|'convert'|'all')."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the image file to analyze.",
                },
                "task": {
                    "type": "string",
                    "enum": ["ocr", "properties", "describe", "convert", "all"],
                    "description": (
                        "What to do with the image. "
                        "ocr = extract text; properties = dimensions/format/size; "
                        "describe = forward to vision LLM for description (returns the path for the vision pipeline); "
                        "convert = change image format; "
                        "all = everything except convert."
                    ),
                    "default": "all",
                },
                "output_format": {
                    "type": "string",
                    "description": "Target format for conversion (png, jpeg, webp, gif, bmp). Only used when task='convert'.",
                    "default": "png",
                },
                "ocr_lang": {
                    "type": "string",
                    "description": "Tesseract language code (e.g., 'eng', 'fra', 'deu', 'rus').",
                    "default": "eng",
                },
            },
            "required": ["path"],
        }

    @property
    def safety_tier(self) -> str:
        return "safe"

    async def execute(self, params: dict[str, Any]) -> str:
        image_path = (params.get("path") or "").strip()
        if not image_path:
            return "Error: 'path' parameter is required."

        if not os.path.isfile(image_path):
            return f"Error: file not found: {image_path}"

        task = (params.get("task") or "all").strip().lower()
        output_format = (params.get("output_format") or "png").strip().lower()
        ocr_lang = (params.get("ocr_lang") or "eng").strip()

        lines: list[str] = []

        if task in ("properties", "all"):
            props = _extract_properties(image_path)
            lines.append("--- Image Properties ---")
            if "error" in props:
                lines.append(props["error"])
            else:
                for key, value in props.items():
                    lines.append(f"  {key}: {value}")

        if task in ("ocr", "all"):
            lines.append("--- OCR Text ---")
            lines.append(_extract_ocr(image_path, lang=ocr_lang))

        if task == "convert":
            result = _convert_image(image_path, output_format)
            lines.append("--- Format Conversion ---")
            lines.append(f"Result: {result}")

        if task == "describe":
            lines.append(f"Image path: {image_path}")
            lines.append("Instruction: Analyze and describe this image in detail.")

        return "\n".join(lines)
