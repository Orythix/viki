"""
Host resource telemetry for local lab dashboards.

Purpose
-------
Expose coarse CPU / memory / disk signals so operators can correlate spikes with
abusive prompts or runaway tool use.

Security risks
--------------
- Metrics can indirectly leak workload patterns if exported off-host.

Mitigations
-----------
- Keep endpoints behind API key + RBAC; bind Docker ports to 127.0.0.1 only.
- Do not ship detailed per-process command lines in responses.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def resource_snapshot() -> dict[str, Any]:
    """
    Best-effort snapshot. If ``psutil`` is not installed, returns a stub
    (open-source optional dependency).
    """
    try:
        import psutil  # type: ignore
    except ImportError:
        logger.info("psutil_not_installed", extra={"extra_fields": {}})
        return {
            "available": False,
            "note": "Install psutil in the backend venv for CPU/memory metrics.",
            "ts": time.time(),
        }

    try:
        vm = psutil.virtual_memory()
        du = psutil.disk_usage(os.getcwd())
        load = os.getloadavg() if hasattr(os, "getloadavg") else None
        return {
            "available": True,
            "ts": time.time(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory": {
                "total": vm.total,
                "available": vm.available,
                "percent": vm.percent,
            },
            "disk_cwd": {
                "total": du.total,
                "free": du.free,
                "percent": du.percent,
            },
            "loadavg": load,
            "pid": os.getpid(),
        }
    except Exception as e:
        logger.warning("resource_snapshot_failed", extra={"extra_fields": {"err": str(e)}})
        return {"available": False, "error": str(e), "ts": time.time()}
