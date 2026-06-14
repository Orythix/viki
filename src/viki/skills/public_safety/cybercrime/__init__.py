"""Cybercrime analysis skill — digital forensics and threat intelligence."""

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


class CybercrimeAnalysisSkill(BasePublicSafetySkill):
    name = "cybercrime"
    description = "Cybercrime pattern analysis, digital forensics guidance, indicator of compromise analysis, and cybersecurity incident response support."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="analyze_threat",
                description="Analyze cyber threat indicators and provide mitigation guidance",
                input_schema={
                    "type": "object",
                    "properties": {
                        "threat_type": {
                            "type": "string",
                            "enum": [
                                "phishing",
                                "malware",
                                "ransomware",
                                "ddos",
                                "social_engineering",
                                "data_breach",
                            ],
                            "description": "Type of cyber threat",
                        },
                        "indicators": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of indicators (IPs, URLs, hashes, etc.)",
                        },
                        "description": {
                            "type": "string",
                            "description": "Description of the incident",
                        },
                    },
                    "required": ["threat_type", "indicators"],
                },
                safety_tier="medium",
                examples=[
                    {
                        "threat_type": "phishing",
                        "indicators": ["suspicious@phish.com", "http://fake-bank.login.com"],
                        "description": "Employee received suspicious email requesting credentials",
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_enum(
            params.get("threat_type", ""),
            "threat_type",
            ["phishing", "malware", "ransomware", "ddos", "social_engineering", "data_breach"],
        )
        indicators = params.get("indicators", [])
        if not isinstance(indicators, list) or len(indicators) == 0:
            raise ValueError("indicators must be a non-empty list")
        desc = params.get("description", "")
        if desc:
            InputValidator.validate_string(desc, "description")

    def _safety_check(self, params: dict[str, Any]) -> SafetyCheckResult:
        desc = params.get("description", "")
        if any(
            kw in desc.lower()
            for kw in ["how to hack", "exploit code", "deploy malware", "attack tool"]
        ):
            return SafetyCheckResult(
                passed=False,
                refused=True,
                reason="Cannot provide instructions for offensive cyber activities or attack tools.",
                triggered_rules=["cybercrime:offensive_guidance"],
            )
        return super()._safety_check(params)

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        threat_type = params["threat_type"]
        indicators = params["indicators"]
        description = params.get("description", "")

        self.reasoning.add_step(
            f"Analyzing {threat_type} threat", evidence=f"{len(indicators)} indicators"
        )
        if description:
            self.reasoning.add_step(f"Incident context: {description[:200]}")

        analysis = {
            "threat_type": threat_type,
            "indicators_analyzed": len(indicators),
            "risk_level": "high" if threat_type in ("ransomware", "data_breach") else "medium",
            "analysis": f"Analyzed {len(indicators)} indicators for {threat_type} activity.",
            "recommendations": self._get_recommendations(threat_type),
        }

        return analysis

    def _get_recommendations(self, threat_type: str) -> list[str]:
        recommendations = {
            "phishing": [
                "Notify all potential targets immediately",
                "Block sender domains at mail gateway",
                "Run security awareness reminder for staff",
                "Scan for any credentials already compromised",
            ],
            "malware": [
                "Isolate affected systems from the network",
                "Run full antivirus/EDR scan on all endpoints",
                "Collect samples for further analysis",
                "Review firewall logs for C2 communications",
            ],
            "ransomware": [
                "Immediately isolate all affected systems",
                "Disable network shares and SMB protocols if not needed",
                "Activate incident response plan",
                "Do NOT pay the ransom — contact law enforcement",
                "Restore from offline backups if available",
            ],
            "data_breach": [
                "Identify and contain the breach vector",
                "Preserve forensic evidence (logs, disk images)",
                "Notify DPO and legal team",
                "Assess scope of data exposed",
                "Notify affected parties as required by regulations",
            ],
        }
        return recommendations.get(
            threat_type, ["Investigate and contain the threat", "Contact cybersecurity team"]
        )

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        return ConfidenceScore(
            ConfidenceRating.MEDIUM, 0.6, "Based on provided indicators and known threat patterns"
        )
