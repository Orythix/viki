"""
A/B Testing Framework for Model Comparison.

Primary signal: CapabilityIndex over eval harness results (HumanEval+ / SWE /
GAIA adapters under ``scripts/evals`` / ``viki.eval``).

Fallback: a small pinned coding/reasoning subset scored by ExecutionEvaluator
(or structured checks) — never toy keyword quizzes like "2+2".
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from viki.config.logger import viki_logger


# Pinned local-friendly subset used when no CapabilityIndex results exist yet.
_PINNED_EVAL_PROMPTS: list[dict[str, Any]] = [
    {
        "id": "factorial",
        "prompt": (
            "Write a Python function `factorial(n)` that returns n!. "
            "Include only the function in a ```python``` block."
        ),
        "category": "coding",
        "test_code": (
            "def check(candidate):\n"
            "    assert candidate(0) == 1\n"
            "    assert candidate(5) == 120\n"
            "    assert candidate(1) == 1\n"
            "check(factorial)\n"
        ),
    },
    {
        "id": "is_palindrome",
        "prompt": (
            "Write a Python function `is_palindrome(s: str) -> bool` that returns True "
            "iff s reads the same forwards and backwards (case-sensitive). "
            "Include only the function in a ```python``` block."
        ),
        "category": "coding",
        "test_code": (
            "def check(candidate):\n"
            "    assert candidate('aba') is True\n"
            "    assert candidate('ab') is False\n"
            "    assert candidate('') is True\n"
            "check(is_palindrome)\n"
        ),
    },
    {
        "id": "sum_list",
        "prompt": (
            "Write a Python function `sum_list(xs)` that returns the sum of numbers in xs. "
            "Include only the function in a ```python``` block."
        ),
        "category": "coding",
        "test_code": (
            "def check(candidate):\n"
            "    assert candidate([1, 2, 3]) == 6\n"
            "    assert candidate([]) == 0\n"
            "check(sum_list)\n"
        ),
    },
    {
        "id": "fizzbuzz_spec",
        "prompt": (
            "In one short paragraph, explain the FizzBuzz problem and the correct "
            "rules for multiples of 3, 5, and 15."
        ),
        "category": "reasoning",
        "must_contain_any": ["3", "5", "fizz", "buzz"],
    },
]


class ModelABTest:
    """A/B test new models against current model via CapabilityIndex + pinned evals."""

    def __init__(self, controller):
        self.controller = controller
        self.test_prompts = list(_PINNED_EVAL_PROMPTS)

    def _results_root(self) -> str:
        settings = getattr(self.controller, "settings", None) or {}
        data_dir = (settings.get("system") or {}).get("data_dir", "./data")
        return os.path.join(data_dir, "eval_results")

    def _capability_score(self, model_name: str) -> float | None:
        try:
            from viki.core.capability_index import CapabilityIndex

            root = self._results_root()
            if not os.path.isdir(root):
                return None
            snap = CapabilityIndex(root, model_filter=model_name).compute()
            if not snap or not snap.get("suites"):
                return None
            return float(snap.get("capability_index", 0.0))
        except Exception as e:
            viki_logger.debug("ModelABTest: capability index failed for %s: %s", model_name, e)
            return None

    async def compare_models(self, model_a_name: str, model_b_name: str) -> dict[str, Any]:
        """Compare two models; prefer CapabilityIndex, else pinned ExecutionEvaluator suite."""
        viki_logger.info("A/B Test: Comparing %s vs %s", model_a_name, model_b_name)

        score_a = self._capability_score(model_a_name)
        score_b = self._capability_score(model_b_name)
        if score_a is not None and score_b is not None:
            delta = score_b - score_a
            significant = abs(delta) >= 0.01  # meaningful index movement
            winner = model_a_name if score_a >= score_b else model_b_name
            return {
                "model_a": {"name": model_a_name, "avg_score": score_a, "source": "capability_index"},
                "model_b": {"name": model_b_name, "avg_score": score_b, "source": "capability_index"},
                "model_a_score": score_a,
                "model_b_score": score_b,
                "winner": winner,
                "score_difference": abs(delta),
                "significant": significant,
                "source": "capability_index",
                "test_count": 0,
            }

        return await self._compare_pinned(model_a_name, model_b_name)

    async def compare(
        self,
        model_a: str,
        model_b: str,
        test_suite: str = "default",
    ) -> dict[str, Any]:
        """Alias used by ForgeEvalGate."""
        _ = test_suite
        return await self.compare_models(model_a, model_b)

    async def _compare_pinned(self, model_a_name: str, model_b_name: str) -> dict[str, Any]:
        model_a = self.controller.model_router.models.get(model_a_name)
        model_b = self.controller.model_router.models.get(model_b_name)
        if not model_a:
            return {"error": f"Model {model_a_name} not found"}
        if not model_b:
            return {"error": f"Model {model_b_name} not found"}

        test_count = len(self.test_prompts)
        results: dict[str, Any] = {
            "model_a": {"name": model_a_name, "scores": [], "latencies": [], "errors": 0},
            "model_b": {"name": model_b_name, "scores": [], "latencies": [], "errors": 0},
            "test_count": test_count,
            "source": "pinned_eval",
        }

        for i, test_case in enumerate(self.test_prompts):
            viki_logger.debug("A/B Test: pinned case %s (%d/%d)", test_case.get("id"), i + 1, test_count)
            (response_a, latency_a, error_a), (response_b, latency_b, error_b) = await asyncio.gather(
                self._test_model(model_a, test_case),
                self._test_model(model_b, test_case),
            )
            score_a = self._score_response(test_case, response_a)
            score_b = self._score_response(test_case, response_b)
            results["model_a"]["scores"].append(score_a)
            results["model_a"]["latencies"].append(latency_a)
            if error_a:
                results["model_a"]["errors"] += 1
            results["model_b"]["scores"].append(score_b)
            results["model_b"]["latencies"].append(latency_b)
            if error_b:
                results["model_b"]["errors"] += 1
            await asyncio.sleep(0.05)

        results["model_a"]["avg_score"] = sum(results["model_a"]["scores"]) / test_count
        results["model_a"]["avg_latency"] = sum(results["model_a"]["latencies"]) / test_count
        results["model_b"]["avg_score"] = sum(results["model_b"]["scores"]) / test_count
        results["model_b"]["avg_latency"] = sum(results["model_b"]["latencies"]) / test_count

        score_a_weighted = (
            results["model_a"]["avg_score"] * 0.7
            - (results["model_a"]["avg_latency"] / 10.0) * 0.3
        )
        score_b_weighted = (
            results["model_b"]["avg_score"] * 0.7
            - (results["model_b"]["avg_latency"] / 10.0) * 0.3
        )
        results["winner"] = model_a_name if score_a_weighted >= score_b_weighted else model_b_name
        results["score_difference"] = abs(score_a_weighted - score_b_weighted)
        results["model_a_score"] = results["model_a"]["avg_score"]
        results["model_b_score"] = results["model_b"]["avg_score"]
        results["significant"] = results["score_difference"] >= 0.05

        viki_logger.info(
            "A/B Test Complete (pinned): Winner=%s A=%.2f B=%.2f",
            results["winner"],
            results["model_a"]["avg_score"],
            results["model_b"]["avg_score"],
        )
        return results

    async def _test_model(self, model: Any, test_case: dict) -> tuple:
        prompt = test_case["prompt"]
        messages = [
            {"role": "system", "content": "You are VIKI, a helpful AI assistant."},
            {"role": "user", "content": prompt},
        ]
        try:
            start_time = time.perf_counter()
            if hasattr(model, "chat"):
                response = await model.chat(messages, temperature=0.2)
            else:
                return "", 0.0, True
            return response, time.perf_counter() - start_time, False
        except Exception as e:
            viki_logger.warning("Model test failed: %s", e)
            return "", 0.0, True

    def _score_response(self, test_case: dict, response: str) -> float:
        if not response:
            return 0.0
        if test_case.get("test_code"):
            try:
                from viki.core.evaluators import ExecutionEvaluator

                scored = ExecutionEvaluator().evaluate(
                    {
                        "test_code": test_case["test_code"],
                        "language": "python",
                        "timeout": 5,
                    },
                    response,
                )
                return float(scored.score)
            except Exception as e:
                viki_logger.debug("pinned ExecutionEvaluator failed: %s", e)
                return 0.0
        must_any = test_case.get("must_contain_any") or []
        if must_any:
            lower = response.lower()
            hits = sum(1 for tok in must_any if tok.lower() in lower)
            return hits / len(must_any)
        return 0.0

    def load_custom_test_prompts(self, prompts: list[dict[str, Any]]):
        self.test_prompts = prompts
        viki_logger.info("Loaded %d custom test prompts", len(prompts))

    async def quick_validation(self, model_name: str) -> dict[str, Any]:
        ci = self._capability_score(model_name)
        if ci is not None:
            return {
                "model": model_name,
                "avg_score": ci,
                "source": "capability_index",
                "passed": ci > 0.0,
                "scores": [ci],
                "latencies": [],
                "errors": 0,
            }

        model = self.controller.model_router.models.get(model_name)
        if not model:
            return {"error": f"Model {model_name} not found"}

        subset = self.test_prompts[:3]
        scores: list[float] = []
        latencies: list[float] = []
        errors = 0
        for test_case in subset:
            response, latency, error = await self._test_model(model, test_case)
            scores.append(self._score_response(test_case, response))
            latencies.append(latency)
            if error:
                errors += 1
        avg = sum(scores) / len(scores) if scores else 0.0
        return {
            "model": model_name,
            "scores": scores,
            "latencies": latencies,
            "errors": errors,
            "avg_score": avg,
            "avg_latency": sum(latencies) / len(latencies) if latencies else 0.0,
            "passed": avg > 0.5 and errors == 0,
            "source": "pinned_eval",
        }
