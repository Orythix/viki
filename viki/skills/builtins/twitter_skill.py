"""
Twitter/X skill (Molty bird-style): read timeline, search, post tweet.
Requires Twitter API v2 credentials: VIKI_TWITTER_BEARER_TOKEN (read), VIKI_TWITTER_API_KEY + SECRET (post).
"""
import os
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger


class TwitterSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "twitter"

    @property
    def description(self) -> str:
        return "Read timeline, search tweets, or post a tweet. Actions: timeline, search, post. Set VIKI_TWITTER_* env for API."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["timeline", "search", "post"], "description": "Action."},
                "query": {"type": "string", "description": "Search query or tweet text for post."},
                "count": {"type": "integer", "description": "Max results (default 10).", "default": 10},
            },
            "required": ["action"],
        }

    @property
    def safety_tier(self) -> str:
        return "medium"

    async def execute(self, params: Dict[str, Any]) -> str:
        action = (params.get("action") or "timeline").lower()
        query = params.get("query") or ""
        count = min(int(params.get("count", 10)), 20)

        if action == "timeline":
            bearer = os.environ.get("VIKI_TWITTER_BEARER_TOKEN")
            if not bearer:
                return "Twitter not configured: set VIKI_TWITTER_BEARER_TOKEN for timeline."
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.twitter.com/2/users/me/tweets",
                        params={"max_results": count},
                        headers={"Authorization": f"Bearer {bearer}"},
                    ) as resp:
                        if resp.status != 200:
                            return f"Twitter API error: {resp.status} {await resp.text()}"
                        data = await resp.json()
                        tweets = data.get("data", [])
                        return "TIMELINE:\n" + "\n".join([t.get("text", "")[:200] for t in tweets]) if tweets else "No tweets."
            except Exception as e:
                return f"Twitter error: {e}"

        if action == "search":
            bearer = os.environ.get("VIKI_TWITTER_BEARER_TOKEN")
            if not bearer or not query:
                return "Set VIKI_TWITTER_BEARER_TOKEN and provide query for search."
            try:
                import aiohttp
                import urllib.parse
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.twitter.com/2/tweets/search/recent",
                        params={"query": query, "max_results": count},
                        headers={"Authorization": f"Bearer {bearer}"},
                    ) as resp:
                        if resp.status != 200:
                            return f"Twitter API error: {resp.status} {await resp.text()}"
                        data = await resp.json()
                        tweets = data.get("data", [])
                        return "SEARCH:\n" + "\n".join([t.get("text", "")[:200] for t in tweets]) if tweets else "No results."
            except Exception as e:
                return f"Twitter error: {e}"

        if action == "post":
            key = os.environ.get("VIKI_TWITTER_API_KEY")
            secret = os.environ.get("VIKI_TWITTER_API_SECRET")
            if not key or not secret or not query:
                return "Set VIKI_TWITTER_API_KEY, VIKI_TWITTER_API_SECRET and provide query (tweet text) to post."
            try:
                # Twitter OAuth 1.0a for post - simplified: use requests_oauthlib or tweepy if available
                import aiohttp
                # Minimal: would need OAuth 1.0a flow; return instruction
                return "Post tweet: OAuth 1.0a required. Install tweepy and set VIKI_TWITTER_* keys, or use Twitter API v2 with OAuth 2.0 user context."
            except Exception as e:
                return f"Twitter post error: {e}"

        return "Unknown action. Use timeline, search, or post."
