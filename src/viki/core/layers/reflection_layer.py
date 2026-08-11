"""Layer 4: Self-Critique, Validation & Escalation."""

from __future__ import annotations

from viki.config.logger import viki_logger
from viki.core.schema import VIKIResponse

from .cortex_layer import CortexLayer


class ReflectionLayer(CortexLayer):
    """Layer 4: Self-Critique, Validation & Escalation."""

    def __init__(self, name: str, description: str, skill_registry=None):
        super().__init__(name, description)
        self.skill_registry = skill_registry

    async def _logic(self, response: VIKIResponse) -> VIKIResponse:  # NOSONAR
        viki_logger.debug("Layer 4 (Reflection) performing Humanity & Logic audit...")

        issues = []

        if response.action and self.skill_registry:
            skill = self.skill_registry.get_skill(response.action.skill_name)
            if not skill:
                viki_logger.warning(
                    f"Reflection: Tool '{response.action.skill_name}' is a hallucination. Nuking action."
                )
                invalid_name = response.action.skill_name
                response.action = None
                issues.append(f"Invalid tool '{invalid_name}'")
                if response.final_response:
                    response.final_response += (
                        f"\n(Reflection: I realized '{invalid_name}' isn't in my current "
                        f"capabilities, so I've pivoted to a direct answer.)"
                    )

        robotic_markers = [
            "as an ai language model",
            "i am an artificial intelligence",
            "how can i help you today",
            "i don't have personal opinions",
        ]
        if response.final_response:
            resp_lower = response.final_response.lower()
            if any(m in resp_lower for m in robotic_markers):
                viki_logger.warning(
                    "Reflection: Robotic marker detected. Violates Human Agent protocol."
                )
                issues.append("Robotic/Servant tone detected")
                if response.final_thought is not None:
                    response.final_thought.confidence *= 0.5

        passive_markers = ["i will try to", "i think i can", "let me see if"]
        if response.final_response and any(m in resp_lower for m in passive_markers):
            if response.final_thought is not None and response.final_thought.confidence > 0.8:
                viki_logger.info(
                    "Reflection: High confidence but passive language. Encouraging more sovereign tone."
                )
                issues.append("Passive agency — recommend assertive tone")

        if response.final_response:
            hallucination_phrases = [
                "i found your bank",
                "i've scanned your private",
                "according to your medical",
            ]
            for phrase in hallucination_phrases:
                if phrase.lower() in resp_lower:
                    viki_logger.warning(
                        f"Reflection: CRITICAL: Hallucination marker '{phrase}' detected."
                    )
                    issues.append(f"Hallucination: {phrase}")
                    response.needs_escalation = True

        thought_confidence = (
            response.final_thought.confidence if response.final_thought is not None else 0.5
        )
        if thought_confidence < 0.3 or (issues and thought_confidence < 0.6):
            viki_logger.info("Reflection: Escalating to DEEP reasoning due to audit failures.")
            response.needs_escalation = True

        if issues:
            response.internal_metacognition = f"Reflection: {', '.join(issues)}"

        return response
