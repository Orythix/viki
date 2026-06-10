"""
Run every available eval suite back-to-back, then print the Capability Index.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.evals.harness import (  # noqa: E402
    HarnessConfig,
    build_controller,
    default_results_root,
    run_harness,
)
from scripts.evals import eval_datasets  # noqa: E402
from viki.core.capability_index import CapabilityIndex  # noqa: E402

SUITES = [
    "humaneval_plus",
    "livecodebench",
    "swe_bench_verified",
    "bigcodebench",
    "gaia",
    "agentbench",
    "gpqa_diamond",
]


async def main_async():
    parser = argparse.ArgumentParser(description="VIKI: run every eval suite.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--air-gap", action="store_true")
    parser.add_argument("--no-llm-judge", action="store_true")
    parser.add_argument("--dataset-dir", default=os.path.join("data", "eval_fixtures"))
    parser.add_argument(
        "--prepare-datasets",
        action="store_true",
        help="Materialize real benchmark fixtures via HuggingFace before running.",
    )
    parser.add_argument("--concurrency", "-c", type=int, default=1, help="Concurrently run N tasks (default: 1).")
    parser.add_argument("--resume", "-r", action="store_true", help="Resume evaluation from the last matching run.")
    args = parser.parse_args()

    if args.prepare_datasets:
        for s in SUITES:
            try:
                eval_datasets.prepare(s, max_examples=args.limit)
            except Exception as e:
                print(f"  prepare {s}: {e}")

    controller = build_controller(args)
    summaries = []
    for suite in SUITES:
        cfg = HarnessConfig(
            suite=suite,
            tasks_path=os.path.join(args.dataset_dir, f"{suite}.jsonl"),
            results_root=default_results_root(args),
            limit=args.limit,
            air_gap=args.air_gap,
            use_llm_judge=not args.no_llm_judge,
            timeout=60,
            concurrency=args.concurrency,
            resume=args.resume,
        )
        try:
            summary = await run_harness(cfg, controller)
        except Exception as e:
            summary = {"suite": suite, "error": str(e)}
        summaries.append(summary)

    index = CapabilityIndex(default_results_root(args)).compute()
    print("=" * 60)
    print("VIKI Capability Index")
    print("=" * 60)
    print(json.dumps(index, indent=2))
    print()
    for s in summaries:
        print(f"  {s.get('suite'):24} pass_rate={s.get('pass_rate', 0):.2f} mean_score={s.get('mean_score', 0):.3f}")
    return index


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
