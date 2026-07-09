"""Backward-compatible stub — delegates to ``viki.eval.benchmarks.harness``."""

import sys
import warnings

from viki.eval.benchmarks.harness import (
    HarnessConfig,
    _active_model_identity,
    _ensure_dir,
    _find_recent_run_cache,
    _grade_task_with_retry,
    build_controller,
    default_results_root,
    load_jsonl,
    make_arg_parser,
    run_harness,
)

__all__ = [
    "HarnessConfig",
    "build_controller",
    "default_results_root",
    "load_jsonl",
    "make_arg_parser",
    "run_harness",
]
