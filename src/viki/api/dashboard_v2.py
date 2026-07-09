"""
Dashboard v2 — enhanced web dashboard with mission board, router telemetry
charts, scorecard trends, and PWA manifest.
"""

from __future__ import annotations

import time
from typing import Any

from aiohttp import web

PWA_MANIFEST = {
    "name": "VIKI Dashboard",
    "short_name": "VIKI",
    "description": "Personal AI assistant dashboard",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0d1117",
    "theme_color": "#58a6ff",
    "icons": [
        {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
    ],
}


def register_dashboard_v2_routes(app: web.Application, controller: Any) -> None:
    """Register v2 dashboard routes on the app."""

    @app.router.add_get("/api/v2/missions")  # type: ignore[call-arg, operator]
    async def list_missions(request: web.Request) -> web.Response:
        mc = getattr(controller, "mission_control", None)
        if mc is None:
            return web.json_response({"missions": []})
        missions = []
        for m in mc.active_missions.values():
            missions.append(m.to_dict())
        return web.json_response({"missions": missions})

    @app.router.add_post("/api/v2/missions/{id}/pause")  # type: ignore[call-arg, operator]
    async def pause_mission(request: web.Request) -> web.Response:
        mission_id = request.match_info["id"]
        mc = getattr(controller, "mission_control", None)
        if mc is None:
            return web.json_response({"error": "No mission control"}, status=500)
        mission = mc.active_missions.get(mission_id)
        if mission:
            mission.status = "paused"
            mc._save_missions()
            return web.json_response({"status": "paused"})
        return web.json_response({"error": "Not found"}, status=404)

    @app.router.add_post("/api/v2/missions/{id}/cancel")  # type: ignore[call-arg, operator]
    async def cancel_mission(request: web.Request) -> web.Response:
        mission_id = request.match_info["id"]
        mc = getattr(controller, "mission_control", None)
        if mc is None:
            return web.json_response({"error": "No mission control"}, status=500)
        mission = mc.active_missions.pop(mission_id, None)
        if mission:
            mission.status = "cancelled"
            mc._save_missions()
            return web.json_response({"status": "cancelled"})
        return web.json_response({"error": "Not found"}, status=404)

    @app.router.add_get("/api/v2/telemetry")  # type: ignore[call-arg, operator]
    async def get_telemetry(request: web.Request) -> web.Response:
        rt = getattr(controller, "router_telemetry", None)
        if rt is None:
            return web.json_response({"router": {}, "providers": []})
        try:
            stats = rt.get_stats() if hasattr(rt, "get_stats") else {}
            return web.json_response(
                {
                    "router": stats,
                    "providers": rt.provider_stats if hasattr(rt, "provider_stats") else [],
                }
            )
        except Exception:
            return web.json_response({"router": {}, "providers": []})

    @app.router.add_get("/api/v2/scorecard")  # type: ignore[call-arg, operator]
    async def get_scorecard(request: web.Request) -> web.Response:
        sc = getattr(controller, "scorecard", None)
        if sc is None:
            return web.json_response({"trends": [], "current": {}})
        try:
            trends = sc.get_trends() if hasattr(sc, "get_trends") else []
            current = sc.get_current_scores() if hasattr(sc, "get_current_scores") else {}
            return web.json_response({"trends": trends, "current": current})
        except Exception:
            return web.json_response({"trends": [], "current": {}})

    @app.router.add_get("/api/v2/watchers")  # type: ignore[call-arg, operator]
    async def list_watchers(request: web.Request) -> web.Response:
        wm = getattr(controller, "watcher_manager", None)
        if wm is None:
            return web.json_response({"watchers": []})
        watchers = [
            {
                "id": w.id,
                "name": w.name,
                "kind": w.kind,
                "enabled": w.enabled,
                "total_firings": w.total_firings,
                "last_fired": w.last_fired,
            }
            for w in wm.list_watchers()
        ]
        return web.json_response({"watchers": watchers})

    @app.router.add_get("/manifest.json")  # type: ignore[call-arg, operator]
    async def manifest(request: web.Request) -> web.Response:
        return web.json_response(PWA_MANIFEST)

    @app.router.add_get("/api/v2/system/status")  # type: ignore[call-arg, operator]
    async def system_status(request: web.Request) -> web.Response:
        uptime = time.time() - getattr(controller, "_start_time", time.time())
        return web.json_response(
            {
                "version": getattr(controller, "version", "8.3.0"),
                "uptime_seconds": uptime,
                "active_missions": len(getattr(controller, "mission_control", None) or []),
                "skills_loaded": len(getattr(controller, "skill_registry", None) or []),
                "memory_count": getattr(controller, "learning_module", None)
                and controller.learning_module.get_total_lesson_count()
                or 0,
                "router_provider": str(
                    getattr(getattr(controller, "model_router", None), "provider_name", "unknown")
                ),
            }
        )
