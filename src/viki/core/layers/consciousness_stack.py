"""The 5-Layer Cognitive Engine with per-layer timing and auto-learn."""

from __future__ import annotations

import time
from typing import Any

from viki.config.logger import viki_logger
from viki.core.schema import VIKIResponse

from .deliberation_layer import DeliberationLayer
from .interpretation_layer import InterpretationLayer
from .layer_timing import LayerTiming
from .meta_cognition_layer import MetaCognitionLayer
from .pattern_tracker import PatternTracker
from .perception_layer import PerceptionLayer
from .reflection_layer import ReflectionLayer


class ConsciousnessStack:
    """The 5-Layer Cognitive Engine with per-layer timing and auto-learn."""

    def __init__(
        self,
        model_router,
        soul_config: dict = None,
        skill_registry=None,
        world_model=None,
        data_dir: str = None,
    ):
        self.skill_registry = skill_registry
        self.layer_timing = LayerTiming()
        self.pattern_tracker = PatternTracker(data_dir=data_dir)

        interpretation = InterpretationLayer("Interpretation", "Intent Resolution")
        interpretation.world_model = world_model

        self.layers = [
            PerceptionLayer("Perception", "Input Normalization"),
            interpretation,
            DeliberationLayer(model_router, soul_config=soul_config, skill_registry=skill_registry),
            ReflectionLayer("Reflection", "Self-Critique", skill_registry=skill_registry),
            MetaCognitionLayer(
                "Meta-Cognition",
                "Process Optimization",
                layer_timing=self.layer_timing,
                pattern_tracker=self.pattern_tracker,
            ),
        ]

    async def process(
        self,
        user_input: str,
        memory_context: dict[str, Any] = None,
        url_context: str = "",
        use_lite_schema: bool = False,
        world_context: str = "",
        signals_context: str = "",
        evolution_log: str = "",
        action_results: list = None,
        use_ensemble: bool = True,
        on_event=None,
        model_tier: str = "standard",
        is_agent_mode: bool = False,
        is_plan_mode: bool = False,
        is_debug_mode: bool = False,
        is_singularity_mode: bool = False,
        execution_started: bool = False,
        on_think=None,
    ) -> VIKIResponse:
        start_time = time.time()
        data = user_input

        self.layer_timing.reset_cycle()

        for layer in self.layers:
            layer_start = time.time()

            if isinstance(layer, InterpretationLayer) and on_think:
                pass

            if isinstance(layer, DeliberationLayer):
                h_mem = memory_context or {}
                if isinstance(data, dict):
                    data["conversation_history"] = h_mem.get("working", [])
                    data["episodic_context"] = h_mem.get("episodic", [])
                    data["semantic_knowledge"] = h_mem.get("semantic", [])
                    data["narrative_wisdom"] = h_mem.get("narrative_wisdom", "")
                    data["narrative_identity"] = h_mem.get("identity", "")
                    data["evolution_log"] = evolution_log
                    data["url_context"] = url_context
                    data["use_lite_schema"] = use_lite_schema
                    data["world_context"] = world_context
                    data["project_instructions"] = h_mem.get("project_instructions", "")
                    data["signals_context"] = signals_context
                    data["action_results"] = action_results or []
                    data["use_ensemble"] = use_ensemble
                    data["model_tier"] = model_tier
                    data["on_event"] = on_event
                    data["is_agent_mode"] = is_agent_mode
                    data["is_plan_mode"] = is_plan_mode
                    data["is_debug_mode"] = is_debug_mode
                    data["is_singularity_mode"] = is_singularity_mode
                    data["execution_started"] = execution_started
                    data["skip_escalation"] = h_mem.get("skip_escalation", False)
                elif isinstance(data, str):
                    data = {
                        "raw_input": data,
                        "conversation_history": h_mem.get("working", []),
                        "episodic_context": h_mem.get("episodic", []),
                        "semantic_knowledge": h_mem.get("semantic", []),
                        "narrative_wisdom": h_mem.get("narrative_wisdom", ""),
                        "narrative_identity": h_mem.get("identity", ""),
                        "evolution_log": evolution_log,
                        "url_context": url_context,
                        "use_lite_schema": use_lite_schema,
                        "world_context": world_context,
                        "project_instructions": h_mem.get("project_instructions", ""),
                        "signals_context": signals_context,
                        "action_results": action_results or [],
                        "use_ensemble": use_ensemble,
                        "model_tier": model_tier,
                        "on_event": on_event,
                        "is_agent_mode": is_agent_mode,
                        "is_plan_mode": is_plan_mode,
                        "is_debug_mode": is_debug_mode,
                        "is_singularity_mode": is_singularity_mode,
                        "execution_started": execution_started,
                    }

            data = await layer.process(data)

            if on_think:
                try:
                    layer_name = layer.state.name
                    if layer_name == "Interpretation" and isinstance(data, dict):
                        on_think(
                            "interpretation",
                            {
                                "intent": data.get("intent_type", "unknown"),
                                "sentiment": data.get("sentiment", "neutral"),
                                "capabilities": data.get("recommended_capabilities", []),
                            },
                        )
                    elif layer_name == "Deliberation" and isinstance(data, VIKIResponse):
                        model_name = (
                            data.metadata.get("model", "unknown") if data.metadata else "unknown"
                        )
                        on_think(
                            "deliberation",
                            {
                                "model": model_name,
                                "tier": model_tier,
                                "has_action": bool(data.action),
                            },
                        )
                    elif layer_name == "Execution" and isinstance(data, VIKIResponse):
                        if data.action:
                            on_think(
                                "execution",
                                {
                                    "tool": data.action.skill_name,
                                    "params": str(data.action.parameters)[:80],
                                },
                            )
                except Exception:
                    pass

            layer_duration = time.time() - layer_start
            self.layer_timing.record(layer.state.name, layer_duration)

            if isinstance(data, VIKIResponse):
                data._raw_input = user_input

        elapsed = time.time() - start_time
        viki_logger.info(f"Consciousness Cycle Complete in {elapsed:.2f}s")

        for name, duration in self.layer_timing.current_cycle.items():
            viki_logger.debug(f"  Layer '{name}': {duration:.3f}s")

        return data

    def get_reflex_candidates(self) -> list[dict[str, Any]]:
        return self.pattern_tracker.get_reflex_candidates()
