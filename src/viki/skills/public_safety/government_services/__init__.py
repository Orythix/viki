"""Government services skill — public information and administrative guidance."""

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


class GovernmentServicesSkill(BasePublicSafetySkill):
    name = "government_services"
    description = "Government service information, application guidance, eligibility checks, and administrative procedures for public assistance programs."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="get_service_info",
                description="Provide information about government services and programs",
                input_schema={
                    "type": "object",
                    "properties": {
                        "service_category": {
                            "type": "string",
                            "enum": [
                                "benefits",
                                "licensing",
                                "permits",
                                "legal_aid",
                                "social_services",
                                "healthcare",
                                "housing",
                                "immigration",
                            ],
                            "description": "Category of government service",
                        },
                        "query": {
                            "type": "string",
                            "description": "Specific question about the service",
                        },
                        "jurisdiction": {
                            "type": "string",
                            "description": "Country, state, or locality",
                        },
                    },
                    "required": ["service_category", "query"],
                },
                safety_tier="safe",
                examples=[
                    {
                        "service_category": "benefits",
                        "query": "How do I apply for food assistance?",
                        "jurisdiction": "United States",
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_enum(
            params.get("service_category", ""),
            "service_category",
            [
                "benefits",
                "licensing",
                "permits",
                "legal_aid",
                "social_services",
                "healthcare",
                "housing",
                "immigration",
            ],
        )
        InputValidator.validate_string(params.get("query", ""), "query")

    def _safety_check(self, params: dict[str, Any]) -> SafetyCheckResult:
        query = params.get("query", "").lower()
        if any(
            kw in query
            for kw in ["how to fake", "how to forge", "false documents", "fraudulent application"]
        ):
            return SafetyCheckResult(
                passed=False,
                refused=True,
                reason="Cannot provide guidance on illegal activities or document fraud.",
                triggered_rules=["government:fraud_guidance"],
            )
        return super()._safety_check(params)

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        category = params["service_category"]
        query = params["query"]
        jurisdiction = params.get("jurisdiction", "general")

        self.reasoning.add_step(
            f"Researching {category} services for '{query}'",
            evidence=f"Jurisdiction: {jurisdiction}",
        )

        info = {
            "service_category": category,
            "query": query,
            "jurisdiction": jurisdiction,
            "information": f"Information about {category} services related to: {query}",
            "disclaimer": (
                "This information is for general guidance only. Contact the relevant "
                "government agency for official, up-to-date information specific to your situation."
            ),
            "next_steps": [
                f"Visit official {jurisdiction} government website for {category}",
                "Contact the relevant agency directly for personalized assistance",
                "Verify current eligibility requirements before applying",
            ],
        }

        return info

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        return ConfidenceScore(
            ConfidenceRating.MEDIUM,
            0.6,
            "Information based on general knowledge of government services; verify with official sources",
        )
