import os
import json
import uuid
import sqlite3
import threading
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
    Holds current deliberation trace; length capped by memory.short_term_limit (10–50).
    
    SECURITY FIX: MED-001 - Added thread safety with proper locking.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # Clamp short-term trace length (config memory.short_term_limit); wider window = richer multi-turn context.
        self.max_turns = min(max(config.get('memory', {}).get('short_term_limit', 15), 10), 50)
        
        data_dir = config.get('system', {}).get('data_dir', './data')
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "viki_working_memory.db")
        
        self.default_session_id = str(uuid.uuid4())
        self.db = None
        
        # --- SECURITY FIX: MED-001 - Thread safety lock ---
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        
        if Database:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            self.db = Database(conn)
            self._init_tables()
        else:
            self.ephemeral_history = {}

    def _normalize_session_id(self, session_id: Optional[str] = None) -> str:
        return session_id or self.default_session_id

    def _init_tables(self):
        if not self.db: return
        with self._lock:
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

    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None, session_id: Optional[str] = None):
        with self._lock:
            session_id = self._normalize_session_id(session_id)
            msg_id = str(uuid.uuid4())
            ts = datetime.now().isoformat()
            if self.db:
                self.db["messages"].insert({
                    "id": msg_id, "role": role, "content": content,
                    "timestamp": ts, "session_id": session_id,
                    "metadata": json.dumps(metadata or {})
                })
                # Enforce turn limit (Working Memory behavior)
                self._prune_history(session_id=session_id)
            else:
                history = self.ephemeral_history.setdefault(session_id, [])
                history.append({"role": role, "content": content})
                if len(history) > self.max_turns:
                    history.pop(0)

    def _prune_history(self, session_id: Optional[str] = None):
        """Keep only the last max_turns messages in the database."""
        if not self.db: return
        with self._lock:
            session_id = self._normalize_session_id(session_id)
            try:
                # Simple pruning: delete everything but the top N
                rows = list(self.db["messages"].rows_where(
                    "session_id = ?",
                    [session_id],
                    order_by="timestamp DESC",
                    limit=self.max_turns
                ))
                if not rows: return
                oldest_ts = rows[-1]["timestamp"]
                self.db["messages"].delete_where(
                    "session_id = ? AND timestamp < ?",
                    [session_id, oldest_ts]
                )
            except Exception as e:
                viki_logger.error(f"WorkingMemory Pruning Failed: {e}")

    def get_trace(self, session_id: Optional[str] = None) -> List[Dict[str, str]]:
        with self._lock:
            session_id = self._normalize_session_id(session_id)
            if self.db:
                rows = list(self.db["messages"].rows_where(
                    "session_id = ?",
                    [session_id],
                    order_by="timestamp ASC",
                    limit=self.max_turns
                ))
                return [{"role": r["role"], "content": r["content"]} for r in rows]
            return list(self.ephemeral_history.get(session_id, []))

    def replace_trace(self, messages: List[Dict[str, str]], session_id: Optional[str] = None) -> None:
        """Replace current conversation with a saved session (for /load)."""
        with self._lock:
            session_id = self._normalize_session_id(session_id)
            if self.db:
                self.db["messages"].delete_where("session_id = ?", [session_id])
                for m in messages[-self.max_turns:]:
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    self.db["messages"].insert({
                        "id": str(uuid.uuid4()), "role": role, "content": content,
                        "timestamp": datetime.now().isoformat(), "session_id": session_id,
                        "metadata": "{}"
                    })
            else:
                self.ephemeral_history[session_id] = [
                    {"role": m.get("role", "user"), "content": m.get("content", "")}
                    for m in messages[-self.max_turns:]
                ]

    def clear_trace(self, session_id: Optional[str] = None) -> None:
        with self._lock:
            session_id = self._normalize_session_id(session_id)
            if self.db:
                self.db["messages"].delete_where("session_id = ?", [session_id])
            else:
                self.ephemeral_history.pop(session_id, None)

    def get_last_thought(self, session_id: Optional[str] = None) -> str:
        """Get the last assistant message for context."""
        with self._lock:
            trace = self.get_trace(session_id=session_id)
            for msg in reversed(trace):
                if msg.get("role") == "assistant":
                    return msg.get("content", "")
            return ""

    def close(self):
        with self._lock:
            if self.db:
                try:
                    self.db.conn.close()
                except Exception:
                    pass

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

    def get_context(self, current_input: str = "", limit: int = 20, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Legacy alias: returns working trace and episodic context. Prefer get_full_context for full stack."""
        return {
            "working": self.working.get_trace(session_id=session_id),
            "episodic": self.episodic.retrieve_context(current_input, limit=min(limit, 5)),
        }

    def get_full_context(self, current_input: str, narrative_wisdom: List[Dict] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Synthesizes context across all layers for the Deliberation layer."""
        # Cheap-retrieve fast path: trivial smalltalk doesn't need semantic
        # search. Skip the narrative-wisdom fetch and the embedding-based
        # semantic_knowledge query entirely. Saves ~2 sentence-transformer
        # encodes per "hello viki"-class turn.
        from viki.core.utils.trivial_input import is_trivial_input
        cheap = is_trivial_input(current_input)

        # v25: Accept pre-fetched narrative wisdom to avoid duplicate queries
        if narrative_wisdom is None and not cheap:
            narrative_wisdom = self.episodic.get_semantic_knowledge(limit=3)
        if not isinstance(narrative_wisdom, list):
            narrative_wisdom = []
        wisdom_block = "\n".join([
            f"- [{(w.get('category') or 'general').upper()}]: {w.get('insight', '')}"
            for w in narrative_wisdom
        ])

        # Cortex expects specific key names for prompt construction. Keep backwards-compatible
        # aliases (`semantic`, `episodic`, `identity`) but also provide `semantic_knowledge`,
        # `episodic_context`, and `narrative_identity` for the main prompt builder.
        if cheap:
            try:
                episodic_context = self.episodic.retrieve_context(current_input, limit=3, cheap=True)
            except TypeError:
                # Older signature without `cheap` kwarg.
                episodic_context = self.episodic.retrieve_context(current_input, limit=3)
            semantic_knowledge = []
        else:
            episodic_context = self.episodic.retrieve_context(current_input)
            semantic_knowledge = self.semantic.get_relevant_lessons(current_input) if self.semantic else []
        narrative_identity = self.identity.get_identity_prompt()

        return {
            "working": self.working.get_trace(session_id=session_id),
            # Backwards-compatible aliases
            "episodic": episodic_context,
            "semantic": semantic_knowledge,
            "identity": narrative_identity,
            # Keys consumed by `viki/core/cortex.py`
            "episodic_context": episodic_context,
            "semantic_knowledge": semantic_knowledge,
            "narrative_identity": narrative_identity,
            "narrative_wisdom": wisdom_block,
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

    def close(self):
        if hasattr(self, 'working'): self.working.close()
        if hasattr(self, 'episodic'): self.episodic.close()
        if hasattr(self, 'identity') and hasattr(self.identity, 'close'):
            self.identity.close()
        viki_logger.info('HierarchicalMemory: Stack shut down.')
