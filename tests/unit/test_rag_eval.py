"""Tests for offline RAG retrieval evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from viki.core.knowledge_ingestion import LearningModule
from viki.eval.rag_eval import (
    GoldRow,
    evaluate_rag_retrieval,
    load_gold_jsonl,
)


@pytest.fixture
def no_encoder(monkeypatch):
    monkeypatch.setattr("viki.core.embeddings.get_encoder", lambda: None)


@pytest.fixture
def lm_with_lessons(tmp_path, no_encoder):
    lm = LearningModule(str(tmp_path))
    lm.save_lesson(
        trigger="t1",
        fact="Sachin leads frontend with Angular and TypeScript in production.",
        source_task="test",
    )
    lm.save_lesson(
        trigger="t2",
        fact="n8n provides hundreds of integrations for fair-code workflow automation.",
        source_task="test",
    )
    lm.save_lesson(
        trigger="t3",
        fact="Unrelated lesson about coffee brewing temperatures.",
        source_task="test",
    )
    return lm


def test_load_gold_jsonl(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text(
        json.dumps(
            {
                "id": "a",
                "query": "hello world",
                "must_contain_any": ["x"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows = load_gold_jsonl(p)
    assert len(rows) == 1
    assert rows[0].id == "a"


def test_load_gold_rejects_empty_constraints(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text(
        json.dumps({"id": "a", "query": "q", "must_contain_any": [], "must_contain_all": []})
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_gold_jsonl(p)


def test_eval_success_any_lexical(lm_with_lessons):
    gold = [
        GoldRow(
            id="q1",
            query="Who uses Angular for frontend leadership?",
            must_contain_any=["Angular", "Sachin"],
        )
    ]
    r = evaluate_rag_retrieval(lm_with_lessons, gold, k=3)
    assert r.total == 1
    assert r.success_any_at_k == 1.0
    assert r.per_query[0].success_any_at_k
    assert r.per_query[0].reciprocal_rank_any >= 1.0 / 3


def test_eval_must_contain_all(lm_with_lessons):
    gold = [
        GoldRow(
            id="q2",
            query="workflow automation integrations platform",
            must_contain_all=["n8n", "integrations"],
        )
    ]
    r = evaluate_rag_retrieval(lm_with_lessons, gold, k=2)
    assert r.success_all_at_k == 1.0


def test_eval_must_not_contain_violation(tmp_path, no_encoder):
    lm = LearningModule(str(tmp_path))
    lm.save_lesson(
        trigger="bad",
        fact="This line documents PoisonToken for abuse testing in the lab only.",
        source_task="test",
    )
    lm.save_lesson(
        trigger="good",
        fact="Clean Angular and TypeScript engineering guidelines.",
        source_task="test",
    )
    gold = [
        GoldRow(
            id="q3",
            query="Angular TypeScript engineering",
            must_contain_any=["Angular"],
            must_not_contain=["PoisonToken"],
        )
    ]
    r = evaluate_rag_retrieval(lm, gold, k=5)
    assert r.per_query[0].must_not_contain_violation


def test_example_fixture_loads():
    root = Path(__file__).resolve().parents[2]
    fixture = root / "src" / "viki" / "eval" / "fixtures" / "rag_gold.example.jsonl"
    rows = load_gold_jsonl(fixture)
    assert len(rows) == 3
