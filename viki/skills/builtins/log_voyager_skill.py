import os
import re
from typing import Dict, Any, List, Optional
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class LogVoyagerSkill(BaseSkill):
    """
    Skill for distributed root-cause analysis via log correlation.
    Scans viki.log and thoughts.log for anomalies and links them to system state.
    """
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        self._telemetry = None
        if controller and hasattr(controller, "telemetry"):
            self._telemetry = controller.telemetry

    @property
    def name(self) -> str:
        return "log_voyager"

    @property
    def description(self) -> str:
        return "Analyzes system telemetry and logs for root-cause analysis. Actions: scan, analyze, summarize."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["scan", "analyze", "summarize", "trace"],
                    "description": "Log analysis action"
                },
                "query": {
                    "type": "string",
                    "description": "Keyword to search for (ERROR, WARNING, etc.)"
                },
                "category": {
                    "type": "string",
                    "description": "Telemetry category (routing, execution, system)"
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Number of items to retrieve"
                }
            },
            "required": ["action"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        query = params.get("query", "ERROR")
        category = params.get("category")
        limit = params.get("limit", 20)
        
        try:
            if action == "trace":
                return self._trace_events(category, query, limit)
            elif action == "scan":
                # Fallback to file scan if telemetry is unavailable or specifically requested
                return self._scan_logs(query, limit)
            elif action == "analyze":
                return self._analyze_anomalies(limit)
            elif action == "summarize":
                return self._summarize_health()
            
            return f"Error: Unknown action '{action}'"
        except Exception as e:
            viki_logger.error(f"LogVoyager Error: {e}")
            return f"Log Analysis Failed: {str(e)}"

    def _trace_events(self, category: Optional[str], query: str, limit: int) -> str:
        """Query the centralized telemetry store."""
        if not self._telemetry:
            return "Error: Telemetry store not initialized in controller."
        
        events = self._telemetry.query(category=category, limit=limit)
        if not events:
            return f"No telemetry events found for category='{category or 'any'}', query='{query}'."
            
        lines = [f"--- Telemetry Trace (Last {len(events)} events) ---"]
        for e in events:
            ts = time.strftime('%H:%M:%S', time.localtime(e['timestamp']))
            lines.append(f"[{ts}] [{e['severity']}] [{e['category']}] {e['event_type']}: {e['payload']}")
            
        return "\n".join(lines)

    def _scan_logs(self, query: str, limit: int) -> str:
        # Resolve log directory
        log_dir = os.path.join(os.getcwd(), "logs")
        if not os.path.exists(log_dir):
            log_dir = os.path.join(os.path.dirname(os.getcwd()), "logs")
            if not os.path.exists(log_dir):
                return "Error: Logs directory not found."

        results = []
        log_files = ["viki.log", "thoughts.log"]
        
        for log_name in log_files:
            path = os.path.join(log_dir, log_name)
            if not os.path.exists(path):
                continue
                
            matches = []
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    for line in reversed(lines):
                        if query.upper() in line.upper():
                            matches.append(line.strip())
                        if len(matches) >= limit:
                            break
                if matches:
                    results.append(f"--- MATCHES IN {log_name} ---")
                    results.extend(matches)
            except Exception as e:
                results.append(f"Error reading {log_name}: {e}")
        
        return "\n".join(results) if results else f"No logs matching '{query}' found."

    def _analyze_anomalies(self, limit: int) -> str:
        if self._telemetry:
            errors = self._telemetry.query(severity="ERROR", limit=limit)
            if errors:
                lines = ["--- Telemetry Anomaly Analysis ---"]
                for e in errors:
                    lines.append(f"ERROR in {e['category']}: {e['payload'].get('message', str(e['payload']))}")
                return "\n".join(lines)
        
        return self._scan_logs("ERROR", limit)

    def _summarize_health(self) -> str:
        if self._telemetry:
            summary = self._telemetry.get_summary()
            status = "HEALTHY"
            if summary["errors"] > 5: status = "CRITICAL"
            elif summary["errors"] > 0 or summary["warnings"] > 5: status = "DEGRADED"
            
            lines = [
                "--- System Telemetry Summary ---",
                f"Status:   {status}",
                f"Total Events: {summary['total_events']}",
                f"Active Errors: {summary['errors']}",
                f"Active Warnings: {summary['warnings']}",
                "Category Breakdown:"
            ]
            for cat, count in summary["categories"].items():
                lines.append(f"  - {cat}: {count}")
            return "\n".join(lines)

        return "Error: Telemetry store not available for summary."
