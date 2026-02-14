import asyncio
import json
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger
from viki.core.llm import StructuredPrompt

class VideoScene(BaseModel):
    scene_number: int
    narration: str
    image_prompt: str

class Captions(BaseModel):
    instagram: str
    youtube: str
    tiktok: str

class VideoProject(BaseModel):
    video_title: str
    video_theme: str
    duration_seconds: int
    scenes: List[VideoScene]
    captions: Captions
    hashtags: List[str]

class ShortVideoSkill(BaseSkill):
    """
    Autonomous AI workflow agent for creating short form social media videos.
    Generates optimized video ideas, scripts, visual prompts, and captions for viral growth.
    """
    def __init__(self, controller):
        self.controller = controller
        self._name = "short_video_agent"
        self._description = "Generate a viral short-form video project (TikTok/Reels/Shorts) for a given topic. Returns structured JSON."

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic, theme, or starting point for the video content (e.g., 'productivity hacks', 'future of AI')"
                }
            },
            "required": ["topic"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        topic = params.get("topic", "trending technology")
        viki_logger.info(f"ShortVideoAgent: Designing viral content for topic: {topic}")

        # Construct the specialized system prompt as requested by user
        identity = (
            "You are an autonomous AI workflow agent responsible for creating and publishing short form social media videos using only free tools and APIs.\n\n"
            "Your goals are:\n"
            "- Generate daily video ideas optimized for viral short form content\n"
            "- Convert ideas into structured scripts and visual prompts\n"
            "- Trigger external tools to generate images and assemble videos\n"
            "- Prepare platform specific captions and hashtags\n"
            "- Coordinate publishing and log results"
        )

        cognitive_instructions = [
            "Content Ideation: Target Instagram Reels, YouTube Shorts, TikTok. Length 20-40s. Tone: Clear, simple, engaging.",
            "Script Generation: Hook within 3s. Max 6 scenes. Each scene visually describable.",
            "Visual Prompts: Compatible with Stable Diffusion. Include style, lighting, mood, camera angle. No copyright content.",
            "Captions: One per platform (IG, YT, TikTok) with CTA. 5-8 hashtags. No spam words.",
            "Format: Valid JSON only. No explanations. No markdown. Use the provided schema exactly.",
            "Logic: Rewrite risky content. Prefer evergreen content. Avoid emojis unless relevant."
        ]

        # Use VIKI's StructuredPrompt builder
        prompt = StructuredPrompt(request=f"Generate a viral short video project about: {topic}")
        prompt.set_identity(identity)
        for inst in cognitive_instructions:
            prompt.add_cognitive(inst)
        prompt.add_context(f"Current Date: {self.controller.settings.get('system', {}).get('current_time', '2026-02-14')}") # Heuristic date

        messages = prompt.build()

        # Select model (Reasoning/General models preferred)
        model = self.controller.model_router.get_model(capabilities=["reasoning", "general"])
        
        try:
            # chat_structured uses instructor+pydantic to ensure the exact schema
            project = await model.chat_structured(
                messages=messages,
                response_model=VideoProject,
                temperature=0.7
            )
            
            # The user requested valid JSON only, no explanations, no markdown.
            # model_dump_json() returns the raw string.
            return project.model_dump_json(indent=2)
            
        except Exception as e:
            viki_logger.error(f"ShortVideoAgent execution error: {e}")
            # Fallback error JSON
            return json.dumps({
                "error": "Failed to generate video project",
                "reason": str(e),
                "topic": topic
            }, indent=2)
