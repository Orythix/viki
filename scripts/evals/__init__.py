"""Evaluation harness runners for VIKI (Phase 2).

This package is a backward-compatibility shim that re-exports from
``viki.eval.benchmarks``. New code should import directly from
``viki.eval.benchmarks``.
"""

import sys
import warnings

from viki.eval.benchmarks import (
    SPECS,
    DatasetSpec,
    HarnessConfig,
    _agentbench_convert,
    _bigcodebench_convert,
    _gaia_convert,
    _gpqa_convert,
    _humaneval_plus_convert,
    _livecodebench_convert,
    _swe_bench_convert,
    build_controller,
    default_results_root,
    load_jsonl,
    make_arg_parser,
    prepare,
    run_harness,
)

__all__ = [
    "DatasetSpec",
    "HarnessConfig",
    "SPECS",
    "_agentbench_convert",
    "_bigcodebench_convert",
    "_gaia_convert",
    "_gpqa_convert",
    "_humaneval_plus_convert",
    "_livecodebench_convert",
    "_swe_bench_convert",
    "build_controller",
    "default_results_root",
    "load_jsonl",
    "make_arg_parser",
    "prepare",
    "run_harness",
]
