import re
from typing import Any


class SafetyService:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.constraints = config.get("constraints", {})
        self.confirmation_required = self.constraints.get("confirmation_required", [])

        self.prohibited_patterns = [
            r"rm -rf",
            r"format [a-z]:",
            r"Mass Delete",
            r"dd if=",
            r"sudo ",
            r"chmod ",
            r"chown ",
        ]

        self.injection_blocklist = [
            "jailbreak",
            "DAN ",
            "ignore all previous",
            "ignore previous instructions",
            "disregard your instructions",
        ]

    def sanitize_request(self, prompt_text: str) -> str:
        if not prompt_text:
            return prompt_text
        sanitized = re.sub(r"SYSTEM:.*", "", prompt_text, flags=re.IGNORECASE)
        sanitized = re.sub(r"IGNORE PREVIOUS INSTRUCTIONS", "", sanitized, flags=re.IGNORECASE)
        for phrase in self.injection_blocklist:
            sanitized = re.sub(re.escape(phrase), "[removed]", sanitized, flags=re.IGNORECASE)
        return sanitized

    def validate_action(self, skill_name: str, params: dict[str, Any]) -> bool:
        param_str = str(params)
        for pattern in self.prohibited_patterns:
            if re.search(pattern, param_str, re.IGNORECASE):
                return False
        return True

    def get_action_severity(self, skill_name: str, params: dict[str, Any]) -> str:
        param_str = str(params).lower()
        destructive_keywords = ["Mass Delete", "truncate ", "format ", "rm -rf"]
        if any(k in param_str for k in destructive_keywords):
            return "destructive"
        medium_keywords = ["delete", "remove", "kill", "terminate", "uninstall"]
        if any(k in param_str for k in medium_keywords) or skill_name == "system_shell":
            return "medium"
        return "safe"

    def requires_confirmation(self, skill_name: str) -> bool:
        return skill_name in self.confirmation_required
