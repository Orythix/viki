"""Tool-contract validation for skill parameters and outputs.

Extracted from ``VIKIController`` so contract rules can be tested and
evolved independently of the orchestrator.
"""

from __future__ import annotations

from typing import Any

from viki.core.orchestrator_helpers import json_type_matches


class ToolContractValidator:
    """Validates skill params against declared schemas and sanity-checks outputs.

    Parameters
    ----------
    skill_registry:
        Object exposing ``get_skill(name)``.
    safety:
        Object exposing ``validate_response(text) -> dict`` (optional checks).
    """

    def __init__(self, skill_registry: Any, safety: Any = None):
        self.skill_registry = skill_registry
        self.safety = safety

    def validate_required_params(self, required: list[str], params: dict[str, Any]) -> str | None:
        """Validate required schema fields are present and non-empty."""
        for field in required:
            if field not in params:
                return f"Tool contract violation: missing required param '{field}'."
            val = params.get(field)
            if val is None:
                return f"Tool contract violation: required param '{field}' is None."
            if isinstance(val, str) and not val.strip():
                return f"Tool contract violation: required param '{field}' is empty."
        return None

    def validate_param_spec(self, field: str, spec: dict[str, Any], val: Any) -> str | None:
        """Validate enum/type constraints for a single parameter spec."""
        if "enum" in spec and isinstance(spec["enum"], list):
            allowed = spec["enum"]
            if val not in allowed:
                return (
                    f"Tool contract violation: param '{field}' must be one of "
                    f"{allowed}, got {val!r}."
                )

        expected_type = spec.get("type")
        if expected_type and not json_type_matches(val, str(expected_type)):
            return (
                f"Tool contract violation: param '{field}' expected type "
                f"'{expected_type}', got {type(val).__name__}."
            )

        return None

    def validate_property_constraints(
        self, props: dict[str, Any], params: dict[str, Any]
    ) -> str | None:
        """Validate provided parameters against enum/type constraints in schema."""
        for field, spec in props.items():
            if field not in params or not isinstance(spec, dict):
                continue
            val = params.get(field)
            err = self.validate_param_spec(field, spec, val)
            if err:
                return err
        return None

    def validate_params(self, skill_name: str, params: dict[str, Any]) -> str | None:
        """Validate incoming params against the skill's declared ``schema``.

        Returns None if validation passes, otherwise a tool-contract error string.
        """
        skill = self.skill_registry.get_skill(skill_name)
        if not skill:
            return f"Tool contract violation: skill '{skill_name}' not found."

        schema = getattr(skill, "schema", None) or {}
        if not isinstance(schema, dict) or not schema:
            # No contract available; don't block.
            return None

        required = schema.get("required") or []
        props = schema.get("properties") or {}
        err = self.validate_required_params(required, params)
        if err:
            return err
        return self.validate_property_constraints(props, params)

    def validate_output(self, skill_name: str, output: Any) -> str | None:
        """Validate skill output for common failure modes.

        Catches empty output, explicit errors, and safety contradictions.
        Returns None if valid, otherwise an output-validation error string.
        """
        if output is None:
            return f"Tool contract output validation failed: '{skill_name}' returned None."

        out_str = output if isinstance(output, str) else str(output)
        if not out_str.strip():
            return (
                f"Tool contract output validation failed: "
                f"'{skill_name}' returned an empty string."
            )

        out_lower = out_str.strip().lower()
        error_signals = ("error:", "command failed", "shell error:", "action failed:")
        if any(s in out_lower for s in error_signals):
            return (
                f"Tool contract output validation failed: "
                f"'{skill_name}' produced an error-like result."
            )

        # Reuse existing safety response validators for hallucination patterns.
        if self.safety is not None:
            try:
                resp_check = self.safety.validate_response(out_str)
                if not resp_check.get("valid", True):
                    issues = resp_check.get("issues") or []
                    return (
                        f"Tool contract output validation failed: '{skill_name}' "
                        f"output failed safety validation: {issues}"
                    )
            except Exception:
                # If validation itself fails, don't block execution completion.
                pass

        return None
