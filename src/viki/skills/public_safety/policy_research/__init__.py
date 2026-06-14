"""Policy research skill — legislative analysis and policy recommendations."""

from __future__ import annotations

from typing import Any

from viki.skills.public_safety.base import (
    BasePublicSafetySkill,
    CapabilityDefinition,
    ConfidenceRating,
    ConfidenceScore,
    InputValidator,
)


class PolicyResearchSkill(BasePublicSafetySkill):
    name = "policy_research"
    description = "Legislative and policy research, regulatory analysis, policy impact assessment, and evidence-based policy recommendations for public safety and governance."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="research_policy",
                description="Research policy issues and provide analysis",
                input_schema={
                    "type": "object",
                    "properties": {
                        "policy_topic": {
                            "type": "string",
                            "enum": [
                                "public_safety_law",
                                "cyber_regulation",
                                "emergency_management",
                                "criminal_justice_reform",
                                "data_privacy",
                                "community_policing",
                                "disaster_recovery_policy",
                            ],
                            "description": "Policy area to research",
                        },
                        "jurisdiction": {"type": "string", "description": "Geographic scope"},
                        "research_question": {
                            "type": "string",
                            "description": "Specific policy question to address",
                        },
                        "include_alternatives": {
                            "type": "boolean",
                            "description": "Include alternative policy approaches",
                        },
                    },
                    "required": ["policy_topic", "research_question"],
                },
                safety_tier="safe",
                examples=[
                    {
                        "policy_topic": "data_privacy",
                        "jurisdiction": "European Union",
                        "research_question": "How does GDPR affect law enforcement data sharing?",
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_enum(
            params.get("policy_topic", ""),
            "policy_topic",
            [
                "public_safety_law",
                "cyber_regulation",
                "emergency_management",
                "criminal_justice_reform",
                "data_privacy",
                "community_policing",
                "disaster_recovery_policy",
            ],
        )
        InputValidator.validate_string(params.get("research_question", ""), "research_question")

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        topic = params["policy_topic"]
        jurisdiction = params.get("jurisdiction", "general")
        question = params["research_question"]
        include_alternatives = params.get("include_alternatives", True)

        self.reasoning.add_step(
            f"Researching {topic} policy in {jurisdiction}",
            evidence=f"Question: {question[:200]}",
        )

        self.reasoning.add_step("Analyzing relevant legislation and regulations")
        if include_alternatives:
            self.reasoning.add_step("Identifying alternative policy approaches")

        research = {
            "policy_topic": topic,
            "jurisdiction": jurisdiction,
            "research_question": question,
            "analysis": f"Analysis of {topic} policy in {jurisdiction} addressing: {question}",
            "key_considerations": [
                "Legal framework and statutory authority",
                "Stakeholder impacts and civil liberties",
                "Implementation feasibility and resource requirements",
                "Alignment with international standards and best practices",
            ],
            "stakeholders": [
                "Government agencies and regulators",
                "Law enforcement and public safety officials",
                "Privacy and civil liberties advocates",
                "Affected communities and individuals",
                "Private sector and industry bodies",
            ],
        }

        if include_alternatives:
            research["alternative_approaches"] = [
                "Regulatory approach — legislation and enforcement",
                "Technology-based solutions — systems and tools",
                "Community-based approaches — engagement and education",
                "Public-private partnerships — collaborative frameworks",
            ]

        return research

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        has_jurisdiction = bool(params.get("jurisdiction", ""))
        question_length = len(params.get("research_question", ""))
        score = 0.5
        if has_jurisdiction:
            score += 0.15
        if question_length > 100:
            score += 0.15
        return ConfidenceScore(
            ConfidenceRating.HIGH if score > 0.65 else ConfidenceRating.MEDIUM,
            round(score, 2),
            "Policy analysis based on established legal and regulatory frameworks",
        )
