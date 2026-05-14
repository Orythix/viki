from app.audit_store import AuditEntry
from monitoring.alerts import alerts_from_audit_entries


def test_alerts_blocked_chat() -> None:
    entries = [
        AuditEntry("1", 1.0, "chat", {"blocked": True, "injection_score": 0.9, "session_id": "s1"}),
    ]
    a = alerts_from_audit_entries(entries)
    assert len(a) == 1
    assert a[0]["kind"] == "prompt_heuristic"


def test_alerts_tool_failure() -> None:
    entries = [
        AuditEntry("2", 2.0, "tool", {"ok": False, "tool": "http_get_sandbox"}),
    ]
    a = alerts_from_audit_entries(entries)
    assert any(x["kind"] == "tool_failure" for x in a)


def test_alerts_elevated_score() -> None:
    entries = [
        AuditEntry("3", 3.0, "chat", {"blocked": False, "injection_score": 0.5}),
    ]
    a = alerts_from_audit_entries(entries)
    assert any(x["kind"] == "elevated_injection_score" for x in a)
