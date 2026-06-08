"""
Common harness for VIKI eval runners.

Each suite defines:
- `load_tasks(path) -> List[dict]`
- `evaluator_for(task) -> ExecutionEvaluator | LLMJudgeEvaluator`

The harness drives `controller.process_request(task["prompt"])`, scores the
answer, and writes one JSONL per run to `data/eval_results/<suite>/<run_id>.jsonl`.

A `__metadata__` first line in the result file captures run-level info
(air_gap flag, total tasks, model defaults, controller persona).

Designed so the user can run a subset (`--limit 10`) for fast PR-time
sanity checks and the full suite weekly with cloud allowed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Local-first import path for ad-hoc invocations.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.logger import viki_logger  # noqa: E402
from core.evaluators import EvalScore, ExecutionEvaluator, LLMJudgeEvaluator  # noqa: E402


@dataclass
class HarnessConfig:
    suite: str
    tasks_path: str
    results_root: str
    limit: Optional[int] = None
    air_gap: bool = False
    use_llm_judge: bool = True
    persona: Optional[str] = None
    timeout: int = 60


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _active_model_identity(controller) -> Dict[str, Optional[str]]:
    """
    Best-effort identity for the model under evaluation.

    The router stores models by profile key (e.g. `gemma4`) while providers
    expose an engine/tag (e.g. `gemma4:latest`). Persist both so promotion can
    compare candidates against baselines instead of reading unscoped eval files.
    """
    model_profile: Optional[str] = None
    model_name: Optional[str] = None
    try:
        model_profile = (
            ((getattr(controller, "models_config", {}) or {}).get("models") or {}).get("default")
        )
    except Exception:
        model_profile = None
    try:
        router = getattr(controller, "model_router", None)
        default_model = getattr(router, "default_model", None)
        model_name = getattr(default_model, "model_name", None)
        if router is not None and default_model is not None and not model_profile:
            for profile, model in getattr(router, "models", {}).items():
                if model is default_model:
                    model_profile = profile
                    break
    except Exception:
        model_name = None
    return {
        "model_profile": model_profile,
        "model_name": model_name,
        "model_label": model_profile or model_name,
    }


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.isfile(path):
        viki_logger.warning("Eval dataset not found at %s; returning empty list.", path)
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


async def _grade_task(
    task: Dict[str, Any],
    response: str,
    use_llm_judge: bool,
    model_router,
) -> EvalScore:
    """Pick the right evaluator for the task and grade the response."""
    grader = task.get("grader") or "auto"
    if grader == "execution" or task.get("test_code") or task.get("expected_stdout"):
        return ExecutionEvaluator().evaluate(task, response)
    if grader == "llm" or (use_llm_judge and model_router is not None):
        try:
            return await LLMJudgeEvaluator(model_router).evaluate(task, response)
        except Exception as e:
            viki_logger.warning("LLM judge failed (%s); falling back to keyword scoring.", e)
    # Last resort: keyword/contains scoring
    expected = (task.get("expected_outcome") or "").strip().lower()
    response_lower = (response or "").strip().lower()
    score = 1.0 if expected and expected in response_lower else 0.0
    return EvalScore(score=score, passed=bool(score >= 0.5), reason="keyword_fallback")


async def run_harness(
    cfg: HarnessConfig,
    controller,
    inject_prompt: Optional[Callable[[Dict[str, Any]], str]] = None,
) -> Dict[str, Any]:
    """
    Drive the controller against the suite's tasks. Returns a summary dict.
    """
    tasks = load_jsonl(cfg.tasks_path)
    if cfg.limit:
        tasks = tasks[: cfg.limit]
    if not tasks:
        viki_logger.warning("Eval suite %s: no tasks at %s", cfg.suite, cfg.tasks_path)
        return {
            "suite": cfg.suite,
            "task_count": 0,
            "pass_rate": 0.0,
            "results_path": "",
        }

    suite_dir = os.path.join(cfg.results_root, cfg.suite)
    _ensure_dir(suite_dir)
    run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    out_path = os.path.join(suite_dir, f"{run_id}.jsonl")

    viki_logger.info(
        "Eval[%s]: running %d tasks (air_gap=%s, judge=%s) -> %s",
        cfg.suite,
        len(tasks),
        cfg.air_gap,
        cfg.use_llm_judge,
        out_path,
    )

    metadata = {
        "__metadata__": True,
        "suite": cfg.suite,
        "run_id": run_id,
        "task_count": len(tasks),
        "air_gap": bool(cfg.air_gap),
        "use_llm_judge": bool(cfg.use_llm_judge),
        "persona": cfg.persona,
        "started_at": time.time(),
    }
    metadata.update({k: v for k, v in _active_model_identity(controller).items() if v})

    passed = 0
    total_score = 0.0
    with open(out_path, "w", encoding="utf-8") as out:
        out.write(json.dumps(metadata) + "\n")
        for i, task in enumerate(tasks):
            prompt = inject_prompt(task) if inject_prompt else task.get("prompt", "")
            t0 = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    controller.process_request(prompt), timeout=cfg.timeout
                )
            except asyncio.TimeoutError:
                response = ""
            except Exception as e:
                response = f"ERROR: {e}"
            latency = time.perf_counter() - t0
            score = await _grade_task(task, response, cfg.use_llm_judge, getattr(controller, "model_router", None))
            row = {
                "task_id": task.get("id", str(i)),
                "task_name": task.get("name") or task.get("id"),
                "model_profile": metadata.get("model_profile"),
                "model_name": metadata.get("model_name"),
                "prompt": prompt[:500],
                "response": (response or "")[:1500],
                "score": score.score,
                "passed": score.passed,
                "reason": score.reason,
                "latency_seconds": round(latency, 3),
                "judge_votes": score.judge_votes,
            }
            out.write(json.dumps(row) + "\n")
            if score.passed:
                passed += 1
            total_score += score.score
            viki_logger.info("  [%d/%d] %s -> %.2f (%s)", i + 1, len(tasks), row["task_id"], score.score, "PASS" if score.passed else "FAIL")

    summary = {
        "suite": cfg.suite,
        "run_id": run_id,
        "task_count": len(tasks),
        "pass_rate": passed / len(tasks),
        "mean_score": total_score / len(tasks),
        "results_path": out_path,
        "air_gap": cfg.air_gap,
        "model_profile": metadata.get("model_profile"),
        "model_name": metadata.get("model_name"),
    }
    try:
        router = getattr(controller, "model_router", None)
        if router is not None:
            for candidate in (metadata.get("model_profile"), metadata.get("model_name")):
                if candidate:
                    router.apply_eval_signal(candidate, summary["pass_rate"])
    except Exception:
        pass
    viki_logger.info(
        "Eval[%s] done: pass_rate=%.2f%% mean_score=%.3f",
        cfg.suite,
        summary["pass_rate"] * 100,
        summary["mean_score"],
    )
    return summary


# ---------------------------------------------------------------------------
# CLI helpers shared across suite runners
# ---------------------------------------------------------------------------
def make_arg_parser(suite: str, default_dataset: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"VIKI {suite} runner")
    parser.add_argument("--dataset", default=default_dataset, help="Path to JSONL with tasks.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tasks.")
    parser.add_argument("--air-gap", action="store_true", help="Force VIKI into air-gap mode.")
    parser.add_argument("--no-llm-judge", action="store_true", help="Disable LLM-as-judge grader.")
    parser.add_argument("--results-dir", default=None, help="Override output directory.")
    parser.add_argument("--timeout", type=int, default=60, help="Per-task timeout (seconds).")
    parser.add_argument("--mock", action="store_true", help="Use MockLLM (CI smoke).")
    return parser


def build_controller(args, persona_name: Optional[str] = None):
    """Construct a VIKIController suitable for evals."""
    from core.orchestrator import VIKIController
    from config.resolve import get_soul_path

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_dir = os.path.dirname(base_dir)
    settings_path = os.path.join(repo_dir, "viki", "config", "settings.yaml")
    soul_path = get_soul_path(settings_path)

    if getattr(args, "air_gap", False):
        os.environ["VIKI_AIR_GAP"] = "1"
    if getattr(args, "mock", False):
        os.environ["VIKI_LOCAL_LLM_ONLY"] = "1"
    if persona_name:
        os.environ["VIKI_PERSONA"] = persona_name

    return VIKIController(settings_path=settings_path, soul_path=soul_path)


def default_results_root(args) -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_dir = os.path.dirname(base_dir)
    return getattr(args, "results_dir", None) or os.path.join(repo_dir, "data", "eval_results")
