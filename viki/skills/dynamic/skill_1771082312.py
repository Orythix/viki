from typing import Dict, Any
import os
import platform
import sys
from viki.skills.base import BaseSkill

class SystemInfoSkill(BaseSkill):
    name = "system_info"
    description = "Returns the current system platform and Python version."
    schema = {}

    async def execute(self, **kwargs: Dict[str, Any]) -> str:
        system_platform = platform.system()
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

        result = f"System Platform: {system_platform}\nPython Version: {python_version}"
        return result
