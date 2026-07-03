"""
Offline RAG / retrieval evaluation for VIKI lessons.

Why this exists
---------------
Production RAG fails silently: retrieval can return the wrong chunks while the LLM
still sounds confident. This module measures whether *retrieval* surfaces expected
evidence under controlled gold queries — before you spend GPU on generation eval.

Metrics (intentionally simple, explainable)
------------------------------------------
- **success@K**: For `must_contain_any`, at least one gold substring appears in the
  union of the top-K retrieved lesson texts (case-insensitive).
- **MRR (mean reciprocal rank)**: Among ranked hits, the first retrieved row that
  contains any `must_contain_any` phrase gets reciprocal rank 1/(rank); else 0.
- **must_contain_all@K**: All phrases appear somewhere in the union of top-K (stricter).
- **must_not_contain_violation@K**: Any forbidden phrase appears in top-K (should be 0 for clean corpora).

Security note: Gold files may contain sensitive strings; treat them like test data, not logs.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from viki.config.logger import viki_logger


@dataclass
class GoldRow:
    id: str
    query: str
    must_contain_any: list[str] = field(default_factory=list)
    must_contain_all: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GoldRow:
        return cls(
            id=str(d.get("id") or ""),
            query=str(d.get("query") or "").strip(),
            must_contain_any=[str(x) for x in (d.get("must_contain_any") or []) if str(x).strip()],
            must_contain_all=[str(x) for x in (d.get("must_contain_all") or []) if str(x).strip()],
            must_not_contain=[str(x) for x in (d.get("must_not_contain") or []) if str(x).strip()],
        )


@dataclass
class QueryResult:
    gold_id: str
    query: str
    latency_ms: float
    retrieved: list[str]
    success_any_at_k: bool
    success_all_at_k: bool
    must_not_contain_violation: bool
    reciprocal_rank_any: float
    reciprocal_rank_all: float
    # Populated when optional Ollama judge runs (see viki.eval.rag_judge).
    judge_relevance: float | None = None
    judge_covers_expected: bool | None = None
    judge_rationale: str | None = None
    judge_latency_ms: float | None = None
    judge_error: str | None = None


@dataclass
class RagEvalReport:
    k: int
    total: int
    success_any_at_k: float
    success_all_at_k: float
    mrr_any: float
    mrr_all: float
    must_not_contain_violation_rate: float
    per_query: list[QueryResult]
    meta: dict[str, Any] = field(default_factory=dict)
    judge_mean_relevance: float | None = None
    judge_covers_expected_rate: float | None = None

    def to_json(self) -> str:
        def ser(q: QueryResult) -> dict[str, Any]:
            d: dict[str, Any] = {
                "gold_id": q.gold_id,
                "query": q.query,
                "latency_ms": round(q.latency_ms, 3),
                "success_any_at_k": q.success_any_at_k,
                "success_all_at_k": q.success_all_at_k,
                "must_not_contain_violation": q.must_not_contain_violation,
                "reciprocal_rank_any": round(q.reciprocal_rank_any, 4),
                "reciprocal_rank_all": round(q.reciprocal_rank_all, 4),
                "retrieved_preview": [t[:200] + ("…" if len(t) > 200 else "") for t in q.retrieved],
            }
            if q.judge_relevance is not None:
                d["judge_relevance"] = round(q.judge_relevance, 4)
            if q.judge_covers_expected is not None:
                d["judge_covers_expected"] = q.judge_covers_expected
            if q.judge_rationale:
                d["judge_rationale"] = q.judge_rationale
            if q.judge_latency_ms is not None:
                d["judge_latency_ms"] = round(q.judge_latency_ms, 3)
            if q.judge_error:
                d["judge_error"] = q.judge_error
            return d

        payload: dict[str, Any] = {
            "k": self.k,
            "total": self.total,
            "success_any_at_k": round(self.success_any_at_k, 4),
            "success_all_at_k": round(self.success_all_at_k, 4),
            "mrr_any": round(self.mrr_any, 4),
            "mrr_all": round(self.mrr_all, 4),
            "must_not_contain_violation_rate": round(self.must_not_contain_violation_rate, 4),
            "per_query": [ser(x) for x in self.per_query],
            "meta": self.meta,
        }
        if self.judge_mean_relevance is not None:
            payload["judge_mean_relevance"] = round(self.judge_mean_relevance, 4)
        if self.judge_covers_expected_rate is not None:
            payload["judge_covers_expected_rate"] = round(self.judge_covers_expected_rate, 4)
        return json.dumps(payload, ensure_ascii=False, indent=2)


def load_gold_jsonl(path: str | Path) -> list[GoldRow]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"gold file not found: {p}")
    rows: list[GoldRow] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(GoldRow.from_dict(json.loads(line)))
    if not rows:
        raise ValueError(f"no gold rows in {p}")
    for r in rows:
        if not r.query:
            raise ValueError(f"gold row {r.id!r} missing query")
        if not r.must_contain_any and not r.must_contain_all:
            raise ValueError(f"gold row {r.id!r} needs must_contain_any and/or must_contain_all")
    return rows


def _union_text(chunks: Sequence[str]) -> str:
    return " ".join(chunks).lower()


def _first_rr_any(retrieved: list[str], phrases: list[str]) -> float:
    if not phrases:
        return 1.0
    pl = [p.lower() for p in phrases]
    for i, chunk in enumerate(retrieved):
        cl = chunk.lower()
        if any(p in cl for p in pl):
            return 1.0 / (i + 1)
    return 0.0


def _first_rr_all(retrieved: list[str], phrases: list[str]) -> float:
    if not phrases:
        return 1.0
    pl = [p.lower() for p in phrases]
    for i in range(len(retrieved)):
        union = _union_text(retrieved[: i + 1])
        if all(p in union for p in pl):
            return 1.0 / (i + 1)
    return 0.0


def _success_any_at_k(retrieved: list[str], phrases: list[str]) -> bool:
    if not phrases:
        return True
    u = _union_text(retrieved)
    return any(p.lower() in u for p in phrases)


def _success_all_at_k(retrieved: list[str], phrases: list[str]) -> bool:
    if not phrases:
        return True
    u = _union_text(retrieved)
    return all(p.lower() in u for p in phrases)


def _must_not_violation(retrieved: list[str], phrases: list[str]) -> bool:
    if not phrases:
        return False
    u = _union_text(retrieved)
    return any(p.lower() in u for p in phrases)


def evaluate_rag_retrieval(
    learning_module: Any,
    gold_rows: Sequence[GoldRow],
    k: int = 5,
    *,
    meta: dict[str, Any] | None = None,
) -> RagEvalReport:
    """
    Run retrieval via `learning_module.get_relevant_lessons(query, limit=k)` for each gold row.

    `learning_module` must be a VIKI `LearningModule` instance (or compatible duck type).
    """
    k = max(1, int(k))
    per_query: list[QueryResult] = []
    for row in gold_rows:
        t0 = time.perf_counter()
        try:
            retrieved = learning_module.get_relevant_lessons(row.query, limit=k)
        except Exception as e:
            viki_logger.warning("rag_eval retrieval failed for %s: %s", row.id, e)
            retrieved = []
        if not isinstance(retrieved, list):
            retrieved = [str(retrieved)] if retrieved else []
        latency_ms = (time.perf_counter() - t0) * 1000.0

        s_all = _success_all_at_k(retrieved, row.must_contain_all)
        if row.must_contain_any:
            s_any = _success_any_at_k(retrieved, row.must_contain_any)
            rr_any = _first_rr_any(retrieved, row.must_contain_any)
        else:
            # Rows that only define must_contain_all: align "any" metrics with the all-* gate.
            s_any = s_all
            rr_any = _first_rr_all(retrieved, row.must_contain_all)
        bad = _must_not_violation(retrieved, row.must_not_contain)
        rr_all = _first_rr_all(retrieved, row.must_contain_all)

        per_query.append(
            QueryResult(
                gold_id=row.id,
                query=row.query,
                latency_ms=latency_ms,
                retrieved=retrieved,
                success_any_at_k=s_any,
                success_all_at_k=s_all,
                must_not_contain_violation=bad,
                reciprocal_rank_any=rr_any,
                reciprocal_rank_all=rr_all,
            )
        )

    n = len(per_query)
    success_any = sum(1 for x in per_query if x.success_any_at_k) / n if n else 0.0
    success_all = sum(1 for x in per_query if x.success_all_at_k) / n if n else 0.0
    mrr_any = sum(x.reciprocal_rank_any for x in per_query) / n if n else 0.0
    mrr_all = sum(x.reciprocal_rank_all for x in per_query) / n if n else 0.0
    viol = sum(1 for x in per_query if x.must_not_contain_violation) / n if n else 0.0

    return RagEvalReport(
        k=k,
        total=n,
        success_any_at_k=success_any,
        success_all_at_k=success_all,
        mrr_any=mrr_any,
        mrr_all=mrr_all,
        must_not_contain_violation_rate=viol,
        per_query=per_query,
        meta=meta or {},
    )
