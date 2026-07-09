from typing import Any

from viki.core.orchestrator_helpers import json_type_matches


class ValidationMixin:
    def _json_type_matches(self, value: Any, expected_type: str) -> bool:
        return json_type_matches(value, expected_type)

    def _validate_required_params(self, required: list[str], params: dict[str, Any]) -> str | None:
        return self.tool_contract.validate_required_params(required, params)

    def _validate_param_spec(self, field: str, spec: dict[str, Any], val: Any) -> str | None:
        return self.tool_contract.validate_param_spec(field, spec, val)

    def _validate_property_constraints(
        self, props: dict[str, Any], params: dict[str, Any]
    ) -> str | None:
        return self.tool_contract.validate_property_constraints(props, params)

    def _validate_tool_contract_params(self, skill_name: str, params: dict[str, Any]) -> str | None:
        return self.tool_contract.validate_params(skill_name, params)

    def _validate_skill_output(self, skill_name: str, output: Any) -> str | None:
        return self.tool_contract.validate_output(skill_name, output)

    def _compress_output(self, text: str) -> str:
        if not text:
            return text
        fillers = [
            "I will now",
            "I am going to",
            "Let me see",
            "Starting the process of",
            "Confirmed.",
            "Okay,",
            "Certainly.",
            "Processing...",
            "Executing command:",
        ]
        cleaned = text
        for f in fillers:
            cleaned = cleaned.replace(f, "").strip()
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned
