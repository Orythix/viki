import os
import json
import uuid
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime
from viki.config.logger import viki_logger

try:
    from sqlite_utils import Database
except ImportError:
    Database = None

class Memory:
    """
    Persistent Memory System backed by SQLite.
    Stores conversation history, goals, and context.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.max_short_term = config.get('memory', {}).get('short_term_limit', 10)
        
        # Path setup
        data_dir = config.get('system', {}).get('data_dir', './data')
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "viki_memory.db")
        
        # Session ID
        self.session_id = str(uuid.uuid4())
        
        # Initialize DB
        self.db = None
        if Database:
            self.db = Database(self.db_path)
            self._init_tables()
        else:
            viki_logger.warning("sqlite-utils not installed. Memory will be ephemeral.")
            self.ephemeral_history = []
            self.ephemeral_goals = []

    def _init_tables(self):
        if not self.db: return
        
        # Messages Table
        if "messages" not in self.db.table_names():
            self.db["messages"].create({
                "id": str,
                "role": str,
                "content": str,
                "timestamp": str,
                "session_id": str,
                "metadata": str  # JSON
            }, pk="id")
            self.db["messages"].create_index(["timestamp", "session_id"])

        # Goals Table
        if "goals" not in self.db.table_names():
            self.db["goals"].create({
                "id": str,
                "description": str,
                "status": str,
                "result": str,
                "reason": str,
                "timestamp": str,
                "steps": str # JSON
            }, pk="id")

    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """Add message to memory."""
        msg_id = str(uuid.uuid4())
        ts = datetime.now().isoformat()
        meta_json = json.dumps(metadata or {})
        
        if self.db:
            try:
                self.db["messages"].insert({
                    "id": msg_id,
                    "role": role,
                    "content": content,
                    "timestamp": ts,
                    "session_id": self.session_id,
                    "metadata": meta_json
                })
            except Exception as e:
                viki_logger.error(f"Failed to save message to DB: {e}")
        else:
            self.ephemeral_history.append({
                "role": role, 
                "content": content, 
                "timestamp": ts
            })

    def get_context(self, limit: int = None) -> List[Dict[str, str]]:
        """Retrieve recent context (Short Term Memory)."""
        limit = limit or self.max_short_term
        
        if self.db:
            try:
                # Get last N messages
                rows = list(self.db["messages"].rows_where(
                    order_by="timestamp DESC", 
                    limit=limit
                ))
                # Reverse to chronological order
                return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
            except Exception as e:
                viki_logger.error(f"Failed to load context from DB: {e}")
                return []
        else:
            return self.ephemeral_history[-limit:]

    def add_goal(self, description: str) -> str:
        goal_id = str(uuid.uuid4())[:8]
        ts = datetime.now().isoformat()
        
        record = {
            "id": goal_id,
            "description": description,
            "status": "IN_PROGRESS",
            "timestamp": ts,
            "steps": "[]",
            "result": "",
            "reason": ""
        }
        
        if self.db:
            self.db["goals"].insert(record)
        else:
            self.ephemeral_goals.append(record)
            
        return goal_id

    def complete_goal(self, goal_id: str, result: str):
        if self.db:
            self.db["goals"].update(goal_id, {"status": "COMPLETED", "result": result})
        else:
            for g in self.ephemeral_goals:
                if g['id'] == goal_id:
                     g['status'] = "COMPLETED"
                     g['result'] = result

    def get_recent_goals(self, limit: int = 5) -> List[Dict[str, Any]]:
        if self.db:
            return list(self.db["goals"].rows_where(
                order_by="timestamp DESC", 
                limit=limit
            ))
        else:
            return self.ephemeral_goals[-limit:]

    def search_history(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """FTF search if enabled, else simple LIKE."""
        if not self.db: return []
        
        try:
            # Simple LIKE search for now
            return list(self.db["messages"].rows_where(
                "content LIKE ?", 
                [f"%{query}%"], 
                order_by="timestamp DESC", 
                limit=limit
            ))
        except:
            return []
