"""Public safety education skill — awareness and prevention guidance."""

from __future__ import annotations

from typing import Any

from viki.skills.public_safety.base import (
    BasePublicSafetySkill,
    CapabilityDefinition,
    ConfidenceRating,
    ConfidenceScore,
    InputValidator,
)


class PublicSafetyEducationSkill(BasePublicSafetySkill):
    name = "public_safety_education"
    description = "Public safety education, awareness content, prevention strategies, and community safety guidance for various audiences."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="generate_educational_content",
                description="Generate educational safety content for a specific topic and audience",
                input_schema={
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "enum": [
                                "cybersecurity",
                                "fire_safety",
                                "first_aid",
                                "natural_disaster_prep",
                                "street_safety",
                                "online_safety",
                                "home_security",
                            ],
                            "description": "Safety education topic",
                        },
                        "audience": {
                            "type": "string",
                            "enum": ["children", "teens", "adults", "seniors", "general_public"],
                            "description": "Target audience",
                        },
                        "format": {
                            "type": "string",
                            "enum": [
                                "guide",
                                "checklist",
                                "tips",
                                "lesson_plan",
                                "infographic_text",
                            ],
                            "description": "Preferred content format",
                        },
                        "language": {
                            "type": "string",
                            "description": "Output language (default: English)",
                        },
                    },
                    "required": ["topic", "audience"],
                },
                safety_tier="safe",
                examples=[
                    {
                        "topic": "cybersecurity",
                        "audience": "seniors",
                        "format": "guide",
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_enum(
            params.get("topic", ""),
            "topic",
            [
                "cybersecurity",
                "fire_safety",
                "first_aid",
                "natural_disaster_prep",
                "street_safety",
                "online_safety",
                "home_security",
            ],
        )
        InputValidator.validate_enum(
            params.get("audience", ""),
            "audience",
            ["children", "teens", "adults", "seniors", "general_public"],
        )

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        topic = params["topic"]
        audience = params["audience"]
        content_format = params.get("format", "tips")
        language = params.get("language", "English")

        self.reasoning.add_step(
            f"Creating educational content on {topic} for {audience}",
            evidence=f"Format: {content_format}, Language: {language}",
        )

        content = {
            "topic": topic,
            "audience": audience,
            "format": content_format,
            "language": language,
            "title": self._get_title(topic, audience),
            "key_points": self._get_key_points(topic, audience),
            "tips": self._get_tips(topic, audience),
            "resources": self._get_resources(topic),
        }

        return content

    def _get_title(self, topic: str, audience: str) -> str:
        titles = {
            "cybersecurity": "Staying Safe Online",
            "fire_safety": "Fire Prevention and Safety",
            "first_aid": "Basic First Aid Everyone Should Know",
            "natural_disaster_prep": "Natural Disaster Preparedness",
            "street_safety": "Street Safety Awareness",
            "online_safety": "Internet Safety Guide",
            "home_security": "Home Security Basics",
        }
        base = titles.get(topic, "Safety Guide")
        audience_map = {"children": " for Kids", "teens": " for Teens", "seniors": " for Seniors"}
        suffix = audience_map.get(audience, "")
        return f"{base}{suffix}"

    def _get_key_points(self, topic: str, audience: str) -> list[str]:
        points = {
            "cybersecurity": [
                "Use strong, unique passwords for each account",
                "Enable two-factor authentication where available",
                "Be cautious of unsolicited emails and messages",
                "Keep software and devices updated",
                "Use reputable antivirus software",
            ],
            "fire_safety": [
                "Install smoke alarms on every level of your home",
                "Create and practice a fire escape plan",
                "Keep flammable materials away from heat sources",
                "Never leave cooking unattended",
                "Know how to use a fire extinguisher",
            ],
            "first_aid": [
                "Check the scene for safety before approaching",
                "Call emergency services for serious injuries",
                "Control bleeding with direct pressure",
                "Learn CPR — it saves lives",
                "Keep a well-stocked first aid kit",
            ],
        }
        return points.get(topic, ["Follow safety guidelines for this topic"])

    def _get_tips(self, topic: str, audience: str) -> list[str]:
        audience_adj = "simple" if audience == "children" else "practical"
        return [
            f"Remember these {audience_adj} tips",
            f"Practice {topic} habits daily",
            "Share this information with family and friends",
        ]

    def _get_resources(self, topic: str) -> list[str]:
        return [
            "Local emergency services",
            "Community safety programs",
            "Official government safety websites",
        ]

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        return ConfidenceScore(
            ConfidenceRating.HIGH,
            0.85,
            "Educational content based on established safety guidelines",
        )
