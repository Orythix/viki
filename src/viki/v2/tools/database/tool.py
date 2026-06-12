"""DatabaseTool — SQL queries and schema inspection."""

from __future__ import annotations

from ...core.permission_manager import PermissionTier
from ..base import BaseTool, ToolResult
from .providers import DBProvider, create_provider


class DatabaseTool(BaseTool):
    name = "database"
    description = (
        "Execute SQL queries, inspect schemas, manage databases (SQLite, PostgreSQL, MySQL)."
    )
    capabilities = [
        "query",
        "describe",
        "tables",
        "connect",
    ]
    permission_tier = PermissionTier.ELEVATED
    examples = [
        "Show all tables in the database",
        "Describe the users table",
        "Run SELECT * FROM users LIMIT 10",
        "Execute INSERT INTO logs VALUES (...)",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["query", "describe", "tables", "connect"],
                "description": "Database action",
            },
            "connection_string": {
                "type": "string",
                "description": "DB connection string (e.g., sqlite:///data.db)",
            },
            "db_type": {
                "type": "string",
                "description": "Database type: sqlite, postgresql, mysql",
            },
            "query": {"type": "string", "description": "SQL query to execute"},
            "table": {"type": "string", "description": "Table name for describe/tables"},
        },
        "required": ["action"],
    }

    def __init__(self):
        self._provider: DBProvider | None = None
        self._connected = False

    async def get_permission_tier(self, params: dict) -> PermissionTier:
        action = params.get("action", "")
        if action in ("tables", "describe", "query"):
            # Check if it's a SELECT query
            query = params.get("query", "").strip().upper()
            if action == "query" and not query.startswith("SELECT"):
                return PermissionTier.ADMIN
            return PermissionTier.ELEVATED
        return PermissionTier.ADMIN

    async def execute(self, params: dict, provider=None) -> ToolResult:
        action = params.get("action")

        try:
            if action == "connect":
                conn_str = params.get("connection_string")
                db_type = params.get("db_type", "sqlite")
                if not conn_str:
                    return ToolResult(
                        success=False,
                        error="connection_string required",
                        error_type="invalid_parameters",
                    )
                p = create_provider(db_type)
                await p.connect(conn_str)
                self._provider = p
                self._connected = True
                return ToolResult(success=True, data={"connected": True, "type": db_type})

            if not self._connected or not self._provider:
                return ToolResult(
                    success=False,
                    error="Not connected. Call connect first.",
                    error_type="not_found",
                )

            p = self._provider

            if action == "tables":
                tables = await p.tables()
                return ToolResult(success=True, data={"tables": tables})

            elif action == "describe":
                table = params.get("table")
                if not table:
                    return ToolResult(
                        success=False,
                        error="table name required",
                        error_type="invalid_parameters",
                    )
                columns = await p.describe_table(table)
                return ToolResult(success=True, data={"table": table, "columns": columns})

            elif action == "query":
                query = params.get("query")
                if not query:
                    return ToolResult(
                        success=False,
                        error="query required",
                        error_type="invalid_parameters",
                    )
                query_upper = query.strip().upper()
                if query_upper.startswith("SELECT"):
                    rows = await p.fetch_all(query)
                    return ToolResult(success=True, data={"rows": rows, "count": len(rows)})
                else:
                    result = await p.execute(query)
                    return ToolResult(success=True, data={"rowcount": result.rowcount})

            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    error_type="invalid_parameters",
                )

        except Exception as e:
            return ToolResult(success=False, error=str(e), error_type="execution_failed")
