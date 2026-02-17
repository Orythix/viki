"""
GIF search (gifgrep-style). GIPHY API: set VIKI_GIPHY_API_KEY.
"""
import os
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger


class GifSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "gif"

    @property
    def description(self) -> str:
        return "Search and get GIF URL. Params: query= search term. Set VIKI_GIPHY_API_KEY."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        query = params.get("query")
        if not query:
            return "Provide query= for GIF search."
        key = os.environ.get("VIKI_GIPHY_API_KEY")
        if not key:
            return "Set VIKI_GIPHY_API_KEY for GIPHY search."
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.giphy.com/v1/gifs/search",
                    params={"api_key": key, "q": query, "limit": min(int(params.get("limit", 5)), 10)},
                ) as resp:
                    if resp.status != 200:
                        return f"GIPHY error: {resp.status}"
                    data = await resp.json()
                    gifs = data.get("data", [])
                    urls = [g.get("images", {}).get("original", {}).get("url") or g.get("url", "") for g in gifs]
                    return "GIFs:\n" + "\n".join(urls) if urls else "No results."
        except Exception as e:
            return f"GIF search error: {e}"