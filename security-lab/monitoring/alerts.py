"""
Derive human-readable security alerts from audit entries.

Purpose
-------
Turn structured audit rows into dashboard-friendly alerts without a separate
alerting product (appropriate for a single-tenant local lab).

Security risks
--------------
- Alert rules tuned too loosely → noise; too tight → missed signals.

Mitigations
-----------
- Version rules alongside detector thresholds; log tuning changes to audit.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Import AuditEntry only for typing — avoid circular imports at runtime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.audit_store import AuditEntry


def alerts_from_audit_entries(entries: List["AuditEntry"], limit: int = 50) -> List[Dict[str, Any]]:
    """Build alerts from recent audit rows (newest first in ``entries``)."""
    out: List[Dict[str, Any]] = []
    for e in entries[:limit]:
        if e.kind == "chat":
            p = e.payload
            if p.get("blocked"):
                out.append(
                    {
                        "level": "warning",
                        "kind": "prompt_heuristic",
                        "ts": e.ts,
                        "audit_id": e.id,
                        "summary": "Chat blocked by injection heuristic",
                        "detail": {
                            "injection_score": p.get("injection_score"),
                            "session_id": p.get("session_id"),
                        },
                    }
                )
            elif (p.get("injection_score") or 0) >= 0.35 and not p.get("blocked"):
                out.append(
                    {
                        "level": "info",
                        "kind": "elevated_injection_score",
                        "ts": e.ts,
                        "audit_id": e.id,
                        "summary": "Chat allowed but injection score elevated",
                        "detail": {"injection_score": p.get("injection_score")},
                    }
                )
        elif e.kind == "tool":
            p = e.payload
            if p.get("ok") is False:
                out.append(
                    {
                        "level": "warning",
                        "kind": "tool_failure",
                        "ts": e.ts,
                        "audit_id": e.id,
                        "summary": f"Tool failure: {p.get('tool')}",
                        "detail": {"tool": p.get("tool"), "role": p.get("role")},
                    }
                )
    return out
