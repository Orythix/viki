"""
QMD-style hybrid memory search: BM25 (keyword) + vector (episodic) + optional LLM rerank.
Used by recall_skill and can be wired into get_full_context for richer retrieval.
"""
import hashlib
import re
from collections import OrderedDict
from typing import Any

try:
    from rank_bm25 import BM25Okapi

    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", (text or "").lower())


class _BM25Cache:
    """Reusable BM25 index to avoid rebuilding on every query."""

    def __init__(self, max_docs: int = 500):
        self._docs: list[str] = []
        self._bm25: Any = None
        self._max_docs = max_docs

    def build(self, docs: list[str]):
        if docs == self._docs:
            return self._bm25
        self._docs = docs[: self._max_docs]
        tokenized = [_tokenize(d) for d in self._docs]
        self._bm25 = BM25Okapi(tokenized)
        return self._bm25


_bm25_cache = _BM25Cache()

_LRU_CACHE: "OrderedDict[str, list[str]]" = OrderedDict()
_LRU_MAX = 128


def _cache_key(query: str, limit: int, rerank: bool) -> str:
    return hashlib.md5(f"{query}|{limit}|{rerank}".encode()).hexdigest()


async def search_memory(
    controller: Any,  # VIKIController
    query: str,
    limit: int = 10,
    rerank: bool = False,
    alpha: float = 0.5,
) -> list[str]:
    """
    Hybrid search over lessons (learning) and episodic memory.
    Combines keyword (BM25) and existing semantic retrieval, optionally reranks with LLM.

    Args:
        alpha: BM25 vs semantic weight (0 = pure semantic, 1 = pure BM25). Default 0.5 balanced.
    """
    if not controller:
        return []

    ck = _cache_key(query, limit, rerank)
    if ck in _LRU_CACHE:
        _LRU_CACHE.move_to_end(ck)
        return list(_LRU_CACHE[ck])

    (query or "").lower()
    # 1) Lessons (keyword/semantic from learning)
    lessons = controller.learning.get_relevant_lessons(query, limit=limit * 2)
    if not isinstance(lessons, list):
        lessons = [str(lessons)] if lessons else []
    # 2) Episodic (vector/semantic from narrative)
    episodic = controller.memory.episodic.retrieve_context(query, limit=limit * 2)
    if not isinstance(episodic, list):
        episodic = []
    doc_strs = []
    for e in episodic:
        if isinstance(e, dict):
            parts = [e.get("intent", ""), e.get("outcome", ""), e.get("trigger_context", "")]
            doc_strs.append(" | ".join(p for p in parts if p))
        else:
            doc_strs.append(str(e))
    combined = list(lessons) + doc_strs
    if not combined:
        return []

    # 3) BM25 over combined docs (if available) with configurable alpha
    if HAS_BM25 and combined:
        bm25 = _bm25_cache.build(combined)
        bm25_scores = bm25.get_scores(_tokenize(query))
        max_bm25 = max(bm25_scores) if bm25_scores else 1.0
        if max_bm25 == 0:
            max_bm25 = 1.0
        q_tokens = set(_tokenize(query))
        semantic_scores = []
        for d in combined:
            t = set(_tokenize(d))
            semantic_scores.append(len(q_tokens & t) / (len(q_tokens) + 1e-6))
        max_sem = max(semantic_scores) if semantic_scores else 1.0
        if max_sem == 0:
            max_sem = 1.0
        fused = [
            (
                alpha * (bm25_scores[i] / max_bm25) + (1 - alpha) * (semantic_scores[i] / max_sem),
                combined[i],
            )
            for i in range(len(combined))
        ]
        fused.sort(key=lambda x: -x[0])
        combined = [c for _, c in fused if (c and c.strip())][: limit * 2]
    else:
        # Simple keyword overlap score
        q_tokens = set(_tokenize(query))

        def score(d: str):
            t = set(_tokenize(d))
            return len(q_tokens & t) / (len(q_tokens) + 1e-6)

        combined = sorted(combined, key=score, reverse=True)[: limit * 2]

    results = [c.strip() for c in combined if c.strip()][:limit]

    # 4) Optional LLM rerank: ask model to return indices in relevance order
    if len(_LRU_CACHE) >= _LRU_MAX:
        _LRU_CACHE.popitem(last=False)
    _LRU_CACHE[ck] = list(results)

    if rerank and results and hasattr(controller, "model_router") and len(results) > 1:
        try:
            prompt = (
                f"Query: {query}\n\nRank these by relevance. "
                f"Return only the indices 0 to {len(results)-1} in order, one per line (e.g. 2\\n0\\n1):\n"
                + "\n".join(f"{i}. {r[:150]}" for i, r in enumerate(results))
            )
            model = controller.model_router.get_model(capabilities=["general"])
            messages = [{"role": "user", "content": prompt}]
            reply = await model.chat(messages, temperature=0.0)
            ordered = []
            for line in (reply or "").strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                # Parse leading number (e.g. "2" or "2.")
                num_str = re.match(r"^(\d+)", line)
                if num_str:
                    idx = int(num_str.group(1))
                    if 0 <= idx < len(results) and idx not in ordered:
                        ordered.append(idx)
            if len(ordered) == len(results):
                results = [results[i] for i in ordered]
            # else keep original order on parse failure
        except Exception as e:
            from config.logger import viki_logger

            viki_logger.debug("Hybrid search rerank: %s", e)

    return results[:limit]
