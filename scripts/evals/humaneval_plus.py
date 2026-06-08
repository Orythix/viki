"""
HumanEval+ runner.

Each task in JSONL:
  {
    "id": "HumanEval/0",
    "prompt": "<function signature + docstring>",
    "test_code": "<def check(candidate): assert ...>",
    "grader": "execution"
  }

The candidate is the agent's answer text; ExecutionEvaluator extracts a fenced
Python code block, runs it in a fresh subprocess, then exec's the test.
"""

from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.evals.harness import (  # noqa: E402
    HarnessConfig,
    build_controller,
    default_results_root,
    make_arg_parser,
    run_harness,
)

SUITE = "humaneval_plus"
DEFAULT_DATASET = os.path.join("data", "eval_fixtures", f"{SUITE}.jsonl")


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
    return await run_harness(cfg, controller)



def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
