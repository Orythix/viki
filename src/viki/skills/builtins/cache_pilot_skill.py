import json
from typing import Dict, Any, Optional
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class CachePilotSkill(BaseSkill):
    """
    Skill for managing the Semantic Cache.
    Allows inspection, pruning, and manual injection of cache entries.
    """
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        self._cache = None
        
    def _get_cache(self):
        """Lazy load or retrieve cache from controller."""
        if self._cache:
            return self._cache
            
        if self._controller and hasattr(self._controller, "router") and hasattr(self._controller.router, "cache"):
            self._cache = self._controller.router.cache
            return self._cache
            
        # Fallback: create a new instance if controller doesn't have one (unlikely in production)
        from core.utils.semantic_cache import SemanticCache
        data_dir = "./data"
        if self._controller and hasattr(self._controller, "settings"):
            data_dir = self._controller.settings.get("system", {}).get("data_dir", "./data")
        
        self._cache = SemanticCache(data_dir)
        return self._cache

    @property
    def name(self) -> str:
        return "cache_pilot"

    @property
    def description(self) -> str:
        return "Manages the Semantic Cache. Actions: stats, list, prune, warm."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["stats", "list", "prune", "warm"],
                    "description": "Cache management action"
                },
                "query": {
                    "type": "string",
                    "description": "Query text for search, prune, or warm"
                },
                "response": {
                    "type": "string",
                    "description": "Response text for warm action"
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Limit for list action"
                }
            },
            "required": ["action"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        cache = self._get_cache()
        
        if not cache:
            return "Error: Semantic Cache not available."

        try:
            if action == "stats":
                stats = cache.get_stats()
                if "error" in stats:
                    return f"Error retrieving stats: {stats['error']}"
                
                output = [
                    f"--- Cache Statistics ---",
                    f"Total Entries: {stats['entry_count']}",
                    f"Total Hits:    {stats['total_hits']}",
                    f"DB Size:      {stats['db_size_kb']} KB",
                    f"\nTop Queries:"
                ]
                for q in stats['top_queries']:
                    output.append(f" - [{q['hits']} hits] {q['query'][:60]}...")
                return "\n".join(output)

            elif action == "list":
                limit = params.get("limit", 10)
                entries = cache.list_entries(limit=limit)
                if not entries:
                    return "Cache is empty."
                
                output = [f"--- Recent Cache Entries (Last {limit}) ---"]
                for e in entries:
                    output.append(f" - [{e['hit_count']} hits] {e['query_text'][:70]}...")
                return "\n".join(output)

            elif action == "prune":
                query = params.get("query")
                if query:
                    success = cache.clear(query=query)
                    return f"Entry for '{query}' removed from cache." if success else "Failed to remove entry."
                else:
                    success = cache.clear()
                    return "Entire semantic cache wiped successfully." if success else "Failed to wipe cache."

            elif action == "warm":
                query = params.get("query")
                response_text = params.get("response")
                if not query or not response_text:
                    return "Error: Both 'query' and 'response' are required for warm action."
                
                # We store a minimal VIKIResponse structure
                response_obj = {"final_response": response_text}
                cache.store(query, response_obj)
                return f"Successfully warmed cache for query: '{query}'"

            return f"Error: Unknown action '{action}'"

        except Exception as e:
            viki_logger.error(f"CachePilot Execution Error: {e}")
            return f"CachePilot Error: {str(e)}"
