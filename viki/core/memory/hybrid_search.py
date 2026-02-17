"""
QMD-style hybrid memory search: BM25 (keyword) + vector (episodic) + optional LLM rerank.
Used by recall_skill and can be wired into get_full_context for richer retrieval.
"""
import re
from typing import List, Dict, Any, Optional

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", (text or "").lower())


async def search_memory(
    controller: Any,  # VIKIController
    query: str,
    limit: int = 10,
    rerank: bool = False,
) -> List[str]:
    """
    Hybrid search over lessons (learning) and episodic memory.
    Combines keyword (BM25) and existing semantic retrieval, optionally reranks with LLM.
    """
    if not controller:
        return []
    query_lower = (query or "").lower()
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

    # 3) BM25 over combined docs (if available)
    if HAS_BM25 and combined:
        tokenized = [_tokenize(d) for d in combined]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(_tokenize(query))
        indexed = list(zip(scores, combined))
        indexed.sort(key=lambda x: -x[0])
        combined = [c for _, c in indexed if (c and c.strip())][: limit * 2]
    else:
        # Simple keyword overlap score
        q_tokens = set(_tokenize(query))
        def score(d: str):
            t = set(_tokenize(d))
            return len(q_tokens & t) / (len(q_tokens) + 1e-6)
        combined = sorted(combined, key=score, reverse=True)[: limit * 2]

    results = [c.strip() for c in combined if c.strip()][:limit]

    # 4) Optional LLM rerank: ask model to return indices in relevance order
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
            from viki.config.logger import viki_logger
            viki_logger.debug("Hybrid search rerank: %s", e)

    return results[:limit]
