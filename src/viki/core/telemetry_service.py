"""
OpenTelemetry tracing scaffolding (Phase 6).

VIKI does not require an external OTel collector — when `opentelemetry-api`
is not installed the tracer becomes a no-op so production runs never break.
When it IS installed we set up:

    * a TracerProvider with a BatchSpanProcessor,
    * stdout export by default,
    * optional OTLP gRPC export when OTEL_EXPORTER_OTLP_ENDPOINT is set.

Use `start_span("name", attributes={...})` everywhere; it works whether or not
OTel is installed.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

_OTEL_TRACER = None
_OTEL_INITIALIZED = False
_LOCAL_RECORDS: list[dict[str, Any]] = []
_LOCAL_RECORDS_MAX = 500
_TRACE_DB: sqlite3.Connection | None = None
_TRACE_DB_LOCK = threading.Lock()
_TRACE_DB_PATH: str | None = None

# Parent-ID propagation via contextvars so nested `with start_span(...)` calls
# inherit the right parent without requiring callers to pass IDs around.
_CURRENT_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "viki_trace_id", default=None
)
_CURRENT_SPAN_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "viki_span_id", default=None
)


def init_tracing(service_name: str = "viki", export_to_stdout: bool = True) -> None:
    """
    Initialize the global tracer. Safe to call multiple times.

    If OpenTelemetry is not installed this is a no-op; spans degrade to
    in-memory records that can still be inspected via `get_local_spans()`.
    """
    global _OTEL_TRACER, _OTEL_INITIALIZED
    if _OTEL_INITIALIZED:
        return
    _OTEL_INITIALIZED = True
    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.sdk.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
    except Exception:
        _OTEL_TRACER = None
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    try:
        from opentelemetry.sdk.trace.export import (  # type: ignore
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        if export_to_stdout:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    except Exception:
        pass

    otlp_endpoint = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
            )
        except Exception:
            pass

    trace.set_tracer_provider(provider)
    _OTEL_TRACER = trace.get_tracer(service_name)


@contextlib.contextmanager
def start_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Context manager that starts a span. Yields a mutable dict the caller can
    add attributes / events to; values are flushed to the underlying tracer
    on `__exit__`.

    Always works, even when OpenTelemetry is not installed. We additionally
    set `trace_id` (one per top-level call) and `parent_span_id` so the
    dashboard can render a Gantt/flame view.
    """
    parent_span_id = _CURRENT_SPAN_ID.get()
    trace_id = _CURRENT_TRACE_ID.get() or uuid.uuid4().hex[:16]
    span_id = uuid.uuid4().hex[:16]

    info: dict[str, Any] = {
        "name": name,
        "attributes": dict(attributes or {}),
        "events": [],
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "started_at": time.time(),
    }
    trace_token = _CURRENT_TRACE_ID.set(trace_id)
    span_token = _CURRENT_SPAN_ID.set(span_id)
    start = time.perf_counter()
    span_cm = None
    span = None
    if _OTEL_TRACER is not None:
        try:
            span_cm = _OTEL_TRACER.start_as_current_span(name, attributes=info["attributes"])
            span = span_cm.__enter__()
        except Exception:
            span_cm = None
            span = None
    try:
        yield info
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        info["elapsed_ms"] = round(elapsed_ms, 3)
        info["finished_at"] = time.time()
        if span is not None:
            try:
                for k, v in info.get("attributes", {}).items():
                    span.set_attribute(k, v)
                for ev in info.get("events", []):
                    span.add_event(ev.get("name", "event"), attributes=ev.get("attributes") or {})
            except Exception:
                pass
        if span_cm is not None:
            try:
                span_cm.__exit__(None, None, None)
            except Exception:
                pass
        _record_local_span(info)
        _persist_span(info)
        _CURRENT_SPAN_ID.reset(span_token)
        _CURRENT_TRACE_ID.reset(trace_token)


def _record_local_span(info: dict[str, Any]) -> None:
    if len(_LOCAL_RECORDS) >= _LOCAL_RECORDS_MAX:
        _LOCAL_RECORDS.pop(0)
    _LOCAL_RECORDS.append(
        {
            "name": info.get("name"),
            "elapsed_ms": info.get("elapsed_ms"),
            "attributes": info.get("attributes"),
            "events": info.get("events"),
            "ts": info.get("started_at") or time.time(),
            "trace_id": info.get("trace_id"),
            "span_id": info.get("span_id"),
            "parent_span_id": info.get("parent_span_id"),
            "started_at": info.get("started_at"),
            "finished_at": info.get("finished_at"),
        }
    )


def init_persistent_traces(db_path: str) -> None:
    """Open a SQLite DB to persist spans. Idempotent."""
    global _TRACE_DB, _TRACE_DB_PATH
    if _TRACE_DB is not None:
        if _TRACE_DB_PATH == db_path:
            return
        # Different path: close existing one first to avoid leaks/locks
        close_persistent_traces()
    try:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spans (
                trace_id TEXT NOT NULL,
                span_id TEXT NOT NULL PRIMARY KEY,
                parent_span_id TEXT,
                name TEXT NOT NULL,
                attributes TEXT,
                started_at REAL NOT NULL,
                finished_at REAL,
                elapsed_ms REAL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_started ON spans(started_at)")
        conn.commit()
        _TRACE_DB = conn
        _TRACE_DB_PATH = db_path
    except Exception:
        _TRACE_DB = None


def _persist_span(info: dict[str, Any]) -> None:
    if _TRACE_DB is None:
        return
    try:
        with _TRACE_DB_LOCK:
            _TRACE_DB.execute(
                "INSERT OR REPLACE INTO spans "
                "(trace_id, span_id, parent_span_id, name, attributes, started_at, finished_at, elapsed_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    info.get("trace_id"),
                    info.get("span_id"),
                    info.get("parent_span_id"),
                    info.get("name"),
                    json.dumps(info.get("attributes") or {}, default=str),
                    info.get("started_at") or time.time(),
                    info.get("finished_at"),
                    info.get("elapsed_ms"),
                ),
            )
            _TRACE_DB.commit()
    except Exception:
        pass


def get_local_spans(limit: int = 100) -> list[dict[str, Any]]:
    """Return the most recent in-memory span records (newest first)."""
    return list(reversed(_LOCAL_RECORDS[-limit:]))


def get_persistent_traces(limit: int = 50) -> list[dict[str, Any]]:
    """
    Return the most recent traces grouped by trace_id, each with its full
    span list and earliest start time. Used by the dashboard's Gantt view.
    """
    if _TRACE_DB is None:
        return []
    try:
        cur = _TRACE_DB.execute(
            "SELECT trace_id, MIN(started_at) AS started_at, COUNT(*) AS span_count "
            "FROM spans GROUP BY trace_id ORDER BY started_at DESC LIMIT ?",
            (int(limit),),
        )
        traces = [
            dict(zip(("trace_id", "started_at", "span_count"), row, strict=False))
            for row in cur.fetchall()
        ]
        out: list[dict[str, Any]] = []
        for t in traces:
            cur = _TRACE_DB.execute(
                "SELECT trace_id, span_id, parent_span_id, name, attributes, "
                "started_at, finished_at, elapsed_ms "
                "FROM spans WHERE trace_id = ? ORDER BY started_at",
                (t["trace_id"],),
            )
            spans = []
            for row in cur.fetchall():
                attrs = {}
                try:
                    attrs = json.loads(row[4] or "{}")
                except Exception:
                    pass
                spans.append(
                    {
                        "trace_id": row[0],
                        "span_id": row[1],
                        "parent_span_id": row[2],
                        "name": row[3],
                        "attributes": attrs,
                        "started_at": row[5],
                        "finished_at": row[6],
                        "elapsed_ms": row[7],
                    }
                )
            out.append(
                {
                    "trace_id": t["trace_id"],
                    "started_at": t["started_at"],
                    "span_count": t["span_count"],
                    "spans": spans,
                }
            )
        return out
    except Exception:
        return []


def clear_local_spans() -> None:
    _LOCAL_RECORDS.clear()


def close_persistent_traces() -> None:
    """Close the SQLite connection used for persistent traces."""
    global _TRACE_DB, _TRACE_DB_PATH
    with _TRACE_DB_LOCK:
        if _TRACE_DB is not None:
            try:
                _TRACE_DB.close()
            except Exception:
                pass
            _TRACE_DB = None
            _TRACE_DB_PATH = None
