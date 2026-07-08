#!/usr/bin/env python3
"""
Offline RAG retrieval evaluation against VIKI lessons (SQLite).

Usage (repo root):
  python scripts/run_rag_eval.py --gold viki/eval/fixtures/rag_gold.example.jsonl
  python scripts/run_rag_eval.py --gold my_gold.jsonl --k 8 --out reports/rag_eval.json

Requires lessons in data_dir (seed with scripts/seed_knowledge.py for the example gold).

Why: Substring gold labels are cheap to curate and catch major retrieval regressions
before you invest in LLM-judge or human eval.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Quiet per-query lesson dumps (viki_logger is the "VIKI" root; INFO logs huge Unicode on Windows consoles).
logging.getLogger("VIKI").setLevel(logging.WARNING)

from viki.core.knowledge_ingestion import LearningModule  # noqa: E402
from viki.eval.rag_eval import evaluate_rag_retrieval, load_gold_jsonl  # noqa: E402
from viki.eval.rag_judge import enrich_report_with_ollama_judge  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Run RAG retrieval eval on lesson store")
    p.add_argument("--gold", required=True, help="JSONL gold file (see viki/eval/fixtures/)")
    p.add_argument(
        "--data-dir",
        default=os.environ.get("VIKI_DATA_DIR", str(_REPO / "data")),
        help="Directory with viki_knowledge.db",
    )
    p.add_argument("--k", type=int, default=5, help="Top-K retrieved lessons per query")
    p.add_argument("--out", default="", help="Write JSON report to this path")
    p.add_argument(
        "--judge",
        action="store_true",
        help="After retrieval, call local Ollama to score relevance (slower; needs ollama serve)",
    )
    p.add_argument(
        "--ollama-url",
        default=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
        help="Ollama base URL for --judge",
    )
    p.add_argument(
        "--judge-model",
        default=os.environ.get(
            "OLLAMA_MODEL", os.environ.get("VIKI_FORGE_BASE_OLLAMA_MODEL", "llama3.2:latest")
        ),
        help="Ollama model tag for --judge",
    )
    p.add_argument(
        "--judge-timeout",
        type=float,
        default=90.0,
        help="Per-query HTTP timeout for judge (seconds)",
    )
    p.add_argument(
        "--judge-context-chars",
        type=int,
        default=6000,
        help="Max characters of retrieved text sent to the judge",
    )
    args = p.parse_args()

    gold = load_gold_jsonl(args.gold)
    lm = LearningModule(os.path.abspath(args.data_dir))
    report = evaluate_rag_retrieval(
        lm,
        gold,
        k=args.k,
        meta={
            "gold_file": str(Path(args.gold).resolve()),
            "data_dir": os.path.abspath(args.data_dir),
            "run_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    if args.judge:
        enrich_report_with_ollama_judge(
            report,
            gold,
            ollama_url=args.ollama_url,
            model=args.judge_model,
            timeout_s=args.judge_timeout,
            max_context_chars=args.judge_context_chars,
        )

    text = report.to_json()
    print(text)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"\nWrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
