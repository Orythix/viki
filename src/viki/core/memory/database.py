import os
import sqlite3
import threading
from typing import Dict, Optional

_connections: Dict[str, sqlite3.Connection] = {}
_refcount: Dict[str, int] = {}
_lock = threading.Lock()

MERGED_DB_NAME = "viki_memory.db"


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get or create a shared persistent SQLite connection.

    Reuses connections for the same real path so that multiple subsystems
    writing to the same file share a single connection (and thus a single WAL).
    Callers should call :func:`release_connection` on shutdown.
    """
    real_path = os.path.realpath(db_path)
    with _lock:
        conn = _connections.get(real_path)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
            except (sqlite3.ProgrammingError, sqlite3.OperationalError):
                conn = None
                _connections.pop(real_path, None)
                _refcount.pop(real_path, None)
        if conn is None:
            conn = sqlite3.connect(real_path, check_same_thread=False, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            _connections[real_path] = conn
            _refcount[real_path] = 1
        else:
            _refcount[real_path] = _refcount.get(real_path, 0) + 1
        return conn


def release_connection(db_path: str) -> None:
    """Release a reference obtained via :func:`get_connection`.

    When the last reference is released the underlying connection is closed.
    """
    real_path = os.path.realpath(db_path)
    with _lock:
        current = _refcount.get(real_path, 0)
        if current <= 1:
            _refcount.pop(real_path, None)
            conn = _connections.pop(real_path, None)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            _refcount[real_path] = current - 1


def close_all():
    """Close every managed connection regardless of remaining references.

    Safe to call more than once.  Clears both the connection dictionary
    and the reference counter.
    """
    with _lock:
        for path, conn in list(_connections.items()):
            try:
                conn.close()
            except Exception:
                pass
        _connections.clear()
        _refcount.clear()


def migrate_to_merged(data_dir: str, merged_path: str) -> bool:
    """One-shot migration from legacy individual DB files into *viki_memory.db*.

    Returns True if any data was copied.
    """
    legacy_files = {
        "viki_working_memory.db": False,
        "orythix_narrative.db": False,
        "orythix_identity.db": False,
    }

    # Quick check: nothing to do if none of the legacy files exist.
    legacy_paths = {name: os.path.join(data_dir, name) for name in legacy_files}
    if not any(os.path.isfile(p) for p in legacy_paths.values()):
        return False

    merged = get_connection(merged_path)
    migrated = False

    # Working Memory → messages
    src = legacy_paths["viki_working_memory.db"]
    if os.path.isfile(src):
        try:
            src_conn = sqlite3.connect(src, timeout=10.0)
            src_conn.row_factory = sqlite3.Row
            try:
                cur = src_conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
                if cur.fetchone() and merged.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
                ).fetchone():
                    rows = src_conn.execute("SELECT * FROM messages").fetchall()
                    for row in rows:
                        merged.execute(
                            "INSERT OR IGNORE INTO messages "
                            "(id, role, content, timestamp, session_id, metadata) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (row["id"], row["role"], row["content"],
                             row["timestamp"], row["session_id"], row["metadata"]),
                        )
                    merged.commit()
                    migrated = True
            finally:
                src_conn.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Migration from %s failed: %s", src, e)

    # Narrative Memory → episodes, semantic_knowledge, meta_reflections
    src = legacy_paths["orythix_narrative.db"]
    if os.path.isfile(src):
        try:
            src_conn = sqlite3.connect(src, timeout=10.0)
            src_conn.row_factory = sqlite3.Row
            try:
                cur = src_conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {r[0] for r in cur.fetchall()}
                for table in ("episodes", "semantic_knowledge", "meta_reflections"):
                    if table in tables and merged.execute(
                        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
                    ).fetchone():
                        src_cols = [d[1] for d in src_conn.execute(f"PRAGMA table_info({table})").fetchall()]
                        placeholders = ", ".join("?" for _ in src_cols)
                        col_names = ", ".join(src_cols)
                        rows = src_conn.execute(f"SELECT * FROM {table}").fetchall()
                        for row in rows:
                            merged.execute(
                                f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",
                                [row[c] for c in src_cols],
                            )
                        merged.commit()
                        migrated = True
            finally:
                src_conn.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Migration from %s failed: %s", src, e)

    # Identity → identity_anchors
    src = legacy_paths["orythix_identity.db"]
    if os.path.isfile(src):
        try:
            src_conn = sqlite3.connect(src, timeout=10.0)
            src_conn.row_factory = sqlite3.Row
            try:
                cur = src_conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='identity_anchors'")
                if cur.fetchone() and merged.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='identity_anchors'"
                ).fetchone():
                    rows = src_conn.execute("SELECT * FROM identity_anchors").fetchall()
                    for row in rows:
                        merged.execute(
                            "INSERT OR IGNORE INTO identity_anchors "
                            "(key, value, category, last_updated, significance) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (row["key"], row["value"], row["category"],
                             row["last_updated"], row["significance"]),
                        )
                    merged.commit()
                    migrated = True
            finally:
                src_conn.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Migration from %s failed: %s", src, e)

    return migrated
