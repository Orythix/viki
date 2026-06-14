"""Fraud detection skill — financial crime analysis and pattern recognition."""

from __future__ import annotations

from typing import Any

from viki.skills.public_safety.base import (
    BasePublicSafetySkill,
    CapabilityDefinition,
    ConfidenceRating,
    ConfidenceScore,
    InputValidator,
)


class FraudDetectionSkill(BasePublicSafetySkill):
    name = "fraud_detection"
    description = "Fraud pattern analysis, financial crime indicators, suspicious transaction review, and anti-fraud advisory support."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="analyze_fraud",
                description="Analyze transactions or behaviors for potential fraud indicators",
                input_schema={
                    "type": "object",
                    "properties": {
                        "fraud_type": {
                            "type": "string",
                            "enum": [
                                "payment_fraud",
                                "identity_theft",
                                "insurance_fraud",
                                "benefits_fraud",
                                "investment_scam",
                            ],
                            "description": "Type of potential fraud",
                        },
                        "transactions": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "List of transactions or events to analyze",
                        },
                        "known_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Known fraud patterns to check against",
                        },
                        "report_only": {
                            "type": "boolean",
                            "description": "If true, generate summary report only",
                        },
                    },
                    "required": ["fraud_type", "transactions"],
                },
                safety_tier="medium",
                examples=[
                    {
                        "fraud_type": "payment_fraud",
                        "transactions": [
                            {
                                "amount": 5000,
                                "location": "foreign",
                                "time": "03:00",
                                "new_device": True,
                            }
                        ],
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_enum(
            params.get("fraud_type", ""),
            "fraud_type",
            [
                "payment_fraud",
                "identity_theft",
                "insurance_fraud",
                "benefits_fraud",
                "investment_scam",
            ],
        )
        transactions = params.get("transactions", [])
        if not isinstance(transactions, list) or len(transactions) == 0:
            raise ValueError("transactions must be a non-empty list")

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        fraud_type = params["fraud_type"]
        transactions = params["transactions"]
        known_patterns = params.get("known_patterns", [])

        self.reasoning.add_step(
            f"Analyzing {len(transactions)} transactions for {fraud_type}",
            evidence=f"Known patterns: {len(known_patterns)}",
        )

        flags = []
        total_amount = 0
        for tx in transactions:
            if isinstance(tx, dict):
                amount = tx.get("amount", 0)
                total_amount += amount
                if amount > 10000:
                    flags.append(f"Large transaction: ${amount}")
                if tx.get("new_device"):
                    flags.append(f"Transaction from new device: ${amount}")
                if tx.get("location") == "foreign":
                    flags.append(f"Foreign transaction: ${amount}")
                if tx.get("time"):
                    hour = int(str(tx["time"]).split(":")[0])
                    if hour < 6:
                        flags.append(f"Off-hours transaction at {tx['time']}")

        risk_score = len(flags) / max(len(transactions), 1)
        risk_level = "high" if risk_score > 0.5 else "medium" if risk_score > 0.2 else "low"

        analysis = {
            "fraud_type": fraud_type,
            "transactions_reviewed": len(transactions),
            "total_amount": total_amount,
            "flags_raised": flags,
            "flag_count": len(flags),
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "recommendations": self._get_recommendations(fraud_type, risk_level),
        }

        return analysis

    def _get_recommendations(self, fraud_type: str, risk_level: str) -> list[str]:
        recs = [
            f"Review flagged transactions manually ({fraud_type})",
            "Document findings for compliance records",
        ]
        if risk_level == "high":
            recs.append("Escalate to fraud investigation team immediately")
            recs.append("Consider freezing affected accounts pending review")
            recs.append("File Suspicious Activity Report if required")
        return recs

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        tx_count = len(params.get("transactions", []))
        if tx_count >= 20:
            return ConfidenceScore(
                ConfidenceRating.HIGH, 0.82, f"Analysis based on {tx_count} transactions"
            )
        elif tx_count >= 5:
            return ConfidenceScore(
                ConfidenceRating.MEDIUM, 0.6, f"Analysis based on {tx_count} transactions"
            )
        return ConfidenceScore(ConfidenceRating.LOW, 0.35, "Limited transaction data")
