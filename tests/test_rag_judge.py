"""Tests for optional Ollama RAG judge (parsing + report enrichment)."""
from __future__ import annotations

from unittest.mock import patch

from viki.eval.rag_eval import GoldRow, QueryResult, RagEvalReport
from viki.eval.rag_judge import _parse_judge_json, enrich_report_with_ollama_judge, run_ollama_judge


def test_parse_judge_json_plain():
    d = _parse_judge_json('{"relevance": 0.8, "covers_expected": true, "rationale": "ok"}')
    assert d["relevance"] == 0.8
    assert d["covers_expected"] is True


def test_parse_judge_json_fenced():
    raw = 'Here you go:\n```json\n{"relevance": 1, "covers_expected": false, "rationale": "x"}\n```'
    d = _parse_judge_json(raw)
    assert d["relevance"] == 1


def test_enrich_report_mocked():
    report = RagEvalReport(
        k=2,
        total=1,
        success_any_at_k=1.0,
        success_all_at_k=1.0,
        mrr_any=1.0,
        mrr_all=1.0,
        must_not_contain_violation_rate=0.0,
        per_query=[
            QueryResult(
                gold_id="g1",
                query="q1",
                latency_ms=1.0,
                retrieved=["chunk a", "chunk b"],
                success_any_at_k=True,
                success_all_at_k=True,
                must_not_contain_violation=False,
                reciprocal_rank_any=1.0,
                reciprocal_rank_all=1.0,
            )
        ],
        meta={},
    )
    gold = [GoldRow(id="g1", query="q1", must_contain_any=["Angular"])]

    fake = type(
        "JR",
        (),
        {
            "relevance": 0.9,
            "covers_expected": True,
            "rationale": "test",
            "raw_response": "{}",
            "latency_ms": 5.0,
            "error": None,
        },
    )()

    with patch("viki.eval.rag_judge.run_ollama_judge", return_value=fake):
        enrich_report_with_ollama_judge(
            report,
            gold,
            ollama_url="http://127.0.0.1:11434",
            model="dummy",
            timeout_s=1.0,
        )

    assert report.judge_mean_relevance == 0.9
    assert report.judge_covers_expected_rate == 1.0
    assert report.per_query[0].judge_relevance == 0.9
    assert report.per_query[0].judge_covers_expected is True
    assert "judge" in report.meta


def test_run_ollama_judge_parse_only():
    mock_resp = b'{"message":{"content":"{\\"relevance\\":0.5,\\"covers_expected\\":true,\\"rationale\\":\\"fine\\"}"}}\n'

    class FakeResp:
        def read(self):
            return mock_resp

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        return FakeResp()

    with patch("urllib.request.urlopen", fake_urlopen):
        jr = run_ollama_judge(
            query="hello",
            retrieved=["a"],
            expected_phrases=["x"],
            ollama_url="http://127.0.0.1:11434",
            model="m",
            timeout_s=5.0,
        )
    assert jr.relevance == 0.5
    assert jr.covers_expected is True
    assert jr.error is None
