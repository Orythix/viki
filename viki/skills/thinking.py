from typing import Dict, Any
from viki.skills.base import BaseSkill

class ThinkingSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "thinking_skill"

    @property
    def description(self) -> str:
        return "Internal simulation step to plan complex tasks. Do not call this for simple queries."

    async def execute(self, params: Dict[str, Any]) -> str:
        topic = params.get("topic")
        plan = params.get("plan_content", "Analyzing request...")
        return f"[INTERNAL THOUGHT] Planning for '{topic}': {plan}"
