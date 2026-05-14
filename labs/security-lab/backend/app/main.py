"""
FastAPI entrypoint — local AI security learning lab backend.

Run (dev):
  cd labs/security-lab/backend
  set PYTHONPATH=..   # PowerShell: $env:PYTHONPATH=(Resolve-Path ..).Path
  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Repo layout: labs/security-lab/backend/app, labs/security-lab/security
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.agent_core import AgentCore  # noqa: E402
from app.agent_memory import SessionMemory  # noqa: E402
from app.audit_store import AuditStore  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.rbac import RBACPolicy  # noqa: E402
from app.tools_registry import ToolRegistry  # noqa: E402
from monitoring.alerts import alerts_from_audit_entries  # noqa: E402
from monitoring.telemetry import resource_snapshot  # noqa: E402
from security.adversarial_analysis import adversarial_prompt_report  # noqa: E402
from security.injection_detector import analyze_prompt  # noqa: E402
from security.secrets_redact import redact_mapping  # noqa: E402
from security.testing_harness import (  # noqa: E402
    run_injection_suite,
    run_jailbreak_policy_suite,
    run_memory_poisoning_check,
    run_tool_abuse_checks,
)

setup_logging()
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AI Security Learning Lab", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _cors_origins() -> List[str]:
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_memory = SessionMemory()
_audit: Optional[AuditStore] = None
_rbac: Optional[RBACPolicy] = None
_agent: Optional[AgentCore] = None
_metrics: Dict[str, Any] = {"requests": 0, "blocked": 0, "tokens_in": 0, "tokens_out": 0}


@app.on_event("startup")
def startup() -> None:
    global _audit, _rbac, _agent
    settings = get_settings()
    _audit = AuditStore(settings.database_url)
    _rbac = RBACPolicy(settings.rbac_policy_path)
    tools = ToolRegistry(settings)
    _agent = AgentCore(settings, _memory, tools, sandbox_hosts=["sandbox-demo", "localhost", "127.0.0.1"])
    logger.info("lab_started", extra={"extra_fields": {"ollama": settings.ollama_url}})


def require_api_key(request: Request) -> None:
    settings = get_settings()
    key = request.headers.get("x-lab-api-key", "")
    if key != settings.lab_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def get_lab_role(request: Request) -> str:
    role = request.headers.get("x-lab-role", "").strip()
    if role:
        return role
    if _rbac is not None:
        return _rbac.default_role()
    return "observer"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=65536)
    session_id: Optional[str] = None
    # Lab only: allow observing detector without blocking (never in production)
    observe_only: bool = False


class ToolRequest(BaseModel):
    name: str
    payload: Dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/chat")
@limiter.limit("120/minute")
async def chat(request: Request, body: ChatRequest) -> Dict[str, Any]:
    require_api_key(request)
    settings = get_settings()
    role = get_lab_role(request)
    if not _rbac.allowed(role, "chat"):
        raise HTTPException(403, "role cannot chat")
    assert _agent and _audit

    sid = body.session_id or str(uuid.uuid4())
    _metrics["requests"] += 1

    result = await _agent.chat(sid, body.message, skip_injection_block=body.observe_only)
    if result.get("blocked"):
        _metrics["blocked"] += 1
    else:
        te = result.get("tokens_estimated") or {}
        _metrics["tokens_in"] += int(te.get("in") or 0)
        _metrics["tokens_out"] += int(te.get("out") or 0)

    _audit.append(
        "chat",
        redact_mapping(
            {
                "session_id": sid,
                "role": role,
                "blocked": result.get("blocked"),
                "injection_score": result.get("injection_score"),
                "injection_reasons": result.get("injection_reasons"),
                "output_redacted": result.get("output_redacted"),
            }
        ),
    )
    return {"session_id": sid, **result}


@app.post("/api/v1/tools/execute")
@limiter.limit("120/minute")
async def tools_execute(request: Request, body: ToolRequest) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    assert _agent and _audit
    perms = _rbac.permissions_for(role)
    tr = await _agent.run_tool(body.name, body.payload, perms)
    _audit.append(
        "tool",
        redact_mapping(
            {
                "role": role,
                "tool": body.name,
                "ok": tr.ok,
                "meta": tr.meta,
                "output_chars": len(tr.output or ""),
            }
        ),
    )
    return {"ok": tr.ok, "output": tr.output, "meta": tr.meta}


@app.get("/api/v1/audit")
def audit(request: Request, limit: int = 50) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    if not _rbac.allowed(role, "audit.read"):
        raise HTTPException(403, "role cannot read audit")
    assert _audit
    rows = _audit.recent(limit=limit)
    return {
        "items": [
            {"id": r.id, "ts": r.ts, "kind": r.kind, "payload": r.payload} for r in rows
        ]
    }


@app.get("/api/v1/metrics")
def metrics(request: Request) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    if not _rbac.allowed(role, "metrics.read"):
        raise HTTPException(403, "role cannot read metrics")
    return {"counters": dict(_metrics), "ts": time.time()}


@app.get("/api/v1/monitoring/summary")
def monitoring_summary(request: Request, audit_limit: int = 80) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    if not _rbac.allowed(role, "metrics.read"):
        raise HTTPException(403, "role cannot read monitoring summary")
    assert _audit
    entries = _audit.recent(limit=audit_limit)
    alerts = alerts_from_audit_entries(entries, limit=50)
    tool_rows = [e for e in entries if e.kind == "tool"]
    return {
        "metrics": dict(_metrics),
        "resources": resource_snapshot(),
        "alerts": alerts,
        "recent_tool_events": [
            {"id": e.id, "ts": e.ts, "payload": e.payload} for e in tool_rows[:30]
        ],
        "ts": time.time(),
    }


@app.post("/api/v1/security/classify")
def security_classify(request: Request, body: ChatRequest) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    if not _rbac.allowed(role, "security.test"):
        raise HTTPException(403, "role cannot run security tests")
    r = analyze_prompt(body.message)
    return {"score": r.score, "reasons": r.reasons, "blocked": r.blocked}


@app.get("/api/v1/security/harness/injection")
def harness_injection(request: Request) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    if not _rbac.allowed(role, "security.test"):
        raise HTTPException(403, "role cannot run security tests")
    results = run_injection_suite()
    return {
        "cases": [
            {"name": n, "passed": ok, "score": rep.score, "reasons": rep.reasons}
            for n, ok, rep in results
        ]
    }


@app.get("/api/v1/security/harness/jailbreak")
def harness_jailbreak_policy(request: Request) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    if not _rbac.allowed(role, "security.test"):
        raise HTTPException(403, "role cannot run security tests")
    results = run_jailbreak_policy_suite()
    return {
        "cases": [
            {"name": n, "passed": ok, "score": rep.score, "reasons": rep.reasons}
            for n, ok, rep in results
        ]
    }


@app.get("/api/v1/security/harness/tools")
def harness_tools(request: Request) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    if not _rbac.allowed(role, "security.test"):
        raise HTTPException(403, "role cannot run security tests")
    checks = run_tool_abuse_checks()
    return {"checks": checks, "all_passed": all(c["passed"] for c in checks)}


@app.post("/api/v1/security/harness/memory")
def harness_memory(request: Request, body: ChatRequest) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    if not _rbac.allowed(role, "security.test"):
        raise HTTPException(403, "role cannot run security tests")
    sanitized, changed = run_memory_poisoning_check(body.message)
    return {"sanitized": sanitized, "mutated": changed}


@app.post("/api/v1/security/analyze")
def security_analyze_full(request: Request, body: ChatRequest) -> Dict[str, Any]:
    require_api_key(request)
    role = get_lab_role(request)
    if not _rbac.allowed(role, "security.test"):
        raise HTTPException(403, "role cannot run security tests")
    settings = get_settings()
    return adversarial_prompt_report(body.message, settings.max_prompt_chars)
