import math
from typing import Dict, Any
from viki.skills.base import BaseSkill

class MathSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "math_skill"

    @property
    def description(self) -> str:
        return "Evaluates mathematical expressions. Params: 'expression' (str)."

    async def execute(self, params: Dict[str, Any]) -> str:
        expression = params.get("expression")
        if not expression:
            return "Error: No expression provided."
        
        # Safety: restrict globals/locals
        allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("__")}
        allowed_names.update({"abs": abs, "round": round, "min": min, "max": max})
        
        try:
            # Dangerous in production without stricter parsing, but okay for prototype
            result = eval(expression, {"__builtins__": None}, allowed_names)
            return str(result)
        except Exception as e:
            return f"Math Error: {str(e)}"
