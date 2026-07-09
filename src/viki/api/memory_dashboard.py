"""
Memory dashboard endpoints — browse, search, pin, correct, and forget memories.

Extends the web dashboard with interactive memory management features that
hosted assistants cannot offer: user-editable, user-owned memory.
"""

from __future__ import annotations

from typing import Any

from aiohttp import web

from viki.config.logger import viki_logger


def register_memory_routes(app: web.Application, controller: Any) -> None:
    """Register memory management routes on the dashboard app."""

    async def list_memories(request: web.Request) -> web.Response:
        query = request.query.get("q", "")
        source = request.query.get("source", "")
        author = request.query.get("author", "")
        limit = int(request.query.get("limit", "50"))
        offset = int(request.query.get("offset", "0"))

        lm = controller.learning_module
        if lm is None:
            return web.json_response({"items": [], "total": 0})

        lessons = lm.get_lessons(
            query=query, source=source, author=author, limit=limit, offset=offset
        )
        total = lm.get_total_lesson_count()
        return web.json_response(
            {
                "items": lessons,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    async def get_memory(request: web.Request) -> web.Response:
        lesson_id = request.match_info.get("id", "")
        lm = controller.learning_module
        if lm is None:
            return web.json_response({"error": "Learning module unavailable"}, status=500)

        lessons = lm.get_lessons(query="", limit=1000)
        for lesson in lessons:
            if lesson.get("id") == lesson_id:
                return web.json_response(lesson)
        return web.json_response({"error": "Not found"}, status=404)

    async def update_memory(request: web.Request) -> web.Response:
        lesson_id = request.match_info.get("id", "")
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        lm = controller.learning_module
        if lm is None:
            return web.json_response({"error": "Learning module unavailable"}, status=500)

        fact = data.get("text_representation") or data.get("fact")
        reliability = data.get("reliability")
        success = lm.update_lesson(
            lesson_id=lesson_id,
            fact=fact,
            reliability=float(reliability) if reliability is not None else None,
        )
        if success:
            viki_logger.info("Memory dashboard: updated lesson %s", lesson_id)
            return web.json_response({"status": "updated"})
        return web.json_response({"error": "Not found"}, status=404)

    async def delete_memory(request: web.Request) -> web.Response:
        lesson_id = request.match_info.get("id", "")
        lm = controller.learning_module
        if lm is None:
            return web.json_response({"error": "Learning module unavailable"}, status=500)

        success = lm.delete_lesson(lesson_id)
        if success:
            viki_logger.info("Memory dashboard: deleted lesson %s", lesson_id)
            return web.json_response({"status": "deleted"})
        return web.json_response({"error": "Not found"}, status=404)

    async def pin_memory(request: web.Request) -> web.Response:
        lesson_id = request.match_info.get("id", "")
        lm = controller.learning_module
        if lm is None:
            return web.json_response({"error": "Learning module unavailable"}, status=500)
        lm.update_lesson(lesson_id=lesson_id, reliability=1.0)
        return web.json_response({"status": "pinned"})

    async def memory_stats(request: web.Request) -> web.Response:
        lm = controller.learning_module
        if lm is None:
            return web.json_response({"total": 0, "stable": 0, "frequent": 0})

        total = lm.get_total_lesson_count()
        stable = lm.get_stable_lesson_count()
        frequent = len(lm.get_frequent_lessons(min_count=3))
        return web.json_response(
            {
                "total": total,
                "stable": stable,
                "frequent": frequent,
            }
        )

    app.router.add_get("/api/memories", list_memories)
    app.router.add_get("/api/memories/stats", memory_stats)
    app.router.add_get("/api/memories/{id}", get_memory)
    app.router.add_put("/api/memories/{id}", update_memory)
    app.router.add_delete("/api/memories/{id}", delete_memory)
    app.router.add_post("/api/memories/{id}/pin", pin_memory)
