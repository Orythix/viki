"""Citizen assistance skill — public guidance and support services."""

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


class CitizenAssistanceSkill(BasePublicSafetySkill):
    name = "citizen_assistance"
    description = "Citizen support and guidance for public safety concerns, victim assistance resources, reporting procedures, and access to support services."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="assist_citizen",
                description="Provide guidance and resources for a citizen's public safety concern",
                input_schema={
                    "type": "object",
                    "properties": {
                        "inquiry_type": {
                            "type": "string",
                            "enum": [
                                "report_crime",
                                "victim_support",
                                "safety_concern",
                                "resource_referral",
                                "legal_guidance",
                                "emergency_preparedness",
                            ],
                            "description": "Type of citizen inquiry",
                        },
                        "concern": {
                            "type": "string",
                            "description": "Description of the citizen's concern or question",
                        },
                        "location": {
                            "type": "string",
                            "description": "City or region for localized resources",
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["routine", "urgent", "emergency"],
                            "description": "Urgency level of the inquiry",
                        },
                    },
                    "required": ["inquiry_type", "concern"],
                },
                safety_tier="safe",
                examples=[
                    {
                        "inquiry_type": "victim_support",
                        "concern": "I was the victim of a burglary and need help with resources",
                        "urgency": "routine",
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_enum(
            params.get("inquiry_type", ""),
            "inquiry_type",
            [
                "report_crime",
                "victim_support",
                "safety_concern",
                "resource_referral",
                "legal_guidance",
                "emergency_preparedness",
            ],
        )
        InputValidator.validate_string(params.get("concern", ""), "concern")
        urgency = params.get("urgency", "routine")
        if urgency:
            InputValidator.validate_enum(urgency, "urgency", ["routine", "urgent", "emergency"])

    def _safety_check(self, params: dict[str, Any]) -> SafetyCheckResult:
        urgency = params.get("urgency", "routine")
        if urgency == "emergency":
            return SafetyCheckResult(
                passed=True,
                reason="Emergency flagged — ensure immediate referral to emergency services",
            )
        return super()._safety_check(params)

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        inquiry_type = params["inquiry_type"]
        concern = params["concern"]
        location = params.get("location", "")
        urgency = params.get("urgency", "routine")

        self.reasoning.add_step(
            f"Processing {urgency} {inquiry_type} inquiry",
            evidence=f"Location: {location or 'not specified'}",
        )

        response = {
            "inquiry_type": inquiry_type,
            "concern": concern,
            "location": location,
            "urgency": urgency,
            "guidance": self._get_guidance(inquiry_type, urgency),
            "resources": self._get_resources(inquiry_type, location),
            "disclaimer": (
                "This information is for guidance purposes only. Contact local authorities "
                "or emergency services for immediate assistance. For emergency situations, "
                "always call your local emergency number (911 in the US)."
            ),
        }

        return response

    def _get_guidance(self, inquiry_type: str, urgency: str) -> list[str]:
        if urgency == "emergency":
            return [
                "Call emergency services immediately (911 in US / 112 in EU / 999 in UK)",
                "Stay on the line with the dispatcher until help arrives",
                "Provide your exact location and description of the situation",
            ]

        guidance_map = {
            "report_crime": [
                "Contact your local police department's non-emergency line",
                "Document any evidence you have (photos, documents, etc.)",
                "Write down everything you remember about the incident",
                "Get the case/report number for your records",
            ],
            "victim_support": [
                "Your safety is the priority — ensure you are in a safe location",
                "Contact victim support organizations in your area",
                "Consider speaking with a counselor or advocate",
                "Keep records of all communications with authorities",
            ],
            "safety_concern": [
                "Document the specific safety concern with details",
                "Report to appropriate local authorities",
                "Notify building management or property owner if applicable",
                "Consider community safety resources and neighborhood watch",
            ],
            "resource_referral": [
                "Identify which type of assistance you need",
                "Check eligibility requirements for available programs",
                "Prepare necessary documentation for applications",
                "Contact the relevant agency directly for specific guidance",
            ],
            "legal_guidance": [
                "This is not legal advice — consult with a qualified attorney",
                "Legal aid societies may provide free or low-cost consultations",
                "Keep all documents and correspondence related to your case",
                "Understand your rights before making statements",
            ],
            "emergency_preparedness": [
                "Create an emergency kit with supplies for at least 72 hours",
                "Develop a family emergency communication plan",
                "Know evacuation routes from your home and neighborhood",
                "Stay informed about local emergency alert systems",
            ],
        }
        return guidance_map.get(inquiry_type, ["Contact local authorities for assistance"])

    def _get_resources(self, inquiry_type: str, location: str) -> list[str]:
        resources = ["Local police department (non-emergency line)"]
        if inquiry_type == "victim_support":
            resources.extend(
                [
                    "Victim compensation programs",
                    "Domestic violence hotlines",
                    "Mental health counseling services",
                ]
            )
        elif inquiry_type == "legal_guidance":
            resources.extend(
                [
                    "Legal aid societies",
                    "Pro bono legal clinics",
                    "Bar association referral services",
                ]
            )
        if location:
            resources.append(
                f"Local resources in {location} — search online or call 311 for city services"
            )
        return resources

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        has_location = bool(params.get("location", ""))
        concern_length = len(params.get("concern", ""))
        score = 0.6
        if has_location:
            score += 0.1
        if concern_length > 50:
            score += 0.1
        return ConfidenceScore(
            ConfidenceRating.HIGH if score > 0.7 else ConfidenceRating.MEDIUM,
            round(score, 2),
            "Guidance based on established protocols and available resources",
        )
