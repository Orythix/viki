"""Emergency response skill — crisis assessment and response coordination."""

from __future__ import annotations

from typing import Any

from viki.skills.public_safety.base import (
    BasePublicSafetySkill,
    CapabilityDefinition,
    ConfidenceRating,
    ConfidenceScore,
    InputValidator,
    SafetyCheckResult,
)


class EmergencyResponseSkill(BasePublicSafetySkill):
    name = "emergency_response"
    description = "Emergency situation assessment, response guidance, resource coordination, and safety recommendations for crisis scenarios."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="assess_emergency",
                description="Assess an emergency situation and provide response guidance",
                input_schema={
                    "type": "object",
                    "properties": {
                        "emergency_type": {
                            "type": "string",
                            "enum": [
                                "fire",
                                "medical",
                                "natural_disaster",
                                "active_threat",
                                "hazmat",
                                "missing_person",
                                "structural_collapse",
                            ],
                            "description": "Type of emergency",
                        },
                        "location": {
                            "type": "object",
                            "properties": {
                                "address": {"type": "string"},
                                "lat": {"type": "number"},
                                "lon": {"type": "number"},
                            },
                            "description": "Location of the emergency",
                        },
                        "severity_level": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "critical"],
                            "description": "Perceived severity level",
                        },
                        "details": {
                            "type": "string",
                            "description": "Additional details about the situation",
                        },
                        "resources_available": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of available resources (personnel, equipment)",
                        },
                    },
                    "required": ["emergency_type", "severity_level"],
                },
                safety_tier="medium",
                examples=[
                    {
                        "emergency_type": "fire",
                        "location": {"address": "123 Main St"},
                        "severity_level": "high",
                        "details": "Visible smoke from second floor",
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_enum(
            params.get("emergency_type", ""),
            "emergency_type",
            [
                "fire",
                "medical",
                "natural_disaster",
                "active_threat",
                "hazmat",
                "missing_person",
                "structural_collapse",
            ],
        )
        InputValidator.validate_enum(
            params.get("severity_level", ""),
            "severity_level",
            ["low", "medium", "high", "critical"],
        )

    def _safety_check(self, params: dict[str, Any]) -> SafetyCheckResult:
        sev = params.get("severity_level", "low")
        if sev in ("high", "critical"):
            self.audit_logger.log(
                self.name,
                "high_severity_alert",
                status="warning",
                details={"severity": sev, "type": params.get("emergency_type")},
            )
        return super()._safety_check(params)

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        emergency_type = params["emergency_type"]
        severity_level = params["severity_level"]
        location = params.get("location", {})
        resources = params.get("resources_available", [])

        self.reasoning.add_step(
            f"Assessing {severity_level} severity {emergency_type} emergency",
            evidence=f"Location: {location.get('address', 'unknown')}, Resources: {len(resources)}",
        )

        response = {
            "emergency_type": emergency_type,
            "severity": severity_level,
            "location": location,
            "assessment": f"{severity_level.upper()} severity {emergency_type} incident",
            "immediate_actions": self._get_immediate_actions(emergency_type, severity_level),
            "resources_needed": self._get_resources(emergency_type, severity_level),
            "coordination_ tips": [
                "Establish incident command system",
                "Designate safety officer",
                "Maintain communication log",
            ],
            "priority": "IMMEDIATE" if severity_level in ("high", "critical") else "STANDARD",
        }

        return response

    def _get_immediate_actions(self, emergency_type: str, severity: str) -> list[str]:
        base = ["Ensure personal safety first", "Call emergency services (911/112/999)"]
        if emergency_type == "fire":
            base.extend(
                ["Evacuate the area immediately", "Close doors behind you", "Do not use elevators"]
            )
        elif emergency_type == "medical":
            base.extend(
                [
                    "Check responsiveness and breathing",
                    "Control any bleeding with direct pressure",
                    "Do not move the person unless in immediate danger",
                ]
            )
        elif emergency_type == "active_threat":
            base.extend(
                [
                    "RUN — evacuate if safe to do so",
                    "HIDE — find secure location, lock doors",
                    "FIGHT — only as last resort",
                ]
            )
        elif emergency_type == "hazmat":
            base.extend(
                [
                    "Move upwind and uphill from the spill",
                    "Avoid breathing fumes",
                    "Do not touch unknown substances",
                ]
            )
        elif emergency_type == "missing_person":
            base.extend(
                [
                    "Secure the area and preserve scene",
                    "Gather last known location and description",
                    "Coordinate search efforts",
                ]
            )
        return base

    def _get_resources(self, emergency_type: str, severity: str) -> list[str]:
        base = ["Emergency responders", "First aid kits"]
        if severity in ("high", "critical"):
            base.extend(
                ["Multiple response units", "Incident command post", "Medical evacuation support"]
            )
        if emergency_type == "fire":
            base.extend(
                ["Fire suppression equipment", "Breathing apparatus", "Thermal imaging cameras"]
            )
        elif emergency_type == "hazmat":
            base.extend(["Hazmat suits", "Decontamination equipment", "Chemical spill kit"])
        return base

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        details = params.get("details", "")
        has_location = bool(params.get("location", {}))
        score = 0.6
        if has_location:
            score += 0.15
        if len(details) > 50:
            score += 0.15
        score = min(score, 0.95)
        return ConfidenceScore(
            ConfidenceRating.HIGH if score > 0.7 else ConfidenceRating.MEDIUM,
            round(score, 2),
            f"Assessment based on severity level and {' '.join(['detailed input' if len(details) > 50 else '', 'location data' if has_location else ''])}",
        )
