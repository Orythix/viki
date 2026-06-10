"""
Image generation (DALL-E or Gemini). Set OPENAI_API_KEY or GEMINI API key. Actions: generate(prompt, size).
"""
import os
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger


class ImageGenSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "image_gen"

    @property
    def description(self) -> str:
        return "Generate an image from a text prompt (DALL-E). Params: prompt, size (1024x1024, 1792x1024, 1024x1792)."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image description."},
                "size": {"type": "string", "enum": ["1024x1024", "1792x1024", "1024x1792"], "default": "1024x1024"},
            },
            "required": ["prompt"],
        }

    @property
    def safety_tier(self) -> str:
        return "medium"

    async def execute(self, params: Dict[str, Any]) -> str:
        prompt = params.get("prompt")
        if not prompt:
            return "Error: prompt required."
        size = params.get("size", "1024x1024")
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            return "Set OPENAI_API_KEY for DALL-E image generation."
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": "dall-e-3", "prompt": prompt[:4000], "size": size, "n": 1},
                ) as resp:
                    if resp.status != 200:
                        return f"OpenAI API error: {resp.status} {await resp.text()}"
                    data = await resp.json()
                    url = data.get("data", [{}])[0].get("url")
                    if url:
                        return f"Generated image: {url}"
                    revised = data.get("data", [{}])[0].get("revised_prompt", "")
                    return f"Generated (no URL in response). Revised prompt: {revised[:200]}"
        except Exception as e:
            return f"Image gen error: {e}"
