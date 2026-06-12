"""Layer 5: Process Optimization, Timing Analysis & Auto-Learn."""

from __future__ import annotations

from viki.config.logger import viki_logger
from viki.core.schema import VIKIResponse

from .cortex_layer import CortexLayer
from .layer_timing import LayerTiming
from .pattern_tracker import PatternTracker


class MetaCognitionLayer(CortexLayer):
    """Layer 5: Process Optimization, Timing Analysis & Auto-Learn."""

    def __init__(
        self,
        name: str,
        description: str,
        layer_timing: LayerTiming = None,
        pattern_tracker: PatternTracker = None,
    ):
        super().__init__(name, description)
        self.layer_timing = layer_timing
        self.pattern_tracker = pattern_tracker or PatternTracker()
        self._confidence_history: list[float] = []

    async def _logic(self, response: VIKIResponse) -> VIKIResponse:  # NOSONAR
        viki_logger.debug("Layer 5 (Meta-Cognition) evaluating mental efficiency...")

        insights = []
        confidence = response.final_thought.confidence
        has_action = response.action is not None
        has_response = bool(response.final_response and response.final_response.strip())

        self._confidence_history.append(confidence)
        if len(self._confidence_history) > 30:
            self._confidence_history.pop(0)

        if len(self._confidence_history) >= 5:
            recent = self._confidence_history[-5:]
            avg_recent = sum(recent) / len(recent)
            if avg_recent < 0.4:
                insights.append("Confidence trending low — consider switching to a stronger model")
            elif avg_recent > 0.85:
                insights.append("Consistently high confidence — REFLEX caching opportunity")

        if response.sentiment == "frustrated" or response.intent_type == "correction":
            viki_logger.warning(
                "Meta-Cognition: User frustration or correction detected. Intensifying reasoning."
            )
            insights.append(
                "FRUSTRATION SIGNAL: User provides correction or expresses frustration."
            )
            response.needs_escalation = True
            response.final_thought.confidence *= 0.8

        if self.layer_timing:
            total_time = self.layer_timing.get_total_current()
            slowest_name, slowest_time = self.layer_timing.get_slowest()

            if total_time > 5.0:
                insights.append(
                    f"Slow cycle ({total_time:.1f}s) — bottleneck: {slowest_name} ({slowest_time:.1f}s)"
                )

            delib_time = self.layer_timing.current_cycle.get("Deliberation", 0)
            if delib_time > 3.0:
                insights.append(
                    f"Deliberation took {delib_time:.1f}s — consider SHALLOW for simple requests"
                )

        if has_action and confidence >= 0.6 and self.pattern_tracker:
            raw_input = getattr(response, "_raw_input", "")
            if not raw_input and isinstance(response, VIKIResponse):
                raw_input = response.__dict__.get("_raw_input", "")

            if raw_input:
                self.pattern_tracker.record_success(
                    raw_input, response.action.skill_name, response.action.parameters, confidence
                )

        if self.pattern_tracker:
            candidates = self.pattern_tracker.get_reflex_candidates()
            if candidates:
                candidate_names = [
                    f"'{c['input']}'->{c['skill']}(x{c['count']})" for c in candidates[:3]
                ]
                insights.append(f"REFLEX candidates: {', '.join(candidate_names)}")

        if has_action and not has_response:
            insights.append("Action without explanation — user may need feedback")
        if not has_action and not has_response:
            insights.append("Empty pipeline output — possible failure")

        existing_meta = response.internal_metacognition or ""
        meta_note = " | ".join(insights) if insights else "Process nominal."
        if existing_meta:
            meta_note = f"{existing_meta} || MetaCog: {meta_note}"
        response.internal_metacognition = meta_note

        return response
