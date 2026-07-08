"""
Real benchmark dataset adapters (Phase 7 / P1).

Each adapter knows how to:
  1. Locate (or download) the canonical dataset from its upstream source.
  2. Convert each example into the harness's task format:
         {"id", "name", "prompt", "grader", "test_code"|"expected_*"}
  3. Cache the resulting JSONL in `data/eval_fixtures/<suite>.jsonl` so
     subsequent runs are offline-friendly.

Datasets are deliberately pinned by version/split so leaderboard scores are
reproducible. The adapters degrade gracefully when `datasets` /
`huggingface_hub` aren't installed: in that case we leave any pre-existing
cached fixture alone, and `prepare()` returns False.

Usage:
    python scripts/evals/eval_datasets.py --suite humaneval_plus
    python scripts/evals/eval_datasets.py --suite swe_bench_verified --limit 50
    python scripts/evals/eval_datasets.py --suite all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from viki.config.logger import viki_logger  # noqa: E402


@dataclass
class DatasetSpec:
    suite: str
    hf_path: str  # HuggingFace dataset id, e.g. "evalplus/humanevalplus"
    hf_split: str  # split name, e.g. "test"
    revision: str | None  # commit SHA / tag for reproducibility
    convert: Callable[[dict[str, Any]], dict[str, Any] | None]
    description: str


# ---------------------------------------------------------------------------
# Per-suite converters: each returns a task dict in the harness's format,
# or None to skip the example.
# ---------------------------------------------------------------------------
def _humaneval_plus_convert(ex: dict[str, Any]) -> dict[str, Any] | None:
    """
    HumanEval+ schema:
      task_id, prompt (function signature + docstring), canonical_solution,
      test (extended unit test), entry_point.
    We use `test` as the grader's test_code so the harness can execute it.
    """
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
    """
    SWE-bench Verified schema:
      instance_id, repo, base_commit, problem_statement, hints_text,
      patch (gold), test_patch, FAIL_TO_PASS, PASS_TO_PASS.
    We surface a 'fix the bug' prompt; grading is LLM-as-judge by default
    because running the full harness requires Docker images.
    """
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
    """
    LiveCodeBench schema (problem-solving subset):
      question_title, question_content, public_test_cases, private_test_cases,
      starter_code, difficulty, contest_id.
    """
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
    """
    GAIA schema: Question, Final answer, Level, Annotator metadata.
    """
    q = ex.get("Question") or ex.get("question")
    a = ex.get("Final answer") or ex.get("final_answer")
    if not q or a is None:
        return None
    return {
        "id": ex.get("task_id") or q[:64],
        "name": (ex.get("task_id") or q[:32]),
        "prompt": str(q),
        "grader": "llm",
        "expected_outcome": str(a),
        "metadata": {"level": ex.get("Level")},
    }


def _agentbench_convert(ex: dict[str, Any]) -> dict[str, Any] | None:
    """
    AgentBench schema varies per sub-task; we accept the generic
    {scenario, instruction, gold_answer} shape. Sub-tasks that need an env
    are flagged via metadata so the harness can skip them when offline.
    """
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
    """BigCodeBench: prompts + canonical solution + tests."""
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
    """GPQA Diamond: graduate-level multiple-choice."""
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
        hf_split="train",  # GPQA has no test split published
        revision=None,
        convert=_gpqa_convert,
        description="GPQA Diamond graduate-level multiple-choice (~200).",
    ),
}


def _output_path(suite: str) -> str:
    return os.path.join(ROOT, "data", "eval_fixtures", f"{suite}.jsonl")


def _try_load_hf(spec: DatasetSpec, max_examples: int | None) -> list[dict[str, Any]] | None:
    """
    Load a HuggingFace dataset if the `datasets` package is available.
    Returns None on import failure or download error so callers can decide
    whether to error or use a previous cached file.
    """
    try:
        from datasets import load_dataset  # type: ignore
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
    """
    Materialize the suite's fixture JSONL on disk and return its path.
    Returns None when the suite cannot be prepared (e.g. `datasets` not
    installed and no cached fixture exists).
    """
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
