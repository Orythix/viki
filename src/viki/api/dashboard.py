"""Local web dashboard for VIKI.

A lightweight aiohttp app exposing chat, runtime health, sovereign status,
memory search, and mission state over HTTP — served with a single-page UI.
Binds to localhost by default; no auth is applied, so do not expose the port
publicly without a reverse proxy.

Usage::

    python -m viki --dashboard            # CLI flag
    # or programmatically:
    from viki.api.dashboard import run_dashboard
    await run_dashboard(controller)
"""

from __future__ import annotations

import json
import os
from typing import Any

from aiohttp import web

from viki.config.logger import viki_logger

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8321


def _json(data: Any, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, default=str),
        status=status,
        content_type="application/json",
    )


def create_dashboard_app(controller: Any) -> web.Application:
    """Build the aiohttp application bound to a VIKIController."""

    async def index(_request: web.Request) -> web.StreamResponse:
        page = os.path.join(_STATIC_DIR, "dashboard.html")
        if not os.path.isfile(page):
            return web.Response(text="dashboard.html missing", status=500)
        return web.FileResponse(page)

    async def health(_request: web.Request) -> web.Response:
        return _json(controller.get_runtime_health())

    async def status(_request: web.Request) -> web.Response:
        try:
            return _json(controller.get_sovereign_status())
        except Exception as e:
            return _json({"error": str(e)}, status=500)

    async def memory(request: web.Request) -> web.Response:
        query = request.query.get("q", "").strip()
        if not query:
            return _json({"error": "missing ?q="}, status=400)
        limit = min(int(request.query.get("limit", 8)), 50)
        lessons = controller.learning.get_relevant_lessons(query, limit=limit)
        return _json({"query": query, "lessons": lessons})

    async def mission(_request: web.Request) -> web.Response:
        active = controller.world.get_active_mission() if controller.world else None
        return _json({"active_mission": active})

    async def chat(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return _json({"error": "invalid JSON body"}, status=400)
        text = (body.get("text") or "").strip()
        if not text:
            return _json({"error": "missing 'text'"}, status=400)
        session_id = body.get("session_id") or "dashboard"
        try:
            reply = await controller.process_request(text, session_id=session_id)
            return _json({"reply": reply, "session_id": session_id})
        except Exception as e:
            viki_logger.error("Dashboard chat failed: %s", e)
            return _json({"error": str(e)}, status=500)

    app = web.Application()
    app.add_routes(
        [
            web.get("/", index),
            web.get("/api/health", health),
            web.get("/api/status", status),
            web.get("/api/memory", memory),
            web.get("/api/mission", mission),
            web.post("/api/chat", chat),
        ]
    )
    return app


async def run_dashboard(
    controller: Any,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> web.AppRunner:
    """Start the dashboard server. Returns the runner (call cleanup() to stop)."""
    app = create_dashboard_app(controller)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    viki_logger.info("VIKI dashboard running at http://%s:%d", host, port)
    return runner
