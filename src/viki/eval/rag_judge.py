"""
Optional LLM-as-judge for RAG retrieval (local LM Studio).

Why: substring gold checks miss semantic relevance; a small local model can score
whether retrieved chunks *support* answering the query and *mention* expected concepts.

Security: sends query + retrieved text to LM Studio on localhost (or your URL only).
Do not point at untrusted remotes with sensitive corpus text.

Default: off — keeps CI and quick eval runs fast and deterministic.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from viki.config.logger import viki_logger
from viki.eval.rag_eval import GoldRow, RagEvalReport


@dataclass
class JudgeResult:
    relevance: float
    covers_expected: bool
    rationale: str
    raw_response: str
    latency_ms: float
    error: str | None = None


_JSON_BLOCK = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _build_context_snippet(chunks: Sequence[str], max_total: int = 6000) -> str:
    parts: list[str] = []
    n = 0
    for i, c in enumerate(chunks):
        block = f"[{i + 1}] {(c or '').strip()}\n"
        if n + len(block) > max_total:
            parts.append(f"[{i + 1}] {(c or '')[: max(0, max_total - n - 20)]}…\n")
            break
        parts.append(block)
        n += len(block)
    return "".join(parts).strip()


def _parse_judge_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    # Strip common ```json fences
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
        if m:
            text = m.group(1).strip()
    try:
        return cast("dict[str, Any]", json.loads(text))
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK.search(text)
    if m:
        try:
            return cast("dict[str, Any]", json.loads(m.group(0)))
        except json.JSONDecodeError:
            pass
    raise ValueError("model did not return valid JSON")


def run_local_judge(
    *,
    query: str,
    retrieved: Sequence[str],
    expected_phrases: Sequence[str],
    base_url: str,
    model: str,
    timeout_s: float = 60.0,
    max_context_chars: int = 6000,
) -> JudgeResult:
    """
    Ask local LLM (OpenAI-compatible /v1/chat/completions) to score retrieval quality.
    Returns structured JudgeResult.
    """
    t0 = time.perf_counter()
    ctx = _build_context_snippet(retrieved, max_total=max_context_chars)
    hints = ", ".join(expected_phrases) if expected_phrases else "(none specified)"
    system = (
        "You are a retrieval evaluator for RAG systems. Reply with ONLY a JSON object, no markdown.\n"
        'Schema: {"relevance": number 0-1, "covers_expected": boolean, "rationale": string under 200 chars}\n'
        "- relevance: how well the passages help answer the user query (not fluency).\n"
        "- covers_expected: true if the passages clearly support the expected concepts/phrases when provided.\n"
        "If passages are empty, relevance 0 and covers_expected false."
    )
    user = f"USER QUERY:\n{query}\n\nEXPECTED CONCEPTS (gold hints):\n{hints}\n\nRETRIEVED PASSAGES:\n{ctx}\n"

    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
    }
    raw = ""
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        # OpenAI-compatible response: choices[0].message.content
        choices = data.get("choices") or []
        msg = (choices[0].get("message") or {}).get("content") if choices else ""
        parsed = _parse_judge_json(msg)
        rel = float(parsed.get("relevance", 0))
        rel = max(0.0, min(1.0, rel))
        cov = bool(parsed.get("covers_expected", False))
        rat = str(parsed.get("rationale") or "")[:500]
        ms = (time.perf_counter() - t0) * 1000.0
        return JudgeResult(
            relevance=rel,
            covers_expected=cov,
            rationale=rat,
            raw_response=msg[:2000],
            latency_ms=ms,
            error=None,
        )
    except urllib.error.HTTPError as e:
        ms = (time.perf_counter() - t0) * 1000.0
        err = f"HTTP {e.code}: {e.reason}"
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        viki_logger.warning("rag_judge: %s", err)
        return JudgeResult(0.0, False, "", raw[:500], ms, error=err)
    except urllib.error.URLError as e:
        ms = (time.perf_counter() - t0) * 1000.0
        err = f"URL error: {e.reason}"
        viki_logger.warning("rag_judge: %s", err)
        return JudgeResult(0.0, False, "", raw[:500], ms, error=err)
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000.0
        err = str(e)
        viki_logger.warning("rag_judge failed: %s", e)
        return JudgeResult(0.0, False, "", raw[:500], ms, error=err)


def enrich_report_with_local_judge(
    report: RagEvalReport,
    gold_rows: Sequence[GoldRow],
    *,
    base_url: str,
    model: str,
    timeout_s: float = 60.0,
    max_context_chars: int = 6000,
) -> RagEvalReport:
    """
    Mutates report.per_query entries in place with judge fields; updates report.meta aggregates.
    """
    gold_by_id = {g.id: g for g in gold_rows}
    relevances: list[float] = []
    covers: list[bool] = []
    errors = 0

    for q in report.per_query:
        g = gold_by_id.get(q.gold_id)
        expected: list[str] = []
        if g:
            expected = list(g.must_contain_any) + list(g.must_contain_all)
        jr = run_local_judge(
            query=q.query,
            retrieved=q.retrieved,
            expected_phrases=expected,
            base_url=base_url,
            model=model,
            timeout_s=timeout_s,
            max_context_chars=max_context_chars,
        )
        q.judge_relevance = jr.relevance
        q.judge_covers_expected = jr.covers_expected
        q.judge_rationale = jr.rationale
        q.judge_latency_ms = jr.latency_ms
        q.judge_error = jr.error
        if jr.error:
            errors += 1
        else:
            relevances.append(jr.relevance)
            covers.append(jr.covers_expected)

    n = len(report.per_query)
    report.judge_mean_relevance = sum(relevances) / len(relevances) if relevances else None
    report.judge_covers_expected_rate = (
        sum(1 for c in covers if c) / len(covers) if covers else None
    )
    report.meta = dict(report.meta)
    report.meta["judge"] = {
        "base_url": base_url,
        "model": model,
        "queries_judged": n,
        "judge_errors": errors,
        "mean_relevance": report.judge_mean_relevance,
        "covers_expected_rate": report.judge_covers_expected_rate,
    }
    return report
