"""Second-stage reranking for RAG retrieval.

The vector/BM25 backend retrieves a generous candidate set; a reranker then
re-scores query–candidate *pairs* for a much sharper top-k. Two
implementations:

- ``CrossEncoderReranker`` — a sentence-transformers cross-encoder
  (highest quality; used when the model stack is installed).
- ``LexicalReranker`` — dependency-free BM25-style token scoring with a
  coverage bonus. Always available; the automatic fallback.

Use :func:`get_reranker` to obtain the best available implementation.
"""

from __future__ import annotations

import math
import re
from typing import Protocol

from viki.config.logger import viki_logger

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_DEFAULT_CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class Reranker(Protocol):
    """Scores candidates against a query and returns them re-ordered."""

    def rerank(self, query: str, candidates: list[str], top_k: int = 5) -> list[str]: ...


class LexicalReranker:
    """BM25-style lexical reranker with query-coverage bonus.

    No ML dependencies. Robust for the short factual "lessons" VIKI stores:
    rewards candidates that cover more distinct query terms rather than
    repeating one term often.
    """

    k1 = 1.5
    b = 0.75

    def rerank(self, query: str, candidates: list[str], top_k: int = 5) -> list[str]:
        if not candidates:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return candidates[:top_k]

        docs = [_tokenize(c) for c in candidates]
        n = len(docs)
        avg_len = sum(len(d) for d in docs) / max(n, 1) or 1.0

        # document frequencies over the candidate set
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1

        q_set = set(q_tokens)
        scored: list[tuple[float, int]] = []
        for i, d in enumerate(docs):
            tf: dict[str, int] = {}
            for t in d:
                tf[t] = tf.get(t, 0) + 1
            score = 0.0
            matched = 0
            for t in q_set:
                if t not in tf:
                    continue
                matched += 1
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                denom = tf[t] + self.k1 * (1 - self.b + self.b * len(d) / avg_len)
                score += idf * (tf[t] * (self.k1 + 1)) / denom
            # coverage bonus: fraction of distinct query terms present
            score *= 1.0 + matched / len(q_set)
            scored.append((score, i))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return [candidates[i] for _, i in scored[:top_k]]


class CrossEncoderReranker:
    """Cross-encoder reranker (sentence-transformers).

    Raises ``ImportError`` if the stack is missing — use :func:`get_reranker`
    for automatic fallback.
    """

    def __init__(self, model_name: str = _DEFAULT_CROSS_ENCODER):
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)
        self.model_name = model_name

    def rerank(self, query: str, candidates: list[str], top_k: int = 5) -> list[str]:
        if not candidates:
            return []
        scores = self._model.predict([(query, c) for c in candidates])
        order = sorted(range(len(candidates)), key=lambda i: -float(scores[i]))
        return [candidates[i] for i in order[:top_k]]


_cached: Reranker | None = None


def get_reranker(prefer_cross_encoder: bool = True) -> Reranker:
    """Return the best available reranker (cached)."""
    global _cached
    if _cached is not None:
        return _cached
    if prefer_cross_encoder:
        try:
            _cached = CrossEncoderReranker()
            viki_logger.info("Reranker: using cross-encoder '%s'.", _DEFAULT_CROSS_ENCODER)
            return _cached
        except Exception as e:
            viki_logger.info("Reranker: cross-encoder unavailable (%s); using lexical.", e)
    _cached = LexicalReranker()
    return _cached
