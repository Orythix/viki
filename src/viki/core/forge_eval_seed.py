"""
Seed CapabilityIndex results after a forge bake.

Runs the pinned ModelABTest suite against candidate (and optionally incumbent),
writes jsonl under ``data/eval_results/forge_pinned/`` so CapabilityIndex has
real rows before ForgeEvalGate decides promotion.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from viki.config.logger import viki_logger


async def seed_pinned_eval_results(
    controller: Any,
    candidate_model: str,
    incumbent_model: str | None = None,
    suite: str = "forge_pinned",
) -> dict[str, Any]:
    """
    Execute pinned eval prompts and persist CapabilityIndex-compatible jsonl.

    Returns a summary with paths and mean scores.
    """
    data_dir = (getattr(controller, "settings", None) or {}).get("system", {}).get(
        "data_dir", "./data"
    )
    results_root = os.path.join(data_dir, "eval_results")
    suite_dir = os.path.join(results_root, suite)
    os.makedirs(suite_dir, exist_ok=True)

    ab = getattr(controller, "model_ab_test", None) or getattr(controller, "ab_tester", None)
    if ab is None:
        from viki.core.variant_optimizer import ModelABTest

        ab = ModelABTest(controller)
        try:
            controller.model_ab_test = ab
        except Exception:
            pass

    models = [candidate_model]
    if incumbent_model and incumbent_model not in ("unknown", candidate_model):
        models.append(incumbent_model)

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_path = os.path.join(suite_dir, f"{run_id}.jsonl")
    summaries: dict[str, float] = {}

    with open(out_path, "w", encoding="utf-8") as f:
        for model_name in models:
            meta = {
                "__metadata__": True,
                "suite": suite,
                "model": model_name,
                "model_profile": model_name,
                "air_gap": True,
                "run_id": run_id,
                "source": "forge_pinned",
            }
            f.write(json.dumps(meta) + "\n")

            model = None
            try:
                model = controller.model_router.models.get(model_name)
            except Exception:
                model = None

            scores: list[float] = []
            prompts = list(getattr(ab, "test_prompts", []) or [])
            if not prompts:
                from viki.core.variant_optimizer import _PINNED_EVAL_PROMPTS

                prompts = list(_PINNED_EVAL_PROMPTS)

            for case in prompts:
                score = 0.0
                passed = False
                if model is not None and hasattr(ab, "_test_model"):
                    try:
                        response, _lat, err = await ab._test_model(model, case)
                        if not err:
                            score = float(ab._score_response(case, response))
                            passed = score >= 0.5
                    except Exception as e:
                        viki_logger.debug("forge seed eval case failed: %s", e)
                # Even without a live model, write a row so the index has structure.
                row = {
                    "task_id": case.get("id") or case.get("category") or "case",
                    "score": score,
                    "passed": passed,
                    "model": model_name,
                    "category": case.get("category"),
                }
                f.write(json.dumps(row) + "\n")
                scores.append(score)

            summaries[model_name] = (sum(scores) / len(scores)) if scores else 0.0

    # Refresh capability index artifact.
    index_payload: dict[str, Any] = {}
    try:
        from viki.core.capability_index import CapabilityIndex

        index_payload = CapabilityIndex(results_root).compute()
        index_path = os.path.join(results_root, "capability_index.json")
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump({"index": index_payload, "seeded_by": "forge_pinned"}, f, indent=2)
    except Exception as e:
        viki_logger.debug("forge seed: capability index compute failed: %s", e)

    return {
        "path": out_path,
        "suite": suite,
        "scores": summaries,
        "capability_index": index_payload.get("capability_index"),
    }
