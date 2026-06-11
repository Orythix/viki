import json
import os
import sqlite3
import threading
import time
from typing import Any

from viki.config.logger import viki_logger


class TelemetryStore:
    """
    Centralized telemetry store for distributed traceability.
    Stores routing decisions, execution logs, and system anomalies in SQLite.
    Uses a persistent connection with WAL mode for better concurrent performance.
    """

    _lock = threading.Lock()

    def __init__(self, data_dir: str):
        self.db_path = os.path.join(data_dir, "telemetry.db")
        os.makedirs(data_dir, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                category TEXT,
                event_type TEXT,
                payload TEXT,
                severity TEXT
            )
        """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON events(category)")
        conn.commit()

    def record(
        self, category: str, event_type: str, payload: dict[str, Any], severity: str = "INFO"
    ):
        """Record a telemetry event."""
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO events (timestamp, category, event_type, payload, severity) VALUES (?, ?, ?, ?, ?)",
                    (time.time(), category, event_type, json.dumps(payload), severity),
                )
                conn.commit()
        except Exception as e:
            viki_logger.debug(f"Telemetry recording failed: {e}")

    def query(
        self, category: str | None = None, severity: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Query recent events."""
        query = "SELECT timestamp, category, event_type, payload, severity FROM events"
        params: list[Any] = []
        where_clauses: list[str] = []

        if category:
            where_clauses.append("category = ?")
            params.append(category)
        if severity:
            where_clauses.append("severity = ?")
            params.append(severity)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        results = []
        try:
            with self._lock:
                conn = self._get_conn()
                cursor = conn.execute(query, params)
                for row in cursor:
                    results.append(
                        {
                            "timestamp": row[0],
                            "category": row[1],
                            "event_type": row[2],
                            "payload": json.loads(row[3]),
                            "severity": row[4],
                        }
                    )
        except Exception as e:
            viki_logger.error(f"Telemetry query failed: {e}")

        return results

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of system health based on recent telemetry."""
        summary: dict[str, Any] = {"total_events": 0, "errors": 0, "warnings": 0, "categories": {}}
        try:
            with self._lock:
                conn = self._get_conn()
                cursor = conn.execute("SELECT severity, COUNT(*) FROM events GROUP BY severity")
                for row in cursor:
                    severity, count = row
                    if severity == "ERROR":
                        summary["errors"] = count
                    elif severity == "WARNING":
                        summary["warnings"] = count
                    summary["total_events"] += count

                cursor = conn.execute("SELECT category, COUNT(*) FROM events GROUP BY category")
                for row in cursor:
                    cat, count = row
                    summary["categories"][cat] = count
        except Exception as e:
            viki_logger.debug(f"Telemetry summary failed: {e}")

        return summary

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
