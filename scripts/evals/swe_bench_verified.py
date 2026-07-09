"""Backward-compatible stub — delegates to ``viki.eval.benchmarks``."""

import sys
import warnings

from viki.eval.benchmarks.harness import (
    HarnessConfig,
    build_controller,
    default_results_root,
    make_arg_parser,
    run_harness,
)

SUITE = "swe_bench_verified"

import os
DEFAULT_DATASET = os.path.join("data", "eval_fixtures", f"{SUITE}.jsonl")


import asyncio


async def main_async():
    parser = make_arg_parser(SUITE, DEFAULT_DATASET)
    args = parser.parse_args()
    controller = build_controller(args, persona_name="dev")
    cfg = HarnessConfig(
        suite=SUITE,
        tasks_path=args.dataset,
        results_root=default_results_root(args),
        limit=args.limit,
        air_gap=args.air_gap,
        use_llm_judge=not args.no_llm_judge,
        persona="dev",
        timeout=args.timeout,
        concurrency=args.concurrency,
        resume=args.resume,
    )
    summary = await run_harness(cfg, controller)

    return summary


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
