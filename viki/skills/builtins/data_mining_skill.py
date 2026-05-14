import os
import asyncio
import json
import re
from typing import Dict, Any, List, Optional
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class DataMiningSkill(BaseSkill):
    """
    Skill for web data extraction, pattern discovery, and entity mining.
    """
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller

    @property
    def name(self) -> str:
        return "data_mining"

    @property
    def description(self) -> str:
        return (
            "Extract patterns and structured info from raw data or the web.\n"
            "Actions:\n"
            "- scrape_topic(topic, limit): Find and extract structured data about a topic from the web.\n"
            "- discover_patterns(data_path): Identify correlations and anomalies in a dataset.\n"
            "- extract_entities(text, entity_types): Extract names, prices, dates, etc., from raw text."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["scrape_topic", "discover_patterns", "extract_entities"],
                    "description": "Mining action to perform"
                },
                "topic": {"type": "string", "description": "Topic to scrape and mine"},
                "limit": {"type": "integer", "default": 5, "description": "Max results to process"},
                "data_path": {"type": "string", "description": "Path to data file (CSV/JSON)"},
                "text": {"type": "string", "description": "Raw text for entity extraction"},
                "entity_types": {"type": "array", "items": {"type": "string"}, "description": "Types of entities to mine (e.g., 'price', 'product')"}
            },
            "required": ["action"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        
        try:
            if action == "scrape_topic":
                topic = params.get("topic")
                limit = params.get("limit", 5)
                return await self._scrape_and_mine(topic, limit)

            elif action == "discover_patterns":
                path = params.get("data_path")
                return await self._discover_patterns(path)

            elif action == "extract_entities":
                text = params.get("text")
                types = params.get("entity_types", ["entities"])
                return await self._extract_entities(text, types)

            return f"Error: Unknown action '{action}'"
        except Exception as e:
            viki_logger.error(f"DataMining Error: {e}")
            return f"Mining failed: {str(e)}"

    async def _scrape_and_mine(self, topic: str, limit: int) -> str:
        """Combine Research and LLM to mine data from the web."""
        if not self._controller: return "Error: Controller required."
        
        research = self._controller.skill_registry.get_skill("research")
        if not research: return "Error: research skill not found."
        
        viki_logger.info(f"DataMining: Scaping web for '{topic}'...")
        raw_data = await research.execute({"query": f"site:*.csv OR site:*.json OR 'data' {topic}"})
        
        model = self._controller.model_router.get_model(["reasoning"])
        prompt = (
            f"I am mining data about: {topic}\n\n"
            f"Based on these search results, extract a structured JSON list of key data points (e.g., statistics, prices, trends).\n"
            f"Results:\n{raw_data[:4000]}\n\n"
            "Output ONLY the JSON array."
        )
        return await model.chat([{"role": "user", "content": prompt}])

    async def _discover_patterns(self, path: str) -> str:
        """Use Pandas to find basic correlations or LLM for deeper insights."""
        if not path or not os.path.exists(path): return f"Error: File {path} not found."
        
        try:
            import pandas as pd
            df = pd.read_csv(path) if path.endswith('.csv') else pd.read_json(path)
            
            # Basic correlation
            numeric = df.select_dtypes(include=['number'])
            if not numeric.empty and numeric.shape[1] >= 2:
                corr = numeric.corr().to_string()
                return f"DATA MINING PATTERNS for {os.path.basename(path)}:\n\nCORRELATION MATRIX:\n{corr}\n\nTOP CORRELATIONS:\n{self._get_top_corrs(numeric.corr())}"
            
            return f"No numeric data for correlation in {path}. Rows: {len(df)}"
        except ImportError:
            return "Error: pandas is required for pattern discovery."
        except Exception as e:
            return f"Pattern Discovery Error: {e}"

    def _get_top_corrs(self, corr_matrix) -> str:
        # Extract pairs with high absolute correlation (excluding 1.0)
        s = corr_matrix.unstack()
        so = s.sort_values(kind="quicksort", ascending=False)
        top = so[(abs(so) > 0.5) & (so < 1.0)]
        return top.to_string()

    async def _extract_entities(self, text: str, types: List[str]) -> str:
        if not self._controller: return "Error: Controller required."
        model = self._controller.model_router.get_model(["reasoning"])
        prompt = (
            f"Mine the following text for these entity types: {', '.join(types)}\n\n"
            f"Text: {text[:2000]}\n\n"
            "Return a structured list of findings."
        )
        return await model.chat([{"role": "user", "content": prompt}])
