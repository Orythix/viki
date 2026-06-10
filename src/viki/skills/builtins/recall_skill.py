from typing import Dict, Any, List
import re
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class RecallSkill(BaseSkill):
    """
    Skill for targeted semantic memory recall.
    Allows VIKI to explicitly search her long-term "lessons" database.
    """
    def __init__(self, controller):
        self.controller = controller
        self._name = "recall"
        self._description = "Perform a targeted search of your own long-term memory for specific facts. Usage: recall(query='What did Orythix001 say about Python?')"

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    async def execute(self, params: Dict[str, Any]) -> str:
        query = params.get("query")
        if not query:
            return "Error: No query provided."
        limit = int(params.get("limit", 10))
        viki_logger.info(f"Recall: Hybrid search for '{query}'")
        try:
            from core.memory.hybrid_search import search_memory
            results = await search_memory(self.controller, query, limit=limit, rerank=False)
        except Exception as e:
            viki_logger.debug(f"Hybrid search fallback: {e}")
            results = self.controller.learning.get_relevant_lessons(query, limit=limit)
        if not results:
            return f"No specific memories found for '{query}'."

        def _format_recalled(r: str) -> str:
            # Prefer displaying SOURCE-labeled citations clearly when present.
            if "SOURCE:" in r:
                # Expected pattern: "...SOURCE: <url> | <fact>"
                m = re.search(r"SOURCE:\s*(\S+)\s*\|\s*(.*)$", r)
                if m:
                    url = m.group(1)
                    fact = m.group(2).strip()
                    return f"- {fact} (source: {url})"
            return f"- {r}"

        formatted = "\n".join(_format_recalled(r) for r in results)
        return f"RECALLED MEMORIES:\n{formatted}"
