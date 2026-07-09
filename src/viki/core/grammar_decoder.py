"""
Grammar-constrained decoding for structured VIKIResponse output.

Uses Ollama's JSON-schema `format` parameter when available (Ollama ≥0.3.0)
and falls back to parse-and-retry for backends that don't support it.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from viki.config.logger import viki_logger

# JSON Schema for VIKIResponse (used for grammar-constrained decoding)
VIKI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response": {"type": "string", "description": "The main response text to the user"},
        "thought": {"type": "string", "description": "Internal reasoning (not shown to user)"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "description": "Name of the tool/skill to call"},
                    "params": {"type": "object", "description": "Parameters for the tool"},
                },
                "required": ["tool", "params"],
            },
        },
        "confidence": {
            "type": "number",
            "description": "Confidence in this response (0.0-1.0)",
            "minimum": 0,
            "maximum": 1,
        },
    },
    "required": ["response"],
}


def get_ollama_format_schema() -> dict[str, Any]:
    """Return the schema in Ollama's expected JSON format."""
    return {
        "type": "object",
        "properties": {
            "response": {"type": "string"},
            "thought": {"type": "string"},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["tool", "params"],
                },
            },
            "confidence": {"type": "number"},
        },
        "required": ["response"],
    }


def format_as_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Format a JSON schema for models that support constrained decoding."""
    return {
        "type": "json_schema",
        "json_schema": {"schema": schema},
    }


def supports_grammar(backend_name: str) -> bool:
    """Check if a backend supports grammar-constrained decoding."""
    grammar_support = {
        "ollama": True,
        "lm_studio": False,
        "openai": False,
        "azure": False,
        "anthropic": False,
        "google": False,
        "nvidia_nim": False,
    }
    return grammar_support.get(backend_name, False)


def extract_json_from_response(text: str) -> dict[str, Any] | None:
    """Robustly extract a JSON object from a model response."""
    # Try parsing the entire response first
    text = text.strip()
    try:
        return cast("dict[str, Any]", json.loads(text))
    except json.JSONDecodeError:
        pass

    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return cast("dict[str, Any]", json.loads(text[start : end + 1]))
        except json.JSONDecodeError:
            pass

    # Try to find a JSON code block
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        try:
            return cast("dict[str, Any]", json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass

    return None


def validate_against_schema(data: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, str]:
    """Basic schema validation without depending on a JSON Schema library."""
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            return False, f"Missing required field: {field}"

    props = schema.get("properties", {})
    for key, value in data.items():
        if key not in props:
            continue
        prop = props[key]
        prop_type = prop.get("type")
        if prop_type == "string" and not isinstance(value, str):
            return False, f"Field '{key}' should be string, got {type(value).__name__}"
        if prop_type == "array" and not isinstance(value, list):
            return False, f"Field '{key}' should be array, got {type(value).__name__}"
        if prop_type == "number" and not isinstance(value, int | float):
            return False, f"Field '{key}' should be number, got {type(value).__name__}"

    return True, ""


async def chat_with_grammar(
    model_router: Any,
    messages: list[dict[str, str]],
    schema: dict[str, Any] | None = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    """
    Send a chat request with grammar-constrained decoding.

    Uses the backend's native grammar support when available; falls back to
    parse-and-retry with schema validation.
    """
    schema = schema or VIKI_RESPONSE_SCHEMA
    backend_name = getattr(model_router, "provider_name", "") or ""

    if supports_grammar(backend_name):
        try:
            if hasattr(model_router, "chat_structured"):
                response = await model_router.chat_structured(
                    messages=messages,
                    schema=get_ollama_format_schema(),
                )
                if isinstance(response, dict):
                    valid, err = validate_against_schema(response, schema)
                    if valid:
                        return response
                    viki_logger.debug("Grammar response failed validation: %s", err)
        except Exception as e:
            viki_logger.debug("Grammar-constrained decoding failed: %s", e)

    # Fallback: parse-and-retry
    for attempt in range(max_retries + 1):
        try:
            if hasattr(model_router, "chat"):
                raw = await model_router.chat(messages)
            else:
                raw = str(await model_router.process_request(messages))

            parsed = extract_json_from_response(raw)
            if parsed is None:
                if attempt < max_retries:
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": "Please respond with valid JSON matching the required schema.",
                        }
                    )
                    continue
                return {
                    "response": str(raw)[:2000],
                    "thought": "",
                    "actions": [],
                    "confidence": 0.5,
                }

            valid, err = validate_against_schema(parsed, schema)
            if valid:
                return parsed

            if attempt < max_retries:
                messages.append({"role": "assistant", "content": json.dumps(parsed)})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Response failed validation: {err}. Please correct.",
                    }
                )
        except Exception as e:
            viki_logger.debug("chat_with_grammar attempt %d failed: %s", attempt, e)
            if attempt == max_retries:
                return {"response": str(e), "thought": "", "actions": [], "confidence": 0.0}

    return {"response": "", "thought": "", "actions": [], "confidence": 0.0}
