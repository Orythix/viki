"""
Dream consolidation v2 — semantic fact summarization during idle cycles.

Extends DreamModule with:
  - Embedding-cluster deduplication of near-duplicate lessons
  - Contradiction resolution (keep provenance)
  - Summarization of related episodes into semantic facts
  - Confidence decay for stale, low-access lessons
"""

from __future__ import annotations

import json
import math
import time
from typing import Any, cast

from viki.config.logger import viki_logger


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-9 or nb <= 1e-9:
        return 0.0
    return dot / (na * nb)


def _token_jaccard(a: str, b: str) -> float:
    ta = set((a or "").lower().split())
    tb = set((b or "").lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


class DreamConsolidator:
    """
    Advanced dream consolidation for semantic memory.

    Designed to be called from DreamModule during idle cycles.
    """

    def __init__(
        self,
        learning_module: Any,
        model_router: Any | None = None,
        similarity_threshold: float = 0.88,
    ):
        self._lm = learning_module
        self._router = model_router
        self._similarity_threshold = similarity_threshold

    async def consolidate(self) -> dict[str, int]:
        """Run all consolidation passes. Returns counts of actions taken."""
        result: dict[str, int] = {
            "deduplicated": 0,
            "contradictions_resolved": 0,
            "episodes_summarized": 0,
            "stale_decayed": 0,
        }

        result["deduplicated"] = await self._deduplicate_lessons()
        result["contradictions_resolved"] = await self._resolve_contradictions()
        result["episodes_summarized"] = await self._summarize_episodes()
        result["stale_decayed"] = self._decay_stale_confidence()

        if any(result.values()):
            viki_logger.info("DreamConsolidator: %s", result)
        return result

    def _embed_texts(self, texts: list[str]) -> list[list[float] | None]:
        """Best-effort embeddings; None entries fall back to lexical clustering."""
        try:
            from viki.core.embeddings import get_encoder

            enc = get_encoder()
            if enc is None:
                return [None] * len(texts)
            vectors = enc.encode(texts, show_progress_bar=False)
            out: list[list[float] | None] = []
            for v in vectors:
                out.append([float(x) for x in v])
            return out
        except Exception as e:
            viki_logger.debug("DreamConsolidator: embeddings unavailable: %s", e)
            return [None] * len(texts)

    async def _deduplicate_lessons(self) -> int:
        """
        Merge near-duplicate lessons via embedding clusters (cosine ≥ threshold).

        Falls back to token Jaccard when embeddings are unavailable — never the
        old first-100-characters prefix key.
        """
        if self._lm is None:
            return 0
        conn = getattr(self._lm, "conn", None)
        if conn is None:
            return 0

        cur = conn.cursor()
        cur.execute(
            "SELECT id, text_representation, access_count FROM lessons "
            "ORDER BY LENGTH(text_representation) DESC LIMIT 800"
        )
        rows = cur.fetchall()
        items: list[dict[str, Any]] = []
        for r in rows:
            text = (r["text_representation"] or "").strip()
            if len(text) < 10:
                continue
            items.append(
                {
                    "id": r["id"],
                    "text": text,
                    "access_count": int(r["access_count"] or 0),
                }
            )
        if len(items) < 2:
            return 0

        embeddings = self._embed_texts([it["text"] for it in items])
        for it, emb in zip(items, embeddings, strict=False):
            it["emb"] = emb

        # Greedy clustering: assign each item to first cluster centroid above threshold.
        clusters: list[list[dict[str, Any]]] = []
        for it in items:
            placed = False
            for cluster in clusters:
                rep = cluster[0]
                if it["emb"] is not None and rep.get("emb") is not None:
                    sim = _cosine(it["emb"], rep["emb"])
                else:
                    sim = _token_jaccard(it["text"], rep["text"])
                if sim >= self._similarity_threshold:
                    cluster.append(it)
                    placed = True
                    break
            if not placed:
                clusters.append([it])

        removed = 0
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            cluster.sort(key=lambda x: -x["access_count"])
            keeper = cluster[0]
            for dup in cluster[1:]:
                conn.execute(
                    "UPDATE lessons SET access_count = access_count + ? WHERE id = ?",
                    (dup["access_count"], keeper["id"]),
                )
                conn.execute("DELETE FROM lessons WHERE id = ?", (dup["id"],))
                conn.execute("DELETE FROM relationships WHERE lesson_id = ?", (dup["id"],))
                removed += 1

        if removed:
            conn.commit()
            viki_logger.info(
                "Dream: embedding-cluster deduplicated %d lessons (threshold=%.2f)",
                removed,
                self._similarity_threshold,
            )
        return removed

    async def _resolve_contradictions(self) -> int:
        """Find and flag contradictory lessons."""
        if self._lm is None:
            return 0
        try:
            from viki.core.contradiction import heuristic_contradiction_score
        except ImportError:
            return 0

        conn = getattr(self._lm, "conn", None)
        if conn is None:
            return 0

        cur = conn.cursor()
        cur.execute(
            "SELECT id, text_representation, reliability FROM lessons WHERE reliability < 0.9 ORDER BY created_at DESC LIMIT 500"
        )
        recent = cur.fetchall()

        resolved = 0
        for r in recent:
            cur.execute(
                "SELECT id, text_representation FROM lessons WHERE id != ? AND reliability > 0.5 LIMIT 200",
                (r["id"],),
            )
            for existing in cur.fetchall():
                score = heuristic_contradiction_score(
                    existing["text_representation"] or "", r["text_representation"] or ""
                )
                if score >= 0.7:
                    conn.execute(
                        "UPDATE lessons SET reliability = MAX(0.1, reliability - 0.2) WHERE id = ?",
                        (r["id"],),
                    )
                    resolved += 1
                    break

        if resolved:
            conn.commit()
        return resolved

    async def _summarize_episodes(self) -> int:
        """Summarize narrative episodes into semantic facts."""
        if self._lm is None or self._router is None:
            return 0

        conn = getattr(self._lm, "conn", None)
        if conn is None:
            return 0

        cur = conn.cursor()
        cur.execute("SELECT event FROM narratives ORDER BY timestamp DESC LIMIT 20")
        episodes = [r["event"] for r in cur.fetchall() if r["event"]]
        if len(episodes) < 3:
            return 0

        combined = "\n".join(f"- {ep}" for ep in episodes[:10])
        prompt = [
            {
                "role": "system",
                "content": (
                    'Summarize the following narrative episodes into 1-3 concise semantic facts. '
                    'Reply ONLY with a JSON array of strings. Example: ["User prefers working late at night"]'
                ),
            },
            {"role": "user", "content": combined},
        ]

        try:
            response = await self._router.chat(prompt)
            start = response.find("[")
            end = response.rfind("]")
            if start != -1 and end != -1:
                facts = json.loads(response[start : end + 1])
                count = 0
                for fact in facts:
                    if isinstance(fact, str) and len(fact) > 10:
                        self._lm.save_lesson(
                            fact=fact, trigger="dream_summary", source_task="dream_consolidation"
                        )
                        count += 1
                return count
        except Exception as e:
            viki_logger.debug("Dream summarization failed: %s", e)
        return 0

    def _decay_stale_confidence(self) -> int:
        """Reduce reliability of lessons not accessed in > 30 days (never decay pinned)."""
        if self._lm is None:
            return 0
        conn = getattr(self._lm, "conn", None)
        if conn is None:
            return 0

        now = time.time()
        max_age = 30 * 24 * 60 * 60
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE lessons SET reliability = MAX(0.3, reliability - 0.1) "
                "WHERE last_accessed < ? AND reliability > 0.3 AND COALESCE(pinned, 0) = 0",
                (now - max_age,),
            )
        except Exception:
            cur.execute(
                "UPDATE lessons SET reliability = MAX(0.3, reliability - 0.1) "
                "WHERE last_accessed < ? AND reliability > 0.3",
                (now - max_age,),
            )
        count = cur.rowcount
        if count:
            conn.commit()
        return cast("int", count)
