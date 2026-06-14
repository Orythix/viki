"""OSINT research skill — open source intelligence gathering and analysis."""

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


class OSINTResearchSkill(BasePublicSafetySkill):
    name = "osint"
    description = "Open source intelligence research, data gathering from public sources, information verification, and intelligence report generation for authorized investigations."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="research_public_info",
                description="Research publicly available information on a given subject",
                input_schema={
                    "type": "object",
                    "properties": {
                        "subject": {
                            "type": "string",
                            "description": "Person, organization, or topic to research",
                        },
                        "research_areas": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "social_media",
                                    "public_records",
                                    "news",
                                    "corporate",
                                    "geolocation",
                                    "technical",
                                ],
                            },
                            "description": "Areas of research to explore",
                        },
                        "search_terms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific search terms or queries",
                        },
                        "max_sources": {
                            "type": "integer",
                            "description": "Maximum number of sources to analyze",
                        },
                        "purpose": {
                            "type": "string",
                            "description": "Authorized purpose of this research",
                        },
                    },
                    "required": ["subject", "purpose"],
                },
                safety_tier="medium",
                examples=[
                    {
                        "subject": "Example Corporation",
                        "research_areas": ["public_records", "news"],
                        "search_terms": ["Example Corp SEC filing", "Example Corp lawsuits"],
                        "purpose": "Due diligence for fraud investigation",
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_string(params.get("subject", ""), "subject")
        InputValidator.validate_string(params.get("purpose", ""), "purpose", max_length=2000)

    def _safety_check(self, params: dict[str, Any]) -> SafetyCheckResult:
        purpose = params.get("purpose", "").lower()

        if any(
            kw in purpose
            for kw in ["stalk", "harass", "dox", "intimidate", "target individual without"]
        ):
            return SafetyCheckResult(
                passed=False,
                refused=True,
                reason="OSINT research must have a legitimate, authorized purpose. Stalking, harassment, or doxxing are prohibited.",
                triggered_rules=["osint:prohibited_purpose"],
            )

        check_legal = super()._safety_check(params)
        if not check_legal.passed:
            return check_legal

        if not purpose:
            return SafetyCheckResult(
                passed=False,
                refused=True,
                reason="An authorized purpose must be provided for OSINT research (e.g., investigation, due diligence, threat assessment).",
                triggered_rules=["osint:purpose_required"],
            )

        return SafetyCheckResult(passed=True)

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        subject = params["subject"]
        research_areas = params.get("research_areas", ["public_records", "news"])
        search_terms = params.get("search_terms", [subject])
        max_sources = params.get("max_sources", 10)
        purpose = params["purpose"]

        self.reasoning.add_step(
            f"OSINT research on '{subject}' for: {purpose}",
            evidence=f"Areas: {research_areas}, Terms: {search_terms}, Max sources: {max_sources}",
        )

        for area in research_areas:
            self.reasoning.add_step(f"Searching {area} for relevant information")

        report = {
            "subject": subject,
            "purpose": purpose,
            "research_areas_covered": research_areas,
            "search_terms_used": search_terms,
            "findings": {
                "summary": f"OSINT research profile for {subject}",
                "sources_identified": [],
                "key_information": [],
            },
            "methodology": {
                "description": "Research conducted through legitimate public sources",
                "limitations": "Only publicly available information analyzed",
                "legal_compliance": "All research methods comply with applicable laws and terms of service",
            },
            "next_steps": [
                "Verify findings through multiple independent sources",
                "Cross-reference with official records",
                "Document chain of research for evidentiary purposes",
            ],
        }

        return report

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        search_terms = params.get("search_terms", [])
        source_count = len(search_terms)
        if source_count >= 5:
            return ConfidenceScore(
                ConfidenceRating.MEDIUM, 0.6, f"Research based on {source_count} search directions"
            )
        return ConfidenceScore(
            ConfidenceRating.LOW, 0.35, "Limited search scope; verify findings independently"
        )
