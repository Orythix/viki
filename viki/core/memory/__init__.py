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

from .narrative import NarrativeMemory, NarrativeMemory as EpisodicMemory
from .identity import NarrativeIdentity

class WorkingMemory:
    """
    Working Memory (Short-term scratchpad).
    Holds current deliberation trace, lasts ~10–20 turns.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # Limit to 10-20 turns as requested
        self.max_turns = min(max(config.get('memory', {}).get('short_term_limit', 15), 10), 20)
        
        data_dir = config.get('system', {}).get('data_dir', './data')
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "viki_working_memory.db")
        
        self.session_id = str(uuid.uuid4())
        self.db = None
        if Database:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.db = Database(conn)
            self._init_tables()
        else:
            self.ephemeral_history = []

    def _init_tables(self):
        if not self.db: return
        if "messages" not in self.db.table_names():
            self.db["messages"].create({
                "id": str,
                "role": str,
                "content": str,
                "timestamp": str,
                "session_id": str,
                "metadata": str
            }, pk="id")
            self.db["messages"].create_index(["timestamp"])

    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        msg_id = str(uuid.uuid4())
        ts = datetime.now().isoformat()
        if self.db:
            self.db["messages"].insert({
                "id": msg_id, "role": role, "content": content,
                "timestamp": ts, "session_id": self.session_id,
                "metadata": json.dumps(metadata or {})
            })
            # Enforce turn limit (Working Memory behavior)
            self._prune_history()
        else:
            self.ephemeral_history.append({"role": role, "content": content})
            if len(self.ephemeral_history) > self.max_turns:
                self.ephemeral_history.pop(0)

    def _prune_history(self):
        """Keep only the last max_turns messages in the database."""
        if not self.db: return
        try:
            # Simple pruning: delete everything but the top N
            rows = list(self.db["messages"].rows_where(order_by="timestamp DESC", limit=self.max_turns))
            if not rows: return
            oldest_ts = rows[-1]["timestamp"]
            self.db["messages"].delete_where("timestamp < ?", [oldest_ts])
        except Exception as e:
            viki_logger.error(f"WorkingMemory Pruning Failed: {e}")

    def get_trace(self) -> List[Dict[str, str]]:
        if self.db:
            rows = list(self.db["messages"].rows_where(order_by="timestamp ASC", limit=self.max_turns))
            return [{"role": r["role"], "content": r["content"]} for r in rows]
        return self.ephemeral_history

class HierarchicalMemory:
    """
    v23: Orchestrator for the Hierarchical Memory Stack.
    Integrates Working, Episodic, Semantic, and Identity layers.
    """
    def __init__(self, config: Dict[str, Any], learning_module=None):
        self.working = WorkingMemory(config)
        
        data_dir = config.get('system', {}).get('data_dir', './data')
        self.episodic = EpisodicMemory(data_dir)
        self.identity = NarrativeIdentity(data_dir)
        self.semantic = learning_module # Shared with LearningModule

    def get_full_context(self, current_input: str) -> Dict[str, Any]:
        """Synthesizes context across all layers for the Deliberation layer."""
        # v25: Pull high-level semantic insights from narrative Dream Cycles
        narrative_wisdom = self.episodic.get_semantic_knowledge(limit=3)
        wisdom_block = "\n".join([f"- [{w['category'].upper()}]: {w['insight']}" for w in narrative_wisdom])

        return {
            "working": self.working.get_trace(),
            "episodic": self.episodic.retrieve_context(current_input),
            "semantic": self.semantic.get_relevant_lessons(current_input) if self.semantic else [],
            "narrative_wisdom": wisdom_block,
            "identity": self.identity.get_identity_prompt()
        }

    def record_interaction(self, intent: str, action: str, outcome: str, confidence: float):
        """Disperses information to episodic and semantic layers."""
        # 1. Episodic Record
        self.episodic.add_episode(
            context="interaction", 
            intent=intent, 
            plan={}, 
            action=action, 
            outcome=outcome, 
            confidence=confidence
        )
        
        # 2. Semantic Abstraction candidate (if high confidence)
        if confidence > 0.8 and self.semantic:
            self.semantic.save_lesson(
                lesson=f"On '{intent}', successfully used '{action}' to achieve '{outcome[:50]}'.",
                source_task="Empirical Learning"
            )
        
        # 3. v25: Check for Dream Cycle trigger (Every 20 episodes)
        # This is handled by a separate background trigger or in-thread periodically
