import os
from pathlib import Path

import pytest
from app.audit_store import AuditStore


def test_audit_store_sqlite_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    url = f"sqlite:///{db.as_posix()}"
    store = AuditStore(url)
    eid = store.append("tool", {"tool": "shell_echo", "ok": True})
    assert eid
    rows = store.recent(limit=10)
    assert len(rows) == 1
    assert rows[0].kind == "tool"
    assert rows[0].payload["tool"] == "shell_echo"


def test_audit_store_filters_kind(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'b.db').as_posix()}"
    store = AuditStore(url)
    store.append("chat", {"blocked": False})
    store.append("tool", {"ok": True})
    only_tool = store.recent(limit=10, kind="tool")
    assert len(only_tool) == 1
    assert only_tool[0].kind == "tool"


@pytest.mark.skipif(
    os.environ.get("LAB_TEST_POSTGRES_URL") is None,
    reason="Set LAB_TEST_POSTGRES_URL to run PostgreSQL audit tests",
)
def test_audit_store_postgres_roundtrip() -> None:
    url = os.environ["LAB_TEST_POSTGRES_URL"]
    store = AuditStore(url)
    eid = store.append("chat", {"blocked": True, "injection_score": 0.9})
    rows = store.recent(limit=5)
    assert any(r.id == eid for r in rows)
