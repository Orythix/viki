"""
Common harness for VIKI eval runners.

Upgraded version supporting:
- Concurrency control (via asyncio.Semaphore)
- Task cache resumption (skips already-evaluated tasks to resume interrupted runs)
- LLM Judge robust retries with backoff
- Live Rich progress dashboard with statistics (current pass rate, mean score, ETA)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Reconfigure stdout/stderr to UTF-8 on Windows/legacy hosts to handle Unicode characters.
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# Local-first import path for ad-hoc invocations.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from viki.config.logger import viki_logger  # noqa: E402
from viki.core.evaluators import EvalScore, ExecutionEvaluator, LLMJudgeEvaluator  # noqa: E402

# Import Rich components for a premium console experience
try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table

    HAS_RICH = True
except ImportError:
    HAS_RICH = False


@dataclass
class HarnessConfig:
    suite: str
    tasks_path: str
    results_root: str
    limit: int | None = None
    air_gap: bool = False
    use_llm_judge: bool = True
    persona: str | None = None
    timeout: int = 60
    concurrency: int = 1
    resume: bool = False


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _active_model_identity(controller) -> dict[str, str | None]:
    """Best-effort identity for the model under evaluation."""
    model_profile: str | None = None
    model_name: str | None = None
    try:
        model_profile = ((getattr(controller, "models_config", {}) or {}).get("models") or {}).get(
            "default"
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


def load_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not os.path.isfile(path):
        viki_logger.warning("Eval dataset not found at %s; returning empty list.", path)
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


async def _grade_task_with_retry(
    task: dict[str, Any],
    response: str,
    use_llm_judge: bool,
    model_router,
    retries: int = 3,
    backoff_factor: float = 2.0,
) -> EvalScore:
    """Grades the task, applying automatic retries with exponential backoff on LLM judge failures."""
    grader = task.get("grader") or "auto"
    if grader == "execution" or task.get("test_code") or task.get("expected_stdout"):
        return ExecutionEvaluator().evaluate(task, response)

    if grader == "llm" or (use_llm_judge and model_router is not None):
        delay = 1.0
        for attempt in range(retries):
            try:
                evaluator = LLMJudgeEvaluator(model_router)
                return await evaluator.evaluate(task, response)
            except Exception as e:
                viki_logger.warning(
                    "LLM judge failed on attempt %d/%d (%s). Retrying in %.1fs...",
                    attempt + 1,
                    retries,
                    e,
                    delay,
                )
                if attempt == retries - 1:
                    viki_logger.error(
                        "LLM judge chronically failed; falling back to keyword grader."
                    )
                    break
                await asyncio.sleep(delay)
                delay *= backoff_factor

    # Fallback: keyword/contains scoring
    expected = (task.get("expected_outcome") or "").strip().lower()
    response_lower = (response or "").strip().lower()
    score = 1.0 if expected and expected in response_lower else 0.0
    return EvalScore(score=score, passed=bool(score >= 0.5), reason="keyword_fallback")


def _find_recent_run_cache(
    results_dir: str, suite: str, model_id: dict
) -> dict[str, dict[str, Any]]:
    """Scan the target directory for a previous matching run and index completed tasks."""
    cache = {}
    if not os.path.exists(results_dir):
        return cache

    matching_file = None
    latest_time = 0.0

    # Iterate over files to find the newest run with matching model metadata
    for filename in os.listdir(results_dir):
        if filename.endswith(".jsonl"):
            filepath = os.path.join(results_dir, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if not first_line:
                        continue
                    meta = json.loads(first_line)
                    if not meta.get("__metadata__") or meta.get("suite") != suite:
                        continue

                    # Verify model identifiers match
                    m_profile = meta.get("model_profile")
                    m_name = meta.get("model_name")
                    if m_profile == model_id.get("model_profile") or m_name == model_id.get(
                        "model_name"
                    ):
                        mtime = os.path.getmtime(filepath)
                        if mtime > latest_time:
                            latest_time = mtime
                            matching_file = filepath
            except Exception:
                continue

    if matching_file:
        viki_logger.info("Found matching run for cache resumption: %s", matching_file)
        try:
            with open(matching_file, encoding="utf-8") as f:
                next(f)  # Skip metadata line
                for line in f:
                    row = json.loads(line.strip())
                    if "task_id" in row:
                        cache[row["task_id"]] = row
        except Exception as e:
            viki_logger.warning("Failed to load matching run cache: %s", e)

    return cache


async def run_harness(
    cfg: HarnessConfig,
    controller,
    inject_prompt: Callable[[dict[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """Drive the controller against the suite's tasks concurrently with caching and rich output."""
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

    model_id = _active_model_identity(controller)

    # 1. Load run cache if requested
    cache = {}
    if cfg.resume:
        cache = _find_recent_run_cache(suite_dir, cfg.suite, model_id)
        if cache:
            viki_logger.info("Cache Resumption: Loaded %d completed tasks.", len(cache))

    viki_logger.info(
        "Eval[%s]: driving %d tasks (air_gap=%s, concurrency=%d, judge=%s) -> %s",
        cfg.suite,
        len(tasks),
        cfg.air_gap,
        cfg.concurrency,
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
        "concurrency": cfg.concurrency,
        "resumed": bool(cache),
    }
    metadata.update({k: v for k, v in model_id.items() if v})

    passed = 0
    total_score = 0.0
    sem = asyncio.Semaphore(cfg.concurrency)
    write_lock = asyncio.Lock()

    # Pre-write metadata header
    with open(out_path, "w", encoding="utf-8") as out:
        out.write(json.dumps(metadata) + "\n")

    # Define the worker coroutine
    async def evaluate_task(
        task_item: dict[str, Any], index: int, progress_bar=None, task_tracker=None
    ):
        nonlocal passed, total_score
        task_id = task_item.get("id", str(index))
        prompt = inject_prompt(task_item) if inject_prompt else task_item.get("prompt", "")

        # Resumed/Cached Hit Check
        if cfg.resume and task_id in cache:
            cached_row = cache[task_id]
            # Verify prompt or simple match
            cached_score = cached_row.get("score", 0.0)
            cached_passed = cached_row.get("passed", False)

            async with write_lock:
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(cached_row) + "\n")

            if cached_passed:
                passed += 1
            total_score += cached_score

            if progress_bar and task_tracker:
                progress_bar.update(
                    task_tracker, advance=1, description=f"[dim]Skipped (Cached) {task_id}[/]"
                )
            return

        async with sem:
            t0 = time.perf_counter()
            if progress_bar and task_tracker:
                progress_bar.update(task_tracker, description=f"[cyan]Running {task_id}...[/]")
            try:
                response = await asyncio.wait_for(
                    controller.process_request(prompt), timeout=cfg.timeout
                )
            except asyncio.TimeoutError:
                response = ""
            except Exception as e:
                response = f"ERROR: {e}"
            latency = time.perf_counter() - t0

            score = await _grade_task_with_retry(
                task_item, response, cfg.use_llm_judge, getattr(controller, "model_router", None)
            )

            row = {
                "task_id": task_id,
                "task_name": task_item.get("name") or task_id,
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

            async with write_lock:
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")

            if score.passed:
                passed += 1
            total_score += score.score

            if progress_bar and task_tracker:
                status_color = "green" if score.passed else "red"
                status_symbol = "✓" if score.passed else "✗"
                progress_bar.update(
                    task_tracker,
                    advance=1,
                    description=f"[{status_color}]{status_symbol} {task_id} -> {score.score:.2f} ({latency:.1f}s)[/]",
                )

    # 2. Rich Progress Bar Rendering Loop
    if HAS_RICH:
        console = Console()
        console.print(
            Panel(
                f"[bold magenta]VIKI EVALUATION PIPELINE[/]\n"
                f"[dim]Suite      :[/] [cyan]{cfg.suite}[/]\n"
                f"[dim]Model      :[/] [yellow]{model_id.get('model_label', 'Unknown')}[/]\n"
                f"[dim]Concurrency:[/] [green]{cfg.concurrency}[/]\n"
                f"[dim]Resuming   :[/] {'[green]YES[/]' if cache else '[dim]NO[/]'}",
                box=box.ROUNDED,
                border_style="magenta",
                expand=False,
            )
        )

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            TextColumn("[bold yellow]Pass Rate: {task.fields[pass_rate]:.1%}"),
            TextColumn("[bold cyan]Mean: {task.fields[mean_score]:.2f}"),
            TimeRemainingColumn(),
            console=console,
        )

        with progress:
            task_tracker = progress.add_task(
                "Evaluating...", total=len(tasks), pass_rate=0.0, mean_score=0.0
            )

            # Run all tasks concurrently/sequentially according to Semaphore
            coroutines = []
            for i, task_item in enumerate(tasks):
                coroutines.append(evaluate_task(task_item, i, progress, task_tracker))

            await asyncio.gather(*coroutines)

            # Final progress update
            progress.update(
                task_tracker,
                description="[bold green]✓ Done![/]",
                pass_rate=passed / len(tasks),
                mean_score=total_score / len(tasks),
            )
    else:
        # Standard fallback loop without Rich
        coroutines = []
        for i, task_item in enumerate(tasks):
            coroutines.append(evaluate_task(task_item, i))
        await asyncio.gather(*coroutines)

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

    # Try to apply evaluation signal to model router
    try:
        router = getattr(controller, "model_router", None)
        if router is not None:
            for candidate in (metadata.get("model_profile"), metadata.get("model_name")):
                if candidate:
                    router.apply_eval_signal(candidate, summary["pass_rate"])
    except Exception:
        pass

    # Print a premium final results card
    if HAS_RICH:
        console = Console()
        table = Table(title="Evaluation Run Summary", box=box.DOUBLE, header_style="bold cyan")
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold")

        table.add_row("Run ID", summary["run_id"])
        table.add_row("Suite", summary["suite"])
        table.add_row("Tasks Count", str(summary["task_count"]))
        table.add_row("Pass Rate", f"[bold green]{summary['pass_rate']:.2%}[/]")
        table.add_row("Mean Score", f"[bold yellow]{summary['mean_score']:.3f}[/]")
        table.add_row("Logs Path", summary["results_path"])

        console.print()
        console.print(table)
        console.print()
    else:
        viki_logger.info(
            "Eval[%s] done: pass_rate=%.2f%% mean_score=%.3f (path=%s)",
            cfg.suite,
            summary["pass_rate"] * 100,
            summary["mean_score"],
            summary["results_path"],
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
    parser.add_argument(
        "--concurrency", "-c", type=int, default=1, help="Concurrently run N tasks (default: 1)."
    )
    parser.add_argument(
        "--resume", "-r", action="store_true", help="Resume evaluation from the last matching run."
    )
    return parser


def build_controller(args, persona_name: str | None = None):
    """Construct a VIKIController suitable for evals."""
    from config.resolve import get_soul_path
    from core.orchestrator import VIKIController

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_dir = os.path.dirname(base_dir)
    settings_path = os.path.join(repo_dir, "config", "settings.yaml")
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
