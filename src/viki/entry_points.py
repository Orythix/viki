"""
Console entry points for forge, eval, and ingest subcommands.

Usage:
    viki-forge [--help]
    viki-eval   [--help]
    viki-ingest [--help]

Each import-lazy loads only the modules it needs so startup stays fast.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any, NoReturn, cast


def _lazy_controller(*, low_resource: bool = False):
    """Build a minimal VIKIController for tool subcommands."""
    from viki.config.logger import viki_logger
    from viki.core.orchestrator import VIKIController

    config_dir = os.environ.get("VIKI_CONFIG_DIR", "")
    if not config_dir or not os.path.isdir(config_dir):
        config_dir = os.path.join(os.getcwd(), "config")
    settings_path = os.path.join(config_dir, "settings.yaml")
    soul_path = os.path.join(config_dir, "soul.yaml")
    return VIKIController(settings_path, soul_path), viki_logger


async def _run_forge(args: argparse.Namespace) -> None:
    """Run the Neural Forge training pipeline."""
    controller, log = _lazy_controller(low_resource=args.low_resource)
    from viki import evolution_engine as _evolution_engine

    EvolutionEngine = cast("Any", getattr(_evolution_engine, "EvolutionEngine", None))  # noqa: B009

    engine = EvolutionEngine(controller)
    log.info(
        "Forge: starting training run (dataset=%s, epochs=%d)...",
        args.dataset or "auto",
        args.epochs,
    )
    result = await engine.run_forge(
        dataset_path=args.dataset,
        epochs=args.epochs,
        lora_r=args.lora_r,
    )
    print(result)
    log.info("Forge: run complete.")


EVAL_SUITES = [
    "humaneval_plus",
    "livecodebench",
    "swe_bench_verified",
    "bigcodebench",
    "gaia",
    "agentbench",
    "gpqa_diamond",
]


async def _run_eval(args: argparse.Namespace) -> None:
    """Run the benchmark eval harness and compute the capability index."""
    import json
    import os

    from viki.config.logger import viki_logger as log
    from viki.core.capability_index import CapabilityIndex
    from viki.eval.benchmarks import prepare
    from viki.eval.benchmarks.harness import (
        HarnessConfig,
        build_controller,
        default_results_root,
        run_harness,
    )

    suites = EVAL_SUITES if not args.suite or args.suite == "all" else [args.suite]
    unknown = [s for s in suites if s not in EVAL_SUITES]
    if unknown:
        print(f"Unknown suite(s): {', '.join(unknown)}. Available: {', '.join(EVAL_SUITES)}")
        return

    if args.prepare_datasets:
        for s in suites:
            try:
                prepare(s, max_examples=args.limit)
            except Exception as e:
                log.warning("Eval: prepare %s failed: %s", s, e)

    controller = build_controller(args)
    results_root = default_results_root(args)
    summaries = []
    for suite in suites:
        cfg = HarnessConfig(
            suite=suite,
            tasks_path=os.path.join(args.dataset_dir, f"{suite}.jsonl"),
            results_root=results_root,
            limit=args.limit,
            air_gap=args.air_gap,
            use_llm_judge=not args.no_llm_judge,
            timeout=args.timeout,
            concurrency=args.concurrency,
            resume=args.resume,
        )
        log.info("Eval: running suite '%s'...", suite)
        try:
            summary = await run_harness(cfg, controller)
        except Exception as e:
            summary = {"suite": suite, "error": str(e)}
        summaries.append(summary)

    index = CapabilityIndex(results_root).compute()
    index_path = os.path.join(results_root, "capability_index.json")
    os.makedirs(results_root, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"index": index, "summaries": summaries}, f, indent=2)

    print(json.dumps(index, indent=2))
    for s in summaries:
        print(
            f"  {s.get('suite', '?'):24} pass_rate={s.get('pass_rate', 0):.2f} "
            f"mean_score={s.get('mean_score', 0):.3f}"
        )
    log.info("Eval: complete. Capability index written to %s", index_path)


async def _run_ingest(args: argparse.Namespace) -> None:
    """Run knowledge ingestion."""
    controller, log = _lazy_controller(low_resource=args.low_resource)
    log.info("Ingest: starting (source=%s)...", args.source or "web")

    if args.source == "web" or not args.source:
        topics = [args.topic] if args.topic else []
        from viki.scripts.ingest_web_topics import ingest_web_topics

        result = await ingest_web_topics(controller, topics=topics, max_results=args.max_results)
    elif args.source == "file" and args.path:
        result = controller.learning_module.import_lessons_from_jsonl(args.path)
    else:
        result = "Usage: viki-ingest --source web --topic <topic> | viki-ingest --source file --path <path>"
    print(result)
    log.info("Ingest: complete.")


def _build_parser() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--low-resource", action="store_true", help="Skip ML-heavy modules")
    parent.add_argument("--debug", action="store_true", help="Enable debug logging")

    parser = argparse.ArgumentParser(description="VIKI tool subcommands")
    sub = parser.add_subparsers(dest="command", required=True)

    forge = sub.add_parser("forge", parents=[parent], help="Run Neural Forge training")
    forge.add_argument("--dataset", help="Path to training dataset (JSONL)")
    forge.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    forge.add_argument("--lora-r", type=int, default=8, help="LoRA rank")

    ev = sub.add_parser("eval", parents=[parent], help="Run evaluation harness")
    ev.add_argument(
        "--suite", default="all", help=f"Suite name or 'all' (available: {', '.join(EVAL_SUITES)})"
    )
    ev.add_argument("--limit", type=int, default=10, help="Max tasks per suite")
    ev.add_argument("--air-gap", action="store_true", help="Force VIKI into air-gap mode")
    ev.add_argument("--no-llm-judge", action="store_true", help="Disable LLM-as-judge grader")
    ev.add_argument("--mock", action="store_true", help="Use MockLLM (CI smoke)")
    ev.add_argument("--timeout", type=int, default=60, help="Per-task timeout (seconds)")
    ev.add_argument("--concurrency", "-c", type=int, default=1, help="Concurrent tasks")
    ev.add_argument("--resume", "-r", action="store_true", help="Resume last matching run")
    ev.add_argument("--results-dir", default=None, help="Override output directory")
    ev.add_argument(
        "--dataset-dir",
        default=os.path.join("data", "eval_fixtures"),
        help="Directory with <suite>.jsonl task files",
    )
    ev.add_argument(
        "--prepare-datasets",
        action="store_true",
        help="Materialize benchmark fixtures via HuggingFace before running",
    )

    ingest = sub.add_parser("ingest", parents=[parent], help="Run knowledge ingestion")
    ingest.add_argument("--source", choices=["web", "file"], default="web", help="Data source")
    ingest.add_argument("--topic", help="Topic for web ingestion")
    ingest.add_argument("--path", help="Path to JSONL file for file ingestion")
    ingest.add_argument("--max-results", type=int, default=10, help="Max results for web ingestion")

    return parser


def _argv_for(command: str) -> list[str]:
    """Prepend the subcommand so ``viki-eval --suite x`` works without ``eval``."""
    argv = sys.argv[1:]
    if not argv:
        return [command]
    if argv[0] not in ("forge", "eval", "ingest"):
        argv = [command, *argv]
    return argv


def forge_main() -> NoReturn:
    """Entry point for ``viki-forge``."""
    parser = _build_parser()
    args = parser.parse_args(_argv_for("forge"))
    asyncio.run(_run_forge(args))
    sys.exit(0)


def eval_main() -> NoReturn:
    """Entry point for ``viki-eval``."""
    parser = _build_parser()
    args = parser.parse_args(_argv_for("eval"))
    asyncio.run(_run_eval(args))
    sys.exit(0)


def ingest_main() -> NoReturn:
    """Entry point for ``viki-ingest``."""
    parser = _build_parser()
    args = parser.parse_args(_argv_for("ingest"))
    asyncio.run(_run_ingest(args))
    sys.exit(0)
