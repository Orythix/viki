"""Conversation branch manager — fork, switch, compare, merge conversation traces.

Each branch is a named ``session_id`` with a parent pointer.  The actual
message trace lives in the existing working-memory ``messages`` table, so
branching reuses the session-isolation machinery that already exists.
"""

from __future__ import annotations

import difflib
import sqlite3
import threading
import time
import uuid
from typing import Any, cast

from viki.config.logger import viki_logger


class BranchManager:
    """Manage named conversation branches backed by working-memory sessions.

    Usage::

        bm = BranchManager(db_path="./data/branches.db")
        bm.fork("experiment-1", controller)      # snapshot current conv
        bm.switch("experiment-1", controller)     # restore its trace
        branches = bm.list_branches()
        diff = bm.diff("experiment-1", controller)
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, timeout=30.0)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS branches (
                name TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                parent_session_id TEXT,
                description TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fork(
        self,
        name: str,
        controller: Any,
        description: str = "",
        session_id: str | None = None,
    ) -> str:
        """Create a new branch by snapshotting the current conversation.

        Returns the new session_id.
        """
        now = time.time()
        current_sid = self._resolve_session_id(controller, session_id)
        trace = self._get_trace(controller, current_sid)
        new_sid = str(uuid.uuid4())

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO branches (name, session_id, parent_session_id, description, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (name, new_sid, current_sid, description, now, now),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return f"Branch '{name}' already exists."

        # Copy trace into the new session
        if trace:
            self._replace_trace(controller, new_sid, trace)

        viki_logger.info("Branch '%s' forked from session %s -> %s", name, current_sid, new_sid)
        return (
            f"Forked branch '{name}' (session: {new_sid[:8]}…).\nUse /switch {name} to activate it."
        )

    def switch(self, name: str, controller: Any) -> str:
        """Save current trace, load the named branch's trace, return its session_id."""
        branch = self._get_branch(name)
        if branch is None:
            return f"Branch '{name}' not found. Use /branches to list them."

        current_sid = self._resolve_session_id(controller)
        current_trace = self._get_trace(controller, current_sid)

        branch_sid = branch["session_id"]

        # Save current trace to current session (it should already be there)
        if current_trace:
            self._replace_trace(controller, current_sid, current_trace)

        # Load branch trace into working memory
        branch_trace = self._get_trace_by_session(controller, branch_sid)
        if branch_trace:
            self._replace_trace(controller, branch_sid, branch_trace)

        # Update the controller's default session_id to the branch
        self._set_session_id(controller, branch_sid)

        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "UPDATE branches SET updated_at = ? WHERE name = ?",
                (time.time(), name),
            )
            conn.commit()

        n_msgs = len(branch_trace) if branch_trace else 0
        viki_logger.info("Switched to branch '%s' (%d messages)", name, n_msgs)
        return f"Switched to branch '{name}' ({n_msgs} messages)."

    def list_branches(self) -> list[dict[str, Any]]:
        """Return all branches with metadata."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "SELECT name, session_id, parent_session_id, description, created_at, updated_at "
                "FROM branches ORDER BY updated_at DESC"
            )
            rows = cur.fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            result.append(
                {
                    "name": r["name"],
                    "session_id": r["session_id"],
                    "parent_session_id": r["parent_session_id"],
                    "description": r["description"] or "",
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
            )
        return result

    def format_branch_list(self, current_session_id: str | None = None) -> str:
        """Human-readable branch listing with active marker."""
        branches = self.list_branches()
        if not branches:
            return "No conversation branches. Use /fork <name> to create one."

        lines: list[str] = [
            f"{'Active':<8} {'Name':<20} {'Messages':<10} {'Description'}",
            "─" * 70,
        ]
        for b in branches:
            active = "←" if b["session_id"] == current_session_id else ""
            desc = (b["description"] or "")[:40]
            lines.append(f"{active:<8} {b['name']:<20} {b['session_id'][:8]:<10} {desc}")
        return "\n".join(lines)

    def diff(self, name: str, controller: Any, max_lines: int = 40) -> str:
        """Show the diff between current conversation and the named branch.

        Compares assistant responses turn-by-turn.
        """
        branch = self._get_branch(name)
        if branch is None:
            return f"Branch '{name}' not found."

        current_sid = self._resolve_session_id(controller)
        current_trace = self._get_trace(controller, current_sid)
        branch_trace = self._get_trace_by_session(controller, branch["session_id"])

        current_text = "\n".join(f"{m['role']}: {m['content']}" for m in (current_trace or []))
        branch_text = "\n".join(f"{m['role']}: {m['content']}" for m in (branch_trace or []))

        diff = difflib.unified_diff(
            branch_text.splitlines(),
            current_text.splitlines(),
            fromfile=f"branch/{name}",
            tofile="current",
            lineterm="",
        )
        lines = list(diff)
        if not lines:
            return f"Branch '{name}' is identical to current conversation."
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} more lines)"]
        return "\n".join(lines)

    def delete(self, name: str) -> str:
        """Remove a branch record."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute("DELETE FROM branches WHERE name = ?", (name,))
            conn.commit()
        if cur.rowcount:
            return f"Deleted branch '{name}'."
        return f"Branch '{name}' not found."

    def rename(self, old_name: str, new_name: str) -> str:
        """Rename a branch."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE branches SET name = ?, updated_at = ? WHERE name = ?",
                    (new_name, time.time(), old_name),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return f"Branch '{new_name}' already exists."
        if conn.total_changes:
            return f"Renamed '{old_name}' -> '{new_name}'."
        return f"Branch '{old_name}' not found."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_branch(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "SELECT name, session_id, parent_session_id, description, created_at, updated_at "
                "FROM branches WHERE name = ?",
                (name,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "name": row["name"],
            "session_id": row["session_id"],
            "parent_session_id": row["parent_session_id"],
            "description": row["description"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _resolve_session_id(controller: Any, session_id: str | None = None) -> str:
        """Get the current effective session_id from the controller."""
        if session_id:
            return session_id
        try:
            return cast(str, controller._normalize_session_id())
        except Exception:
            return "default"

    @staticmethod
    def _get_trace(controller: Any, session_id: str) -> list[dict[str, str]]:
        """Fetch the working memory trace for a session."""
        try:
            return cast(
                "list[dict[str, str]]", controller.memory.working.get_trace(session_id=session_id)
            )
        except Exception as exc:
            viki_logger.debug("BranchManager._get_trace: %s", exc)
            return []

    @staticmethod
    def _get_trace_by_session(controller: Any, session_id: str) -> list[dict[str, str]]:
        """Same as _get_trace but can handle arbitrary session_ids."""
        return BranchManager._get_trace(controller, session_id)

    @staticmethod
    def _replace_trace(controller: Any, session_id: str, trace: list[dict[str, str]]) -> None:
        """Replace the working memory trace for a session."""
        try:
            controller.memory.working.replace_trace(trace, session_id=session_id)
        except Exception as exc:
            viki_logger.debug("BranchManager._replace_trace: %s", exc)

    @staticmethod
    def _set_session_id(controller: Any, session_id: str) -> None:
        """Update the controller's default session_id to point to a branch."""
        try:
            controller.memory.working.default_session_id = session_id
        except Exception as exc:
            viki_logger.debug("BranchManager._set_session_id: %s", exc)
