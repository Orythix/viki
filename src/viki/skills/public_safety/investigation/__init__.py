"""Investigation skill — case management and investigative analysis."""

from __future__ import annotations

from typing import Any

from viki.skills.public_safety.base import (
    BasePublicSafetySkill,
    CapabilityDefinition,
    ConfidenceRating,
    ConfidenceScore,
    InputValidator,
)


class InvestigationSkill(BasePublicSafetySkill):
    name = "investigation"
    description = "Case management, evidence analysis, timeline reconstruction, and investigative reasoning for law enforcement and public safety."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="analyze_case",
                description="Analyze a case with given evidence and generate investigative insights",
                input_schema={
                    "type": "object",
                    "properties": {
                        "case_id": {"type": "string", "description": "Unique case identifier"},
                        "incident_type": {"type": "string", "description": "Type of incident"},
                        "evidence": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of evidence items or facts",
                        },
                        "timeline": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Timeline of events (optional)",
                        },
                    },
                    "required": ["case_id", "incident_type", "evidence"],
                },
                safety_tier="medium",
                examples=[
                    {
                        "case_id": "CASE-2024-001",
                        "incident_type": "theft",
                        "evidence": [
                            "Security footage shows suspect at 2:30 AM",
                            "Fingerprint found on window",
                        ],
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_string(params.get("case_id", ""), "case_id")
        InputValidator.validate_string(params.get("incident_type", ""), "incident_type")
        evidence = params.get("evidence", [])
        if not isinstance(evidence, list) or len(evidence) == 0:
            raise ValueError("evidence must be a non-empty list")

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        case_id = params["case_id"]
        incident_type = params["incident_type"]
        evidence = params["evidence"]
        timeline = params.get("timeline", [])

        self.reasoning.add_step(
            f"Analyzing case {case_id}: {incident_type}", evidence=", ".join(evidence)
        )
        if timeline:
            self.reasoning.add_step(f"Reviewing timeline with {len(timeline)} events")

        leads = []
        for item in evidence:
            leads.append(f"Investigate: {item}")

        findings = {
            "case_id": case_id,
            "incident_type": incident_type,
            "evidence_count": len(evidence),
            "leads_generated": leads,
            "timeline_events": len(timeline),
            "preliminary_assessment": f"Case {case_id} involves {incident_type}. {len(leads)} investigative leads identified.",
        }

        return findings

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        evidence_count = len(params.get("evidence", []))
        if evidence_count >= 5:
            return ConfidenceScore(
                ConfidenceRating.HIGH, 0.85, f"Analysis based on {evidence_count} evidence items"
            )
        elif evidence_count >= 2:
            return ConfidenceScore(
                ConfidenceRating.MEDIUM, 0.6, f"Analysis based on {evidence_count} evidence items"
            )
        return ConfidenceScore(
            ConfidenceRating.LOW, 0.35, "Limited evidence available for analysis"
        )
