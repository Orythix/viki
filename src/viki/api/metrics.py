"""Prometheus metrics for the VIKI web dashboard.

Provides HTTP-request instrumentation (counters, duration histograms,
in-progress gauge) and application-level gauges updated on each scrape.

Usage::

    from viki.api.metrics import setup_metrics
    setup_metrics(app, controller)

The ``/metrics`` endpoint is registered automatically.  If ``prometheus_client``
is not installed the endpoint returns ``501 Not Implemented`` so production
runs never break.
"""

from __future__ import annotations

import time
from typing import Any, cast

from aiohttp import web

from viki.api import CONTROLLER_KEY
from viki.config.logger import viki_logger

_metrics_enabled = False
_start_time = time.time()

_requests_total: Any = None
_request_duration: Any = None
_requests_in_progress: Any = None
_skills_gauge: Any = None
_missions_gauge: Any = None
_lessons_gauge: Any = None
_models_available_gauge: Any = None
_models_unavailable_gauge: Any = None
_llm_inferences_total: Any = None
_errors_total: Any = None
_uptime_gauge: Any = None
_websocket_connections: Any = None


def _init_metrics() -> None:
    global _metrics_enabled
    global _requests_total, _request_duration, _requests_in_progress
    global _skills_gauge, _missions_gauge, _lessons_gauge
    global _models_available_gauge, _models_unavailable_gauge
    global _llm_inferences_total, _errors_total, _uptime_gauge
    global _websocket_connections

    # Collectors live in a process-wide registry, so creating them twice raises
    # DuplicateTimeseries.  Multiple apps in one process share the same metrics.
    if _metrics_enabled:
        return

    try:
        from prometheus_client import Counter, Gauge, Histogram
    except ImportError:
        return

    _requests_total = Counter(
        "viki_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    _request_duration = Histogram(
        "viki_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    _requests_in_progress = Gauge(
        "viki_http_requests_in_progress",
        "HTTP requests currently in progress",
        ["method", "endpoint"],
    )
    _skills_gauge = Gauge("viki_skills_loaded", "Number of registered skills")
    _missions_gauge = Gauge("viki_missions_active", "Number of active missions")
    _lessons_gauge = Gauge("viki_memory_lessons_total", "Total memory lessons stored")
    _models_available_gauge = Gauge("viki_models_available", "Number of available models")
    _models_unavailable_gauge = Gauge("viki_models_unavailable", "Number of unavailable models")
    _llm_inferences_total = Counter(
        "viki_llm_inferences_total",
        "Total LLM inference calls",
        ["model", "success"],
    )
    _errors_total = Counter(
        "viki_errors_total",
        "Total errors by type",
        ["type"],
    )
    _uptime_gauge = Gauge("viki_uptime_seconds", "VIKI uptime in seconds")
    _websocket_connections = Gauge(
        "viki_websocket_connections_active",
        "Active WebSocket connections",
    )
    _metrics_enabled = True


def _update_app_gauges(controller: Any) -> None:
    if not _metrics_enabled:
        return
    try:
        sr = getattr(controller, "skill_registry", None)
        _skills_gauge.set(len(sr) if sr else 0)

        mc = getattr(controller, "mission_control", None)
        _missions_gauge.set(len(getattr(mc, "active_missions", {})) if mc else 0)

        lm = getattr(controller, "learning", None) or getattr(controller, "learning_module", None)
        total = 0
        if lm is not None:
            total = (
                lm.get_total_lesson_count()
                if hasattr(lm, "get_total_lesson_count")
                else len(getattr(lm, "lessons", []) or [])
            )
        _lessons_gauge.set(total)

        mr = getattr(controller, "model_router", None)
        if mr is not None:
            models = getattr(mr, "models", {}) or {}
            available = [m for m in models.values() if getattr(m, "enabled", False)]
            _models_available_gauge.set(len(available))
            _models_unavailable_gauge.set(len(models) - len(available))

        _uptime_gauge.set(time.time() - _start_time)
    except Exception as exc:
        viki_logger.debug("Failed to update prometheus gauges: %s", exc)


def _add_llm_inference(model_name: str, success: bool) -> None:
    if _metrics_enabled and _llm_inferences_total is not None:
        _llm_inferences_total.labels(model=model_name, success=str(success)).inc()


def _add_error(error_type: str) -> None:
    if _metrics_enabled and _errors_total is not None:
        _errors_total.labels(type=error_type).inc()


def _inc_websocket() -> None:
    if _metrics_enabled and _websocket_connections is not None:
        _websocket_connections.inc()


def _dec_websocket() -> None:
    if _metrics_enabled and _websocket_connections is not None:
        _websocket_connections.dec()


@web.middleware
async def _metrics_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    if not _metrics_enabled or request.path == "/metrics":
        return cast(web.StreamResponse, await handler(request))

    method = request.method
    endpoint = request.path
    _requests_in_progress.labels(method=method, endpoint=endpoint).inc()
    start = time.perf_counter()
    status = "200"
    try:
        response = await handler(request)
        status = str(getattr(response, "status", 200))
        return cast(web.StreamResponse, response)
    except web.HTTPException as exc:
        status = str(exc.status)
        raise
    except Exception as exc:
        status = "500"
        _add_error(type(exc).__name__)
        raise
    finally:
        _requests_in_progress.labels(method=method, endpoint=endpoint).dec()
        duration = time.perf_counter() - start
        if _requests_total is not None:
            _requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
        if _request_duration is not None:
            _request_duration.labels(method=method, endpoint=endpoint).observe(duration)


async def _handle_metrics(request: web.Request) -> web.Response:
    if not _metrics_enabled:
        return web.Response(
            text=(
                "prometheus_client not installed.\nInstall with: pip install prometheus-client\n"
            ),
            status=501,
            content_type="text/plain",
        )
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        controller = request.app.get(CONTROLLER_KEY)
        if controller is not None:
            _update_app_gauges(controller)

        data = generate_latest()
        return web.Response(body=data, content_type=CONTENT_TYPE_LATEST)
    except Exception as exc:
        viki_logger.error("Failed to generate prometheus metrics: %s", exc)
        return web.Response(
            text=f"Error generating metrics: {exc}\n",
            status=500,
            content_type="text/plain",
        )


def setup_metrics(app: web.Application, controller: Any) -> None:
    """Register Prometheus metrics middleware and ``/metrics`` endpoint on *app*.

    If ``prometheus_client`` is not installed the endpoint returns 501.
    """
    _init_metrics()
    app[CONTROLLER_KEY] = controller
    app.middlewares.append(_metrics_middleware)
    app.router.add_get("/metrics", _handle_metrics)
    viki_logger.info(
        "Prometheus metrics %s at /metrics",
        "enabled" if _metrics_enabled else "disabled (prometheus_client not found)",
    )
