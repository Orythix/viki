"""Tests for the web dashboard API endpoints."""

import pytest
from aiohttp.test_utils import TestClient, TestServer

from viki.api.dashboard import create_dashboard_app


class StubLearning:
    def get_relevant_lessons(self, query, limit=8):
        return [f"lesson about {query}"][:limit]


class StubWorld:
    def get_active_mission(self):
        return {"goal": "test goal", "project": "demo", "phase": "EXECUTION"}


class StubController:
    def __init__(self):
        self.learning = StubLearning()
        self.world = StubWorld()

    def get_runtime_health(self):
        return {
            "degraded": False,
            "registered_skill_count": 12,
            "registered_skills": ["research"],
            "disabled_skills": {},
            "default_model": "phi3:mini",
            "available_models": ["phi3:mini"],
            "unavailable_models": {},
            "warnings": [],
        }

    def get_sovereign_status(self):
        return {"mode": "sovereign", "uptime_s": 42}

    async def process_request(
        self, text, on_event=None, on_think=None, attachment_paths=None, session_id=None
    ):
        return f"echo: {text}"


@pytest.fixture
async def client():
    app = create_dashboard_app(StubController())
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


async def test_health_endpoint(client):
    r = await client.get("/api/health")
    assert r.status == 200
    data = await r.json()
    assert data["default_model"] == "phi3:mini"
    assert data["degraded"] is False


async def test_status_endpoint(client):
    r = await client.get("/api/status")
    assert r.status == 200
    assert (await r.json())["mode"] == "sovereign"


async def test_memory_endpoint(client):
    r = await client.get("/api/memory?q=docker")
    assert r.status == 200
    data = await r.json()
    assert data["lessons"] == ["lesson about docker"]

    r = await client.get("/api/memory")
    assert r.status == 400


async def test_mission_endpoint(client):
    r = await client.get("/api/mission")
    data = await r.json()
    assert data["active_mission"]["phase"] == "EXECUTION"


async def test_chat_endpoint(client):
    r = await client.post("/api/chat", json={"text": "hello"})
    assert r.status == 200
    data = await r.json()
    assert data["reply"] == "echo: hello"
    assert data["session_id"] == "dashboard"

    r = await client.post("/api/chat", json={})
    assert r.status == 400


async def test_index_serves_html(client):
    r = await client.get("/")
    assert r.status == 200
    body = await r.text()
    assert "VIKI Dashboard" in body
