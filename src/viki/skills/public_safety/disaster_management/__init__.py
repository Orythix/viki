"""Disaster management skill — preparedness, response, and recovery planning."""

from __future__ import annotations

from typing import Any

from viki.skills.public_safety.base import (
    BasePublicSafetySkill,
    CapabilityDefinition,
    ConfidenceRating,
    ConfidenceScore,
    InputValidator,
)


class DisasterManagementSkill(BasePublicSafetySkill):
    name = "disaster_management"
    description = "Disaster risk assessment, preparedness planning, evacuation coordination, resource allocation, and post-disaster recovery guidance."

    @property
    def capabilities(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                name="assess_disaster",
                description="Assess disaster risk and provide preparedness/response recommendations",
                input_schema={
                    "type": "object",
                    "properties": {
                        "disaster_type": {
                            "type": "string",
                            "enum": [
                                "earthquake",
                                "flood",
                                "hurricane",
                                "wildfire",
                                "tsunami",
                                "pandemic",
                                "industrial_accident",
                            ],
                            "description": "Type of disaster",
                        },
                        "region": {"type": "string", "description": "Affected region or area"},
                        "population_estimate": {
                            "type": "integer",
                            "description": "Estimated affected population",
                        },
                        "infrastructure_status": {
                            "type": "string",
                            "enum": ["intact", "damaged", "severely_damaged", "destroyed"],
                            "description": "Status of local infrastructure",
                        },
                        "phase": {
                            "type": "string",
                            "enum": ["preparedness", "response", "recovery", "mitigation"],
                            "description": "Disaster management phase",
                        },
                    },
                    "required": ["disaster_type", "phase"],
                },
                safety_tier="medium",
                examples=[
                    {
                        "disaster_type": "earthquake",
                        "region": "Coastal City",
                        "infrastructure_status": "damaged",
                        "phase": "response",
                    }
                ],
            ),
        ]

    def _validate_params(self, params: dict[str, Any]):
        InputValidator.validate_enum(
            params.get("disaster_type", ""),
            "disaster_type",
            [
                "earthquake",
                "flood",
                "hurricane",
                "wildfire",
                "tsunami",
                "pandemic",
                "industrial_accident",
            ],
        )
        InputValidator.validate_enum(
            params.get("phase", ""),
            "phase",
            ["preparedness", "response", "recovery", "mitigation"],
        )

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        disaster_type = params["disaster_type"]
        region = params.get("region", "unknown")
        population = params.get("population_estimate", 0)
        infrastructure = params.get("infrastructure_status", "intact")
        phase = params["phase"]

        self.reasoning.add_step(
            f"Assessing {disaster_type} disaster in {region}",
            evidence=f"Phase: {phase}, Population: {population}, Infrastructure: {infrastructure}",
        )

        plan = {
            "disaster_type": disaster_type,
            "region": region,
            "population_estimate": population,
            "infrastructure_status": infrastructure,
            "phase": phase,
            "risk_assessment": f"{disaster_type.upper()} event affecting {region}",
            "immediate_priorities": self._get_priorities(disaster_type, phase, infrastructure),
            "resource_requirements": self._get_resources(disaster_type, population),
            "recovery_steps": self._get_recovery_steps(phase) if phase == "recovery" else [],
            "communication_plan": [
                "Establish public information hotline",
                "Use emergency alert systems (WEA, sirens)",
                "Coordinate with local media for updates",
                "Set up community information centers",
            ],
        }

        return plan

    def _get_priorities(self, disaster_type: str, phase: str, infrastructure: str) -> list[str]:
        if phase == "preparedness":
            return [
                "Develop evacuation routes and shelter plans",
                "Stock emergency supplies (water, food, medical)",
                "Conduct community drills and training",
                "Strengthen infrastructure resilience",
                "Establish early warning systems",
            ]
        elif phase == "response":
            priorities = [
                "Ensure safety of responders and public",
                "Conduct search and rescue operations",
                "Establish emergency shelters",
                "Provide medical triage and treatment",
                "Restore critical infrastructure (power, water, communications)",
            ]
            if infrastructure in ("severely_damaged", "destroyed"):
                priorities.insert(0, "Deploy mobile communication units")
                priorities.insert(1, "Establish field hospitals")
            return priorities
        elif phase == "recovery":
            return [
                "Assess structural damage to buildings",
                "Process disaster assistance applications",
                "Provide mental health support services",
                "Coordinate debris removal and cleanup",
                "Plan for long-term reconstruction",
            ]
        return ["Assess current situation and update plans"]

    def _get_resources(self, disaster_type: str, population: int) -> list[str]:
        resources = ["Emergency response personnel", "Medical supplies and equipment"]
        if population > 10000:
            resources.extend(
                ["Mass shelter facilities", "Mobile kitchens", "Water purification systems"]
            )
        if disaster_type == "flood":
            resources.extend(
                [
                    "Boats and water rescue equipment",
                    "Sandbags and barriers",
                    "Pumps for water removal",
                ]
            )
        elif disaster_type == "earthquake":
            resources.extend(
                ["Structural engineers", "Heavy lifting equipment", "Debris removal machinery"]
            )
        elif disaster_type == "wildfire":
            resources.extend(
                [
                    "Firefighting aircraft",
                    "PPE for smoke protection",
                    "Respirators for affected population",
                ]
            )
        return resources

    def _get_recovery_steps(self, phase: str) -> list[str]:
        return [
            "Conduct damage assessments and document for aid",
            "Prioritize rebuilding of critical infrastructure",
            "Provide financial assistance to affected individuals",
            "Implement disaster-resistant building codes",
            "Establish long-term community recovery programs",
        ]

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        has_population = bool(params.get("population_estimate", 0))
        has_region = bool(params.get("region", ""))
        score = 0.5
        if has_region:
            score += 0.15
        if has_population:
            score += 0.15
        return ConfidenceScore(
            ConfidenceRating.HIGH if score > 0.65 else ConfidenceRating.MEDIUM,
            round(score, 2),
            f"Assessment based on disaster type and {' '.join(['region' if has_region else '', 'population data' if has_population else ''])}",
        )
