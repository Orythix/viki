import os
import sqlite3
import time
import json
from typing import Dict, Any, List, Optional
from viki.config.logger import viki_logger

class TelemetryStore:
    """
    Centralized telemetry store for distributed traceability.
    Stores routing decisions, execution logs, and system anomalies in SQLite.
    """
    
    def __init__(self, data_dir: str):
        self.db_path = os.path.join(data_dir, "telemetry.db")
        os.makedirs(data_dir, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    category TEXT,
                    event_type TEXT,
                    payload TEXT,
                    severity TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON events(category)")

    def record(self, category: str, event_type: str, payload: Dict[str, Any], severity: str = "INFO"):
        """Record a telemetry event."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO events (timestamp, category, event_type, payload, severity) VALUES (?, ?, ?, ?, ?)",
                    (time.time(), category, event_type, json.dumps(payload), severity)
                )
        except Exception as e:
            viki_logger.debug(f"Telemetry recording failed: {e}")

    def query(self, category: Optional[str] = None, severity: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Query recent events."""
        query = "SELECT timestamp, category, event_type, payload, severity FROM events"
        params = []
        where_clauses = []
        
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(query, params)
                for row in cursor:
                    results.append({
                        "timestamp": row[0],
                        "category": row[1],
                        "event_type": row[2],
                        "payload": json.loads(row[3]),
                        "severity": row[4]
                    })
        except Exception as e:
            viki_logger.error(f"Telemetry query failed: {e}")
            
        return results

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of system health based on recent telemetry."""
        summary = {
            "total_events": 0,
            "errors": 0,
            "warnings": 0,
            "categories": {}
        }
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Count totals
                cursor = conn.execute("SELECT severity, COUNT(*) FROM events GROUP BY severity")
                for row in cursor:
                    severity, count = row
                    if severity == "ERROR": summary["errors"] = count
                    elif severity == "WARNING": summary["warnings"] = count
                    summary["total_events"] += count
                
                # Category breakdown
                cursor = conn.execute("SELECT category, COUNT(*) FROM events GROUP BY category")
                for row in cursor:
                    cat, count = row
                    summary["categories"][cat] = count
        except Exception as e:
            viki_logger.debug(f"Telemetry summary failed: {e}")
            
        return summary
