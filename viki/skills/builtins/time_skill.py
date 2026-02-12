from datetime import datetime
from typing import Dict, Any
from viki.skills.base import BaseSkill

class TimeSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "time_skill"

    @property
    def description(self) -> str:
        return "Returns the current system time and date."

    async def execute(self, params: Dict[str, Any] = None) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
