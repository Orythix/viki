"""
Dream consolidation v2 — semantic fact summarization during idle cycles.

Extends DreamModule with:
  - Deduplication of near-duplicate lessons
  - Contradiction resolution (keep provenance)
  - Summarization of related episodes into semantic facts
  - Confidence decay for stale, low-access lessons
"""

from __future__ import annotations

import json
import time
from typing import Any, cast

from viki.config.logger import viki_logger


class DreamConsolidator:
    """
    Advanced dream consolidation for semantic memory.

    Designed to be called from DreamModule during idle cycles.
    """

    def __init__(self, learning_module: Any, model_router: Any | None = None):
        self._lm = learning_module
        self._router = model_router

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

    async def _deduplicate_lessons(self) -> int:
        """Merge lessons with near-identical text_representation."""
        if self._lm is None:
            return 0
        conn = getattr(self._lm, "conn", None)
        if conn is None:
            return 0

        cur = conn.cursor()
        cur.execute(
            "SELECT id, text_representation, access_count FROM lessons ORDER BY LENGTH(text_representation) DESC"
        )
        rows = cur.fetchall()

        # Group by normalized text (lowercase, stripped)
        groups: dict[str, list[dict]] = {}
        for r in rows:
            norm = (r["text_representation"] or "").strip().lower()
            if len(norm) < 10:
                continue
            base = norm[:100]  # Compare first ~100 chars
            groups.setdefault(base, []).append(
                {
                    "id": r["id"],
                    "text": r["text_representation"],
                    "access_count": r["access_count"],
                }
            )

        removed = 0
        for _base, group in groups.items():
            if len(group) <= 1:
                continue
            # Keep the one with highest access_count, delete the rest
            group.sort(key=lambda x: -x["access_count"])
            keeper = group[0]
            for dup in group[1:]:
                # Merge access counts
                conn.execute(
                    "UPDATE lessons SET access_count = access_count + ? WHERE id = ?",
                    (dup["access_count"], keeper["id"]),
                )
                conn.execute("DELETE FROM lessons WHERE id = ?", (dup["id"],))
                conn.execute("DELETE FROM relationships WHERE lesson_id = ?", (dup["id"],))
                removed += 1

        if removed:
            conn.commit()
            viki_logger.info("Dream: deduplicated %d lessons", removed)
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
                "content": 'Summarize the following narrative episodes into 1-3 concise semantic facts. Reply ONLY with a JSON array of strings. Example: ["User prefers working late at night"]',
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
        """Reduce reliability of lessons not accessed in > 30 days."""
        if self._lm is None:
            return 0
        conn = getattr(self._lm, "conn", None)
        if conn is None:
            return 0

        now = time.time()
        max_age = 30 * 24 * 60 * 60
        cur = conn.cursor()
        cur.execute(
            "UPDATE lessons SET reliability = MAX(0.3, reliability - 0.1) WHERE last_accessed < ? AND reliability > 0.3",
            (now - max_age,),
        )
        count = cur.rowcount
        if count:
            conn.commit()
        return cast("int", count)
