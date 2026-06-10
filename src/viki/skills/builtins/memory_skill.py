from typing import Dict, Any, List, Optional
import json
import os
from skills.base import BaseSkill
from config.logger import viki_logger

class MemorySkill(BaseSkill):
    """
    Sovereign Memory Management Skill.
    Advanced interface for managing VIKI's multi-layered memory stack.
    Exceeds agentmemory capabilities with hierarchical consolidation and continuous learning integration.
    """
    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Advanced memory management. Actions: save, search, list, delete, update, stats, wipe, consolidate, sessions."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["save", "search", "list", "delete", "update", "stats", "wipe", "consolidate", "sessions"],
                    "description": "The memory action to perform"
                },
                "text": {"type": "string", "description": "Memory content (for save/update)"},
                "query": {"type": "string", "description": "Search query"},
                "id": {"type": "string", "description": "Memory ID (for delete/update)"},
                "category": {"type": "string", "description": "Category or source (e.g., 'coding', 'user_pref')"},
                "limit": {"type": "integer", "default": 5},
                "reliability": {"type": "number", "description": "Confidence level (0.0 to 1.0)"}
            },
            "required": ["action"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        
        try:
            if action == "save":
                return await self._handle_save(params)
            elif action == "search":
                return await self._handle_search(params)
            elif action == "list":
                return await self._handle_list(params)
            elif action == "delete":
                return await self._handle_delete(params)
            elif action == "update":
                return await self._handle_update(params)
            elif action == "stats":
                return await self._handle_stats()
            elif action == "wipe":
                return await self._handle_wipe(params)
            elif action == "consolidate":
                return await self._handle_consolidate()
            elif action == "sessions":
                return await self._handle_sessions()
            
            return f"Error: Unknown action '{action}'"
        except Exception as e:
            viki_logger.error(f"MemorySkill Error: {e}")
            return f"Memory Operation Failed: {str(e)}"

    async def _handle_save(self, params: Dict[str, Any]) -> str:
        text = params.get("text")
        if not text: return "Error: 'text' is required for save action."
        
        category = params.get("category", "manual_entry")
        reliability = params.get("reliability", 1.0)
        
        self.controller.learning.save_lesson(
            fact=text,
            source_task=category,
            reliability=reliability
        )
        return f"SUCCESS: Memory saved to Semantic Layer. (Source: {category})"

    async def _handle_search(self, params: Dict[str, Any]) -> str:
        query = params.get("query")
        if not query: return "Error: 'query' is required for search action."
        limit = params.get("limit", 5)
        
        viki_logger.info(f"Memory Skill: Hybrid search for '{query}'")
        try:
            from core.memory.hybrid_search import search_memory
            results = await search_memory(self.controller, query, limit=limit)
        except Exception:
            results = self.controller.learning.get_relevant_lessons(query, limit=limit)
            
        if not results:
            return f"No memories found matching '{query}'."
            
        formatted = "\n".join([f"- {r}" for r in results])
        return f"SEARCH RESULTS:\n{formatted}"

    async def _handle_list(self, params: Dict[str, Any]) -> str:
        category = params.get("category")
        query = params.get("query")
        limit = params.get("limit", 10)
        
        lessons = self.controller.learning.get_lessons(query=query, source=category, limit=limit)
        if not lessons:
            return "No memories found in the specified collection."
            
        lines = []
        for l in lessons:
            lines.append(f"[{l['id']}] ({l['source_task']}) {l['text_representation']}")
            
        return "COLLECTION LIST:\n" + "\n".join(lines)

    async def _handle_delete(self, params: Dict[str, Any]) -> str:
        mem_id = params.get("id")
        if not mem_id: return "Error: 'id' is required for delete action."
        
        success = self.controller.learning.delete_lesson(mem_id)
        if success:
            return f"SUCCESS: Memory '{mem_id}' has been deleted."
        return f"FAILED: Memory '{mem_id}' not found."

    async def _handle_update(self, params: Dict[str, Any]) -> str:
        mem_id = params.get("id")
        text = params.get("text")
        reliability = params.get("reliability")
        
        if not mem_id: return "Error: 'id' is required for update action."
        
        success = self.controller.learning.update_lesson(mem_id, fact=text, reliability=reliability)
        if success:
            return f"SUCCESS: Memory '{mem_id}' updated."
        return f"FAILED: Memory '{mem_id}' not found or no changes provided."

    async def _handle_stats(self) -> str:
        learning = self.controller.learning
        memory = self.controller.memory
        
        total_lessons = learning.get_total_lesson_count()
        stable_lessons = learning.get_stable_lesson_count()
        
        # Episodic stats – use get_connection to avoid stale .conn references
        from core.memory.database import get_connection
        conn = get_connection(memory.episodic.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM episodes")
        episodes = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM semantic_knowledge")
        wisdom = cur.fetchone()[0]
        
        # Working stats
        sessions = len(memory.working.get_all_sessions())
        
        stats = [
            f"--- VIKI Sovereign Memory Stats ---",
            f"Semantic Lessons: {total_lessons} (Reinforced: {stable_lessons})",
            f"Episodic Moments: {episodes}",
            f"Narrative Wisdom: {wisdom}",
            f"Active Sessions:  {sessions}",
            f"Memory Backend:   {getattr(learning._vector_backend, 'backend_name', 'None')}"
        ]
        return "\n".join(stats)

    async def _handle_wipe(self, params: Dict[str, Any]) -> str:
        category = params.get("category")
        if not category:
            return "CAUTION: Please specify a 'category' to wipe, or 'ALL' for a full reset (Requires manual confirmation)."
        
        if category == "ALL":
             return "WIPE REJECTED: Full system wipe must be performed via SuperAdmin console."
             
        # Implementation of partial wipe
        cur = self.controller.learning.conn.cursor()
        cur.execute("DELETE FROM lessons WHERE source_task = ?", (category,))
        count = cur.rowcount
        self.controller.learning.conn.commit()
        self.controller.learning.mark_vector_dirty()
        
        return f"SUCCESS: Wiped {count} memories from collection '{category}'."

    async def _handle_consolidate(self) -> str:
        viki_logger.info("Memory Skill: Manually triggering Dream Cycle...")
        # Narrative consolidation
        await self.controller.memory.episodic.consolidate(self.controller.model_router)
        return "SUCCESS: Dream Cycle complete. Episodes have been consolidated into Semantic Knowledge."

    async def _handle_sessions(self) -> str:
        sessions = self.controller.memory.working.get_all_sessions()
        if not sessions:
            return "No active working memory sessions found."
            
        lines = ["ACTIVE SESSIONS:"]
        for s in sessions:
            lines.append(f"- ID: {s['session_id'][:8]}... | Messages: {s['message_count']} | Last Active: {s['last_active']}")
            
        return "\n".join(lines)
