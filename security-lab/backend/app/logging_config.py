"""Structured logging for audit correlation (request_id, user role, event type)."""
from __future__ import annotations

import logging
import sys
from typing import Any, Dict

from pythonjsonlogger import jsonlogger


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    fmt = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"levelname": "severity", "asctime": "timestamp"},
    )
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_security_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    payload: Dict[str, Any] = {"event": event, **fields}
    logger.warning("security_event", extra={"extra_fields": payload})
