"""RAG and retrieval evaluation utilities (offline metrics, reports)."""

from eval.rag_eval import GoldRow, RagEvalReport, evaluate_rag_retrieval, load_gold_jsonl
from eval.rag_judge import enrich_report_with_ollama_judge, run_ollama_judge

__all__ = [
    "GoldRow",
    "RagEvalReport",
    "evaluate_rag_retrieval",
    "load_gold_jsonl",
    "enrich_report_with_ollama_judge",
    "run_ollama_judge",
]
