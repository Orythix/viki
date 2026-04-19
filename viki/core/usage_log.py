"""
Append-only session usage ledger (JSONL), analogous to lightweight client cost logs.

Events share one file: ``usage_session.jsonl`` under the configured data directory.
Each line is one JSON object with at least: ts, event, and event-specific fields.

Configure from VIKIController via ``system.session_usage_log`` and ``configure_session_usage_log``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional

_lock = threading.Lock()
_data_dir: Optional[str] = None
_enabled: bool = False

USAGE_FILENAME = "usage_session.jsonl"


def configure_session_usage_log(data_dir: str, enabled: bool) -> None:
    """Point the ledger at ``data_dir`` and enable or disable writes."""
    global _data_dir, _enabled
    _enabled = bool(enabled)
    if not _enabled:
        _data_dir = None
        return
    root = os.path.abspath(os.path.expanduser(data_dir))
    try:
        os.makedirs(root, exist_ok=True)
    except OSError:
        _enabled = False
        _data_dir = None
        return
    _data_dir = root


def _append(entry: Dict[str, Any]) -> None:
    if not _enabled or not _data_dir:
        return
    entry = dict(entry)
    entry.setdefault("ts", time.time())
    path = os.path.join(_data_dir, USAGE_FILENAME)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    try:
        with _lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except OSError:
        pass


def emit_llm_inference(
    provider: Any,
    latency_s: float,
    success: bool,
    method: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """One logical inference call (HTTP/API round-trip where applicable)."""
    model_name = getattr(provider, "model_name", "") or ""
    provider_cls = type(provider).__name__
    row: Dict[str, Any] = {
        "event": "llm_inference",
        "model_name": model_name,
        "provider_class": provider_cls,
        "method": method,
        "latency_ms": round(float(latency_s) * 1000.0, 3),
        "success": bool(success),
    }
    if extra:
        row.update(extra)
    _append(row)


def emit_model_feedback(provider: Any, latency_s: float, success: bool) -> None:
    """Trust/router feedback from ``LLMProvider.record_performance`` (may include non-LLM latencies)."""
    model_name = getattr(provider, "model_name", "") or ""
    provider_cls = type(provider).__name__
    trust = getattr(provider, "trust_score", None)
    _append(
        {
            "event": "model_feedback",
            "model_name": model_name,
            "provider_class": provider_cls,
            "latency_ms": round(float(latency_s) * 1000.0, 3),
            "success": bool(success),
            "trust_score": trust,
            "call_count": getattr(provider, "call_count", None),
        }
    )


def emit_skill_execution(
    skill_name: str,
    latency_s: float,
    success: bool,
    error: Optional[str] = None,
) -> None:
    row: Dict[str, Any] = {
        "event": "skill_execution",
        "skill_name": skill_name,
        "latency_ms": round(float(latency_s) * 1000.0, 3),
        "success": bool(success),
    }
    if error:
        err = error.strip()
        if len(err) > 400:
            err = err[:400] + "…"
        row["error"] = err
    _append(row)
