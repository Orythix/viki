"""Real benchmark dataset adapters for the VIKI eval harness.

Each adapter knows how to:
  1. Locate (or download) the canonical dataset from its upstream source.
  2. Convert each example into the harness's task format:
         {"id", "name", "prompt", "grader", "test_code"|"expected_*"}
  3. Cache the resulting JSONL in ``data/eval_fixtures/<suite>.jsonl``.

Datasets are deliberately pinned by version/split so leaderboard scores are
reproducible. The adapters degrade gracefully when ``datasets`` /
``huggingface_hub`` aren't installed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from viki.config.logger import viki_logger

__all__ = [
    "DatasetSpec",
    "SPECS",
    "prepare",
    "main",
]

ROOT = Path(__file__).resolve().parents[4]  # src/viki/eval/benchmarks/ -> repo root


@dataclass
class DatasetSpec:
    suite: str
    hf_path: str
    hf_split: str
    revision: str | None
    convert: Callable[[dict[str, Any]], dict[str, Any] | None]
    description: str


def _humaneval_plus_convert(ex: dict[str, Any]) -> dict[str, Any] | None:
    prompt = ex.get("prompt", "")
    test = ex.get("test", "")
    entry = ex.get("entry_point", "")
    if not prompt or not test:
        return None
    full_prompt = (
        prompt
        + "\n# Implement the function above. The complete file (signature + body) "
        + "must run as standalone Python. Do not include explanations."
    )
    return {
        "id": ex.get("task_id", entry),
        "name": entry or ex.get("task_id"),
        "prompt": full_prompt,
        "grader": "execution",
        "test_code": test + f"\n\ncheck({entry})\n",
        "entry_point": entry,
    }


def _swe_bench_convert(ex: dict[str, Any]) -> dict[str, Any] | None:
    if not ex.get("problem_statement"):
        return None
    return {
        "id": ex.get("instance_id"),
        "name": ex.get("instance_id"),
        "prompt": (
            f"Repository: {ex.get('repo')}\n"
            f"Base commit: {ex.get('base_commit')}\n\n"
            f"Issue / problem statement:\n{ex.get('problem_statement')}\n\n"
            f"Produce a unified-diff patch that fixes the issue. Output only "
            f"the diff, starting with `diff --git`."
        ),
        "grader": "llm",
        "expected_outcome": "diff --git",
        "metadata": {
            "repo": ex.get("repo"),
            "base_commit": ex.get("base_commit"),
            "fail_to_pass": ex.get("FAIL_TO_PASS"),
            "pass_to_pass": ex.get("PASS_TO_PASS"),
        },
    }


def _livecodebench_convert(ex: dict[str, Any]) -> dict[str, Any] | None:
    title = ex.get("question_title") or ex.get("title")
    content = ex.get("question_content") or ex.get("description")
    starter = ex.get("starter_code") or ""
    if not content:
        return None
    return {
        "id": ex.get("contest_id") or title,
        "name": title,
        "prompt": (
            f"# {title}\n\n"
            f"{content}\n\n"
            f"Starter code:\n```python\n{starter}\n```\n\n"
            "Submit the complete Python solution. Use only the standard library."
        ),
        "grader": "execution",
        "expected_stdout": ex.get("expected_stdout"),
        "test_code": ex.get("public_test_cases") or "",
    }


def _gaia_convert(ex: dict[str, Any]) -> dict[str, Any] | None:
    q = ex.get("Question") or ex.get("question")
    a = ex.get("Final answer") or ex.get("final_answer")
    if not q or a is None:
        return None
    return {
        "id": ex.get("task_id") or q[:64],
        "name": ex.get("task_id") or q[:32],
        "prompt": str(q),
        "grader": "llm",
        "expected_outcome": str(a),
        "metadata": {"level": ex.get("Level")},
    }


def _agentbench_convert(ex: dict[str, Any]) -> dict[str, Any] | None:
    instr = ex.get("instruction") or ex.get("question") or ex.get("scenario")
    gold = ex.get("gold_answer") or ex.get("answer")
    if not instr:
        return None
    return {
        "id": ex.get("id") or str(hash(instr)),
        "name": ex.get("name") or "agentbench_task",
        "prompt": instr,
        "grader": "llm",
        "expected_outcome": gold or "",
        "metadata": {"sub_task": ex.get("sub_task"), "needs_env": ex.get("needs_env", False)},
    }


def _bigcodebench_convert(ex: dict[str, Any]) -> dict[str, Any] | None:
    prompt = ex.get("prompt") or ex.get("complete_prompt")
    test = ex.get("test")
    entry = ex.get("entry_point")
    if not prompt or not test:
        return None
    return {
        "id": ex.get("task_id", entry),
        "name": entry,
        "prompt": prompt + "\n# Implement the function above. Output the full file.",
        "grader": "execution",
        "test_code": test + f"\n\nrun_tests({entry})\n",
        "entry_point": entry,
    }


def _gpqa_convert(ex: dict[str, Any]) -> dict[str, Any] | None:
    q = ex.get("Question") or ex.get("question")
    a = ex.get("Correct Answer") or ex.get("answer")
    options = [
        ex.get("Correct Answer"),
        ex.get("Incorrect Answer 1"),
        ex.get("Incorrect Answer 2"),
        ex.get("Incorrect Answer 3"),
    ]
    options = [o for o in options if o]
    if not q or not options:
        return None
    return {
        "id": ex.get("Record ID") or q[:64],
        "name": "gpqa_diamond_q",
        "prompt": (
            f"{q}\n\nOptions:\n"
            + "\n".join(f"({chr(65 + i)}) {o}" for i, o in enumerate(options))
            + "\n\nReply with the letter of the correct option only."
        ),
        "grader": "llm",
        "expected_outcome": a,
    }


SPECS: dict[str, DatasetSpec] = {
    "humaneval_plus": DatasetSpec(
        suite="humaneval_plus",
        hf_path="evalplus/humanevalplus",
        hf_split="test",
        revision=None,
        convert=_humaneval_plus_convert,
        description="HumanEval+ extended unit tests (164 problems).",
    ),
    "swe_bench_verified": DatasetSpec(
        suite="swe_bench_verified",
        hf_path="princeton-nlp/SWE-bench_Verified",
        hf_split="test",
        revision=None,
        convert=_swe_bench_convert,
        description="SWE-bench Verified subset (500 verified GitHub issues).",
    ),
    "livecodebench": DatasetSpec(
        suite="livecodebench",
        hf_path="livecodebench/code_generation_lite",
        hf_split="test",
        revision=None,
        convert=_livecodebench_convert,
        description="LiveCodeBench code generation subset.",
    ),
    "gaia": DatasetSpec(
        suite="gaia",
        hf_path="gaia-benchmark/GAIA",
        hf_split="validation",
        revision=None,
        convert=_gaia_convert,
        description="GAIA Level 1-3 validation set.",
    ),
    "agentbench": DatasetSpec(
        suite="agentbench",
        hf_path="THUDM/AgentBench",
        hf_split="test",
        revision=None,
        convert=_agentbench_convert,
        description="AgentBench multi-environment tasks.",
    ),
    "bigcodebench": DatasetSpec(
        suite="bigcodebench",
        hf_path="bigcode/bigcodebench",
        hf_split="v0.1.0",
        revision=None,
        convert=_bigcodebench_convert,
        description="BigCodeBench programming tasks.",
    ),
    "gpqa_diamond": DatasetSpec(
        suite="gpqa_diamond",
        hf_path="Idavidrein/gpqa",
        hf_split="train",
        revision=None,
        convert=_gpqa_convert,
        description="GPQA Diamond graduate-level multiple-choice (~200).",
    ),
}


def _output_path(suite: str) -> str:
    return str(ROOT / "data" / "eval_fixtures" / f"{suite}.jsonl")


def _try_load_hf(spec: DatasetSpec, max_examples: int | None) -> list[dict[str, Any]] | None:
    try:
        from datasets import load_dataset
    except Exception as e:
        viki_logger.warning(
            "Dataset adapter: `datasets` package not installed (%s). "
            "Install with `pip install datasets`.",
            e,
        )
        return None
    try:
        ds = load_dataset(spec.hf_path, split=spec.hf_split, revision=spec.revision)
    except Exception as e:
        viki_logger.warning("Dataset adapter %s: download failed: %s", spec.suite, e)
        return None
    out: list[dict[str, Any]] = []
    for i, ex in enumerate(ds):
        if max_examples is not None and i >= max_examples:
            break
        try:
            row = spec.convert(dict(ex))
        except Exception as e:
            viki_logger.debug("Convert %s row %d failed: %s", spec.suite, i, e)
            row = None
        if row:
            out.append(row)
    return out


def prepare(
    suite: str,
    max_examples: int | None = None,
    overwrite: bool = False,
) -> str | None:
    spec = SPECS.get(suite)
    if spec is None:
        raise KeyError(f"Unknown suite '{suite}'. Known: {list(SPECS)}")
    out_path = _output_path(suite)
    if os.path.isfile(out_path) and not overwrite:
        viki_logger.info("Dataset adapter %s: cached at %s", suite, out_path)
        return out_path
    rows = _try_load_hf(spec, max_examples)
    if not rows:
        viki_logger.warning(
            "Dataset adapter %s: no rows produced; leaving any existing cache.", suite
        )
        return out_path if os.path.isfile(out_path) else None
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    viki_logger.info("Dataset adapter %s: wrote %d rows to %s", suite, len(rows), out_path)
    return out_path


def main() -> int:
    p = argparse.ArgumentParser(description="VIKI dataset adapter / downloader.")
    p.add_argument("--suite", required=True, help="Suite name or 'all'.")
    p.add_argument("--limit", type=int, default=None, help="Cap examples per suite.")
    p.add_argument("--overwrite", action="store_true", help="Re-download even if cached.")
    args = p.parse_args()

    suites = list(SPECS) if args.suite == "all" else [args.suite]
    for s in suites:
        try:
            path = prepare(s, max_examples=args.limit, overwrite=args.overwrite)
            print(f"  {s}: {path or 'unavailable'}")
        except Exception as e:
            print(f"  {s}: error -> {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
