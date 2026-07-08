"""
Live smoke tests against labs/security-lab (FastAPI).

Run:
  cd labs/security-lab/backend && set PYTHONPATH=.. && uvicorn app.main:app --port 8000
  cd labs/qa-automation && set QA_LIVE_API=1 && set QA_API_KEY=dev-lab-change-me && pytest tests/live -m smoke -v
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


@pytest.mark.smoke
def test_health_ok(api_client) -> None:
    r = api_client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"


@pytest.mark.smoke
def test_metrics_requires_auth(api_client) -> None:
    r = api_client.get_unauthenticated("/api/v1/metrics")
    assert r.status_code == 401


@pytest.mark.smoke
def test_metrics_with_auth(api_client) -> None:
    r = api_client.get("/api/v1/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "counters" in body


@pytest.mark.smoke
def test_injection_harness(api_client) -> None:
    r = api_client.get("/api/v1/security/harness/injection")
    assert r.status_code == 200
    data = r.json()
    assert "cases" in data
    assert len(data["cases"]) >= 1
