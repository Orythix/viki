"""RAG and retrieval evaluation utilities (offline metrics, reports) and benchmark suite runners."""

from viki.eval.benchmarks import (
    DatasetSpec,
    HarnessConfig,
    build_controller,
    default_results_root,
    make_arg_parser,
    prepare,
    run_harness,
)
from viki.eval.rag_eval import GoldRow, RagEvalReport, evaluate_rag_retrieval, load_gold_jsonl
from viki.eval.rag_judge import enrich_report_with_local_judge, run_local_judge

__all__ = [
    "GoldRow",
    "RagEvalReport",
    "evaluate_rag_retrieval",
    "load_gold_jsonl",
    "enrich_report_with_local_judge",
    "run_local_judge",
    "HarnessConfig",
    "DatasetSpec",
    "build_controller",
    "default_results_root",
    "make_arg_parser",
    "prepare",
    "run_harness",
]
