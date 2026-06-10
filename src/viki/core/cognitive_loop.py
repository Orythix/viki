"""
Cognitive routing layer.

Sits between the preflight pipeline (`request_pipeline.py`) and the deliberative
ConsciousnessStack. Wires the previously-dormant ReflexBrain and JudgmentEngine
into the request hot path so each input is dispatched to the cheapest cognitive
mode that can serve it:

    ReflexBrain.think -> JudgmentEngine.evaluate -> route to REFLEX / SHALLOW / DEEP / REFUSE

The router does not execute skills or call models itself. It produces a
`CognitiveRoute` decision that the controller's existing ReAct loop consumes:
- `action_override` short-circuits the cortex when reflex hits.
- `use_lite_schema` makes the controller request the lightweight cortex path.
- `refusal_reason` short-circuits with a safe refusal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from viki.config.logger import viki_logger
from viki.core.output_verifier import JudgmentEngine, JudgmentOutcome, JudgmentResult
from viki.core.schema import ActionCall


@dataclass
class CognitiveRoute:
    """
    Decision produced by `CognitiveRouter.classify` and consumed by the controller.
    """

    outcome: JudgmentOutcome
    judgment: JudgmentResult
    action_override: Optional[ActionCall] = None
    cached_response: Optional[str] = None
    refusal_reason: Optional[str] = None
    use_lite_schema: bool = False
    use_ensemble: bool = True
    model_tier: str = "standard" # "fast" | "standard" | "heavy"
    source: str = "judgment"  # "reflex" | "judgment" | "fallback"
    elapsed_ms: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_short_circuit(self) -> bool:
        """True if controller can skip the cortex entirely."""
        return (
            self.action_override is not None
            or self.cached_response is not None
            or self.refusal_reason is not None
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "source": self.source,
            "use_lite_schema": self.use_lite_schema,
            "use_ensemble": self.use_ensemble,
            "model_tier": self.model_tier,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "judgment": self.judgment.as_dict(),
            "has_action_override": self.action_override is not None,
            "has_cached_response": self.cached_response is not None,
            "refusal_reason": self.refusal_reason,
            "metrics": self.metrics,
        }


class CognitiveRouter:
    """
    Routes preflight-cleared requests across the four cognitive modes.

    The controller calls `classify(...)` once per ReAct iteration's outer pass
    (i.e. before the first cortex call) to decide:
    - whether the reflex layer can answer immediately,
    - whether the request should be refused on safety/ambiguity grounds,
    - whether the cortex should run with the lightweight or full schema.

    The decision is tracked via `RouterTelemetry` so we can measure the reflex
    hit rate against real sessions.
    """

    def __init__(self, reflex_brain, judgment_engine, telemetry=None, data_dir: str = None):
        self.reflex = reflex_brain
        self.judgment = judgment_engine
        self.telemetry = telemetry or RouterTelemetry()
        
        # v26: Semantic Cache
        from core.utils.semantic_cache import SemanticCache
        self.cache = SemanticCache(data_dir=data_dir) if data_dir else None

    async def classify(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        skill_registry: Optional[Any] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> CognitiveRoute:
        from core.telemetry_service import start_span

        t0 = time.perf_counter()
        context = context or {}

        with start_span(
            "cognitive_router.classify",
            attributes={"input.len": len(user_input or "")},
        ) as span_info:
            # 1. Semantic Cache Lookup (Phase 3 Optimization)
            if self.cache:
                cached_data = self.cache.lookup(user_input)
                if cached_data:
                    # Reconstruct VIKIResponse from cache
                    from core.schema import VIKIResponse
                    viki_resp = VIKIResponse(**cached_data)
                    
                    # Mock a judgment for the cached route
                    cached_judgment = JudgmentResult(
                        outcome=JudgmentOutcome.SHALLOW,
                        recommendation="proceed",
                        reason="Retrieved from semantic cache",
                        risk=0.0,
                        clarity=1.0,
                        novelty=0.0,
                        complexity_score=0.1
                    )
                    
                    route = CognitiveRoute(
                        outcome=JudgmentOutcome.SHALLOW,
                        judgment=cached_judgment,
                        cached_response=viki_resp.final_response,
                        source="cache",
                        model_tier="fast"
                    )
                    self._finalize(route, t0)
                    return route

            # 2. Reflex Search (Cheapest path)
            reflex_response, reflex_action = self._run_reflex(user_input)
            judgment = await self.judgment.evaluate(user_input, context, history=history)

            route = self._route_from_reflex(
                reflex_action, reflex_response, judgment, skill_registry
            )
            if route is None:
                route = self._route_from_judgment(judgment)

            self._finalize(route, t0)
            span_info["attributes"]["route.outcome"] = route.outcome.value
            span_info["attributes"]["route.source"] = route.source
            return route

    def _run_reflex(self, user_input: str) -> tuple:
        if self.reflex is None:
            return None, None
        try:
            return self.reflex.think(user_input)
        except Exception as e:
            viki_logger.debug("CognitiveRouter: reflex failed: %s", e)
            return None, None

    def _route_from_reflex(
        self,
        reflex_action: Optional[ActionCall],
        reflex_response: Optional[str],
        judgment: JudgmentResult,
        skill_registry: Optional[Any],
    ) -> Optional[CognitiveRoute]:
        if reflex_action is not None and self._reflex_action_safe(reflex_action, judgment, skill_registry):
            return CognitiveRoute(
                outcome=JudgmentOutcome.REFLEX,
                judgment=judgment,
                action_override=reflex_action,
                use_lite_schema=False,
                use_ensemble=False,
                model_tier="fast",
                source="reflex",
            )
        if reflex_response is not None:
            return CognitiveRoute(
                outcome=JudgmentOutcome.REFLEX,
                judgment=judgment,
                cached_response=reflex_response,
                use_lite_schema=False,
                use_ensemble=False,
                model_tier="fast",
                source="reflex",
            )
        return None

    def _reflex_action_safe(
        self,
        action: ActionCall,
        judgment: JudgmentResult,
        skill_registry: Optional[Any],
    ) -> bool:
        if judgment.outcome == JudgmentOutcome.REFUSE:
            return False
        if skill_registry is None:
            return True
        return skill_registry.get_skill(action.skill_name) is not None

    def _route_from_judgment(self, judgment: JudgmentResult) -> CognitiveRoute:
        complexity = judgment.complexity_score
        outcome = judgment.outcome

        if outcome == JudgmentOutcome.REFUSE:
            return CognitiveRoute(
                outcome=outcome,
                judgment=judgment,
                refusal_reason=judgment.reason,
                source="judgment",
            )
        
        # v26: Tiered Routing Logic
        if complexity < 0.3:
            # Fast Lane: Minimal novelty/risk.
            return CognitiveRoute(
                outcome=JudgmentOutcome.SHALLOW,
                judgment=judgment,
                use_lite_schema=True,
                use_ensemble=False,
                model_tier="fast",
                source="judgment",
            )
        
        if complexity <= 0.8:
            # Standard Lane: Typical coding/reasoning.
            return CognitiveRoute(
                outcome=JudgmentOutcome.DEEP,
                judgment=judgment,
                use_lite_schema=False,
                use_ensemble=False,
                model_tier="standard",
                source="judgment",
            )

        # Deep Lane: Complex, novel, or risky.
        return CognitiveRoute(
            outcome=JudgmentOutcome.DEEP,
            judgment=judgment,
            use_lite_schema=False,
            use_ensemble=True,
            model_tier="heavy",
            source="judgment",
        )

    def _finalize(self, route: CognitiveRoute, t0: float) -> None:
        route.elapsed_ms = (time.perf_counter() - t0) * 1000.0
        try:
            self.telemetry.record(route)
        except Exception as e:
            viki_logger.debug("CognitiveRouter: telemetry record failed: %s", e)
        viki_logger.info(
            "CognitiveRouter -> %s (source=%s, lite=%s, %.1fms): %s",
            route.outcome.value,
            route.source,
            route.use_lite_schema,
            route.elapsed_ms,
            route.judgment.reason,
        )

    def store_response(self, user_input: str, response: Any):
        """Store a completed response in the semantic cache."""
        if self.cache:
            self.cache.store(user_input, response)


class RouterTelemetry:
    """
    Tracks per-outcome counts and reflex hit rate. Backed by an in-memory
    counter; persistence can be wired by a higher layer if needed.
    """

    def __init__(self):
        self.totals: Dict[str, int] = {o.value: 0 for o in JudgmentOutcome}
        self.reflex_hits: int = 0
        self.fallback_count: int = 0
        self._total = 0
        self._reflex_attempts = 0

    def record(self, route: CognitiveRoute) -> None:
        self._total += 1
        self.totals[route.outcome.value] += 1
        if route.source == "reflex" and (route.action_override or route.cached_response):
            self.reflex_hits += 1
        self._reflex_attempts += 1

    @property
    def total(self) -> int:
        return self._total

    @property
    def reflex_hit_rate(self) -> float:
        if self._reflex_attempts == 0:
            return 0.0
        return self.reflex_hits / self._reflex_attempts

    def snapshot(self) -> Dict[str, Any]:
        return {
            "total": self._total,
            "reflex_hits": self.reflex_hits,
            "reflex_hit_rate": round(self.reflex_hit_rate, 4),
            "by_outcome": dict(self.totals),
        }
