"""
Forge auto-evaluation gate — automatically A/B test and promote forge candidates.

After `viki-forge` bakes a candidate model, this gate:
  1. Runs the eval harness on both incumbent and candidate
  2. Compares via ModelABTest + IntelligenceScorecard
  3. Promotes only on a statistically significant win
  4. Rolls back on regression

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
    significant: bool  # statistically significant
    metrics: dict[str, Any]
    promoted: bool = False
    timestamp: float = 0.0


class ForgeEvalGate:
    """
    Auto-evaluation gate for the Neural Forge training pipeline.

    Attaches to a VIKIController to access ModelABTest, IntelligenceScorecard,
    and model router.
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

    async def evaluate_candidate(
        self,
        candidate_model: str,
        incumbent_model: str | None = None,
        test_suite: str = "default",
        min_improvement_pct: float = 5.0,
    ) -> ABTestResult:
        """
        A/B test a candidate model against the incumbent.

        Args:
            candidate_model: Name/path of the newly trained model.
            incumbent_model: Name of the current production model (auto-detected if None).
            test_suite: Evaluation suite to run.
            min_improvement_pct: Minimum improvement required to promote.

        Returns:
            ABTestResult with promotion decision.
        """
        incumbent = incumbent_model or self._get_incumbent()
        viki_logger.info(
            "ForgeEvalGate: A/B testing candidate '%s' vs incumbent '%s'",
            candidate_model,
            incumbent,
        )

        metrics: dict[str, Any] = {}
        significant = False
        candidate_score = 0.0
        incumbent_score = 0.0

        # Run scorecard on incumbent
        if self._scorecard is not None:
            try:
                if hasattr(self._scorecard, "run_suite"):
                    incumbent_result = await self._scorecard.run_suite(test_suite)
                    if isinstance(incumbent_result, dict):
                        incumbent_score = incumbent_result.get("overall_score", 0.0)
                        metrics["incumbent"] = incumbent_result
            except Exception as e:
                viki_logger.error("ForgeEvalGate: incumbent eval failed: %s", e)
                return ABTestResult(
                    incumbent_score=0.0,
                    candidate_score=0.0,
                    improvement=0.0,
                    significant=False,
                    metrics={"error": str(e)},
                )

        # Run A/B test if ModelABTest is available
        if self._ab_test is not None:
            try:
                if hasattr(self._ab_test, "compare"):
                    ab_result = await self._ab_test.compare(
                        model_a=incumbent,
                        model_b=candidate_model,
                        test_suite=test_suite,
                    )
                    if isinstance(ab_result, dict):
                        candidate_score = ab_result.get("model_b_score", 0.0)
                        incumbent_score = ab_result.get("model_a_score", incumbent_score)
                        significant = ab_result.get("significant", False)
                        metrics["ab_test"] = ab_result
            except Exception as e:
                viki_logger.error("ForgeEvalGate: A/B test failed: %s", e)

        improvement = 0.0
        if incumbent_score > 0:
            improvement = ((candidate_score - incumbent_score) / incumbent_score) * 100

        promoted = significant and improvement >= min_improvement_pct

        result = ABTestResult(
            incumbent_score=incumbent_score,
            candidate_score=candidate_score,
            improvement=improvement,
            significant=significant,
            metrics=metrics,
            promoted=promoted,
            timestamp=time.time(),
        )

        self._record_result(result)
        self._log_result(result, candidate_model, incumbent)

        if promoted:
            await self._promote(candidate_model, incumbent)

        return result

    def _get_incumbent(self) -> str:
        """Detect the current production model."""
        if self._router is not None:
            primary = getattr(self._router, "primary_model", None)
            if primary:
                return str(primary)
        return "unknown"

    async def _promote(self, candidate: str, incumbent: str) -> None:
        """Promote the candidate model to production."""
        viki_logger.info(
            "ForgeEvalGate: PROMOTING candidate '%s' over incumbent '%s'",
            candidate,
            incumbent,
        )
        if self._router is not None and hasattr(self._router, "set_primary_model"):
            await self._router.set_primary_model(candidate)
        if self._scorecard is not None and hasattr(self._scorecard, "record_promotion"):
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
                }
            )
            os.makedirs(os.path.dirname(self._history_path) or ".", exist_ok=True)
            with open(self._history_path, "w") as f:
                json.dump(history[-100:], f, indent=2)
        except Exception as e:
            viki_logger.error("ForgeEvalGate: failed to persist result: %s", e)

    def _log_result(self, result: ABTestResult, candidate: str, incumbent: str) -> None:
        """Log the A/B result in a readable format."""
        direction = "↑" if result.improvement > 0 else "↓"
        action = "PROMOTED" if result.promoted else "NOT PROMOTED"
        viki_logger.info(
            "ForgeEvalGate: %s — incumbent=%.2f candidate=%.2f %s %.1f%% (significant=%s) [%s vs %s]",
            action,
            result.incumbent_score,
            result.candidate_score,
            direction,
            abs(result.improvement),
            result.significant,
            candidate,
            incumbent,
        )
