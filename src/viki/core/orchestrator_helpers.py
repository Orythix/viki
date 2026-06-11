"""Helper functions extracted from orchestrator.py to reduce file size."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def write_json(path: str, payload: Any, indent: int | None = None) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=indent, default=str)


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text_truncated(path: str, max_len: int) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read(max_len)


def load_yaml(path: str) -> dict[str, Any]:
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError, FileNotFoundError) as e:
        logger.warning("Failed to load YAML config from %s: %s", path, e)
        return {}


def persona_from_soul_path(soul_path: str) -> str:
    if not soul_path:
        return "sovereign"
    base = os.path.basename(soul_path)
    if "personas" in soul_path and base.endswith(".yaml"):
        return base[:-5]
    return "sovereign"


def json_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def is_explanation_requested(input_text: str) -> bool:
    triggers = {
        "explain",
        "why",
        "how does",
        "what does",
        "describe",
        "clarify",
        "elaborate",
        "break down",
        "in detail",
        "walk me through",
        "tell me about",
    }
    lower = input_text.lower().strip()
    return any(lower.startswith(t) or f" {t}" in lower or lower.endswith(t) for t in triggers)


def compress_output(text: str) -> str:
    lines = text.splitlines()
    compressed = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and "file:" not in stripped.lower():
            continue
        if stripped.startswith("```"):
            skip = not skip
            compressed.append(line)
            continue
        if skip:
            compressed.append(line)
            continue
        if stripped == "" and compressed and compressed[-1].strip() == "":
            continue
        compressed.append(line)
    return "\n".join(compressed)
