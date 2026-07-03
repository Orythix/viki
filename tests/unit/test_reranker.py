"""Tests for the RAG second-stage reranker."""

from viki.core.reranker import LexicalReranker, get_reranker


def test_lexical_reranker_prefers_multi_term_coverage():
    r = LexicalReranker()
    candidates = [
        "The user likes coffee coffee coffee coffee coffee.",
        "The user drinks coffee every morning before coding sessions.",
        "Completely unrelated note about garden tools and compost.",
    ]
    out = r.rerank("what does the user drink in the morning", candidates, top_k=2)
    assert out[0] == candidates[1]
    assert candidates[2] not in out


def test_lexical_reranker_empty_and_short():
    r = LexicalReranker()
    assert r.rerank("query", [], top_k=3) == []
    assert r.rerank("", ["a", "b"], top_k=1) == ["a"]


def test_lexical_reranker_respects_top_k():
    r = LexicalReranker()
    cands = [f"lesson about topic {i} and deployment" for i in range(10)]
    out = r.rerank("deployment topic", cands, top_k=4)
    assert len(out) == 4


def test_get_reranker_returns_working_instance():
    r = get_reranker()
    out = r.rerank("docker port", ["uses docker on port 8080", "likes tea"], top_k=1)
    assert out == ["uses docker on port 8080"]


def test_learning_module_rerank_hook():
    """LearningModule._rerank_lessons trims and reorders candidates."""
    import tempfile

    from viki.core.knowledge_ingestion import LearningModule

    with tempfile.TemporaryDirectory() as d:
        lm = LearningModule(data_dir=d)
        cands = [
            "note about compost bins",
            "the api server binds to port 9001 in production",
            "misc trivia entry",
        ]
        out = lm._rerank_lessons("which port does the api server use", cands, limit=1)
        assert out == ["the api server binds to port 9001 in production"]
        lm.close()
