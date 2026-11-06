"""
Forge auto-evaluation gate — A/B test and promote forge candidates.

After `viki-forge` bakes a candidate model, this gate:
  1. Scores incumbent + candidate via CapabilityIndex (preferred) or ModelABTest
  2. Promotes only on a measured win (index delta > 0 and above min improvement)
  3. Rolls back / refuses when delta <= 0

This makes self-improvement safe and measurable — the whole thesis rests
on this loop being closed.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from viki.config.logger import viki_logger


@dataclass
class ABTestResult:
    """Result of an A/B comparison between incumbent and candidate models."""

    incumbent_score: float
    candidate_score: float
    improvement: float  # percentage change
    significant: bool  # statistically significant / meaningful delta
    metrics: dict[str, Any]
    promoted: bool = False
    timestamp: float = 0.0
    trace_id: str | None = None


class ForgeEvalGate:
    """
    Auto-evaluation gate for the Neural Forge training pipeline.

    Attaches to a VIKIController to access ModelABTest, IntelligenceScorecard,
    CapabilityIndex, and model router.
    """

    def __init__(self, controller: Any):
        self._controller = controller
        self._scorecard = getattr(controller, "scorecard", None)
        self._ab_test = getattr(controller, "model_ab_test", None)
        self._router = getattr(controller, "model_router", None)
        self._history_path = os.path.join(
            getattr(controller, "system_settings", {}).get("data_dir", "./data"),
            "forge_eval_history.json",
        )

    def _data_dir(self) -> str:
        settings = getattr(self._controller, "settings", None) or {}
        return (settings.get("system") or {}).get("data_dir", "./data")

    def _capability_score(self, model_name: str) -> float | None:
        try:
            from viki.core.capability_index import CapabilityIndex

            root = os.path.join(self._data_dir(), "eval_results")
            if not os.path.isdir(root):
                return None
            snap = CapabilityIndex(root, model_filter=model_name).compute()
            if not snap or not snap.get("suites"):
                return None
            return float(snap.get("capability_index", 0.0))
        except Exception as e:
            viki_logger.debug("ForgeEvalGate: capability index failed: %s", e)
            return None

    async def evaluate_candidate(
        self,
        candidate_model: str,
        incumbent_model: str | None = None,
        test_suite: str = "default",
        min_improvement_pct: float = 5.0,
    ) -> ABTestResult:
        """
        A/B test a candidate model against the incumbent.

        Promotion requires candidate CapabilityIndex (or pinned A/B score) to beat
        the incumbent by a positive delta; delta <= 0 never promotes.
        """
        from viki.core.telemetry_service import start_span

        incumbent = incumbent_model or self._get_incumbent()
        viki_logger.info(
            "ForgeEvalGate: A/B testing candidate '%s' vs incumbent '%s'",
            candidate_model,
            incumbent,
        )

        metrics: dict[str, Any] = {"test_suite": test_suite}
        significant = False
        candidate_score = 0.0
        incumbent_score = 0.0
        trace_id: str | None = None

        with start_span(
            "forge.eval_gate",
            attributes={"candidate": candidate_model, "incumbent": incumbent},
        ) as span:
            trace_id = span.get("trace_id")

            # Prefer CapabilityIndex for both models.
            ci_inc = self._capability_score(incumbent) if incumbent != "unknown" else None
            ci_cand = self._capability_score(candidate_model)
            if ci_inc is not None and ci_cand is not None:
                incumbent_score = ci_inc
                candidate_score = ci_cand
                metrics["source"] = "capability_index"
                metrics["incumbent_index"] = ci_inc
                metrics["candidate_index"] = ci_cand
                significant = abs(candidate_score - incumbent_score) >= 0.01
            elif self._ab_test is not None:
                try:
                    if hasattr(self._ab_test, "compare"):
                        ab_result = await self._ab_test.compare(
                            model_a=incumbent,
                            model_b=candidate_model,
                            test_suite=test_suite,
                        )
                    else:
                        ab_result = await self._ab_test.compare_models(
                            incumbent, candidate_model
                        )
                    if isinstance(ab_result, dict) and not ab_result.get("error"):
                        candidate_score = float(
                            ab_result.get("model_b_score")
                            or ab_result.get("model_b", {}).get("avg_score", 0.0)
                        )
                        incumbent_score = float(
                            ab_result.get("model_a_score")
                            or ab_result.get("model_a", {}).get("avg_score", incumbent_score)
                        )
                        significant = bool(ab_result.get("significant", False))
                        metrics["ab_test"] = ab_result
                        metrics["source"] = ab_result.get("source", "ab_test")
                except Exception as e:
                    viki_logger.error("ForgeEvalGate: A/B test failed: %s", e)
                    metrics["error"] = str(e)

            # Absolute rule: never promote on non-positive delta.
            delta = candidate_score - incumbent_score
            improvement = 0.0
            if incumbent_score > 0:
                improvement = (delta / incumbent_score) * 100
            elif candidate_score > 0 and incumbent_score == 0:
                improvement = 100.0

            promoted = bool(significant and delta > 0 and improvement >= min_improvement_pct)
            if delta <= 0:
                promoted = False
                metrics["refuse_reason"] = "non_positive_capability_delta"

            span["attributes"]["incumbent_score"] = incumbent_score
            span["attributes"]["candidate_score"] = candidate_score
            span["attributes"]["delta"] = delta
            span["attributes"]["promoted"] = promoted
            span["attributes"]["verifier_score"] = candidate_score

            result = ABTestResult(
                incumbent_score=incumbent_score,
                candidate_score=candidate_score,
                improvement=improvement,
                significant=significant,
                metrics=metrics,
                promoted=promoted,
                timestamp=time.time(),
                trace_id=trace_id,
            )

            self._record_result(result)
            self._log_result(result, candidate_model, incumbent)

            if self._scorecard is not None and hasattr(self._scorecard, "record_event"):
                try:
                    self._scorecard.record_event(
                        "forge_eval",
                        {
                            "candidate": candidate_model,
                            "incumbent": incumbent,
                            "promoted": promoted,
                            "delta": delta,
                            "trace_id": trace_id,
                        },
                    )
                except Exception:
                    pass

            if promoted:
                await self._promote(candidate_model, incumbent)
            else:
                viki_logger.info(
                    "ForgeEvalGate: refusing promotion (delta=%.4f, improvement=%.1f%%)",
                    delta,
                    improvement,
                )

            return result

    def _get_incumbent(self) -> str:
        """Detect the current production model."""
        if self._router is not None:
            primary = getattr(self._router, "primary_model", None)
            if primary:
                return str(primary)
        try:
            models_cfg = getattr(self._controller, "models_config", None) or {}
            default = (models_cfg.get("models") or {}).get("default")
            if default:
                return str(default)
        except Exception:
            pass
        return "unknown"

    async def _promote(self, candidate: str, incumbent: str) -> None:
        """Promote the candidate model to production."""
        viki_logger.info(
            "ForgeEvalGate: PROMOTING candidate '%s' over incumbent '%s'",
            candidate,
            incumbent,
        )
        if self._router is not None and hasattr(self._router, "set_primary_model"):
            maybe = self._router.set_primary_model(candidate)
            if hasattr(maybe, "__await__"):
                await maybe
        if self._scorecard is not None and hasattr(self._scorecard, "record_promotion"):
            # trace_id may be set on the last evaluate_candidate result via metrics
            self._scorecard.record_promotion(candidate, incumbent)

    def _record_result(self, result: ABTestResult) -> None:
        """Persist the eval result to history."""
        try:
            history: list[dict] = []
            if os.path.exists(self._history_path):
                with open(self._history_path) as f:
                    history = json.load(f)
            history.append(
                {
                    "incumbent_score": result.incumbent_score,
                    "candidate_score": result.candidate_score,
                    "improvement": result.improvement,
                    "significant": result.significant,
                    "promoted": result.promoted,
                    "timestamp": result.timestamp,
                    "trace_id": result.trace_id,
                    "metrics": {
                        k: result.metrics[k]
                        for k in ("source", "refuse_reason")
                        if k in result.metrics
                    },
                }
            )
            os.makedirs(os.path.dirname(self._history_path) or ".", exist_ok=True)
            with open(self._history_path, "w") as f:
                json.dump(history[-100:], f, indent=2)
        except Exception as e:
            viki_logger.error("ForgeEvalGate: failed to persist result: %s", e)

    def _log_result(self, result: ABTestResult, candidate: str, incumbent: str) -> None:
        """Log the A/B result in a readable format."""
        direction = "up" if result.improvement > 0 else "down"
        action = "PROMOTED" if result.promoted else "NOT PROMOTED"
        viki_logger.info(
            "ForgeEvalGate: %s — incumbent=%.2f candidate=%.2f %s %.1f%% "
            "(significant=%s) [%s vs %s] trace=%s",
            action,
            result.incumbent_score,
            result.candidate_score,
            direction,
            abs(result.improvement),
            result.significant,
            candidate,
            incumbent,
            result.trace_id,
        )
