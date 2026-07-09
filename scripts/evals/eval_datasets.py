"""Backward-compatible stub — delegates to ``viki.eval.benchmarks.eval_datasets``."""

import sys
import warnings

from viki.eval.benchmarks.eval_datasets import (
    SPECS,
    DatasetSpec,
    _agentbench_convert,
    _bigcodebench_convert,
    _gaia_convert,
    _gpqa_convert,
    _humaneval_plus_convert,
    _livecodebench_convert,
    _output_path,
    _swe_bench_convert,
    _try_load_hf,
    main,
    prepare,
)

__all__ = [
    "DatasetSpec",
    "SPECS",
    "prepare",
    "main",
]
