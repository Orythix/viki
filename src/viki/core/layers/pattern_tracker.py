"""Tracks successful input-to-action patterns for REFLEX promotion."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from viki.config.logger import viki_logger


class PatternTracker:
    """Tracks successful input->action patterns for potential REFLEX promotion.

    Memory-bounded: caps in-memory entries at `max_patterns` and evicts the
    least-recently-seen rows. Saves are debounced (every `save_every` writes)
    so that high-throughput hot paths don't pin a low-end disk with constant
    JSON dumps.
    """

    DEFAULT_MAX_PATTERNS = int(os.environ.get("VIKI_PATTERN_TRACKER_MAX", "5000"))
    DEFAULT_SAVE_EVERY = int(os.environ.get("VIKI_PATTERN_TRACKER_SAVE_EVERY", "10"))

    def __init__(
        self,
        data_dir: str | None = None,
        max_patterns: int | None = None,
        save_every: int | None = None,
    ):
        self.patterns: dict[str, dict[str, Any]] = {}
        self.data_dir = data_dir
        self.max_patterns = int(max_patterns or self.DEFAULT_MAX_PATTERNS)
        self.save_every = max(1, int(save_every or self.DEFAULT_SAVE_EVERY))
        self._writes_since_save = 0
        if data_dir:
            self._load_patterns()

    def record_success(self, user_input: str, skill_name: str, params: dict, confidence: float):
        key = self._normalize(user_input)
        if key not in self.patterns:
            self.patterns[key] = {
                "skill": skill_name,
                "params": params,
                "count": 0,
                "total_confidence": 0.0,
                "first_seen": time.time(),
            }
        self.patterns[key]["count"] += 1
        self.patterns[key]["total_confidence"] += confidence
        self.patterns[key]["last_seen"] = time.time()
        self._evict_if_needed()
        self._writes_since_save += 1
        if self._writes_since_save >= self.save_every:
            self._writes_since_save = 0
            self._save_patterns()

    def _evict_if_needed(self) -> None:
        if len(self.patterns) <= self.max_patterns:
            return
        excess = len(self.patterns) - self.max_patterns
        ordered = sorted(self.patterns.items(), key=lambda kv: kv[1].get("last_seen", 0))
        for k, _ in ordered[:excess]:
            self.patterns.pop(k, None)

    def get_reflex_candidates(
        self, min_count: int = 3, min_avg_confidence: float = 0.7
    ) -> list[dict[str, Any]]:
        candidates = []
        for input_pattern, data in self.patterns.items():
            count = data["count"]
            avg_conf = data["total_confidence"] / count if count > 0 else 0
            if count >= min_count and avg_conf >= min_avg_confidence:
                candidates.append(
                    {
                        "input": input_pattern,
                        "skill": data["skill"],
                        "params": data["params"],
                        "count": count,
                        "avg_confidence": round(avg_conf, 2),
                    }
                )
        return candidates

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().strip().split())

    def _save_patterns(self):
        if not self.data_dir:
            return
        os.makedirs(self.data_dir, exist_ok=True)
        path = os.path.join(self.data_dir, "pattern_tracker.json")
        try:
            with open(path, "w") as f:
                json.dump(self.patterns, f, indent=2)
        except Exception as e:
            viki_logger.warning(f"Failed to save pattern tracker: {e}")

    def _load_patterns(self):
        if not self.data_dir:
            return
        path = os.path.join(self.data_dir, "pattern_tracker.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self.patterns = json.load(f)
                viki_logger.info(f"PatternTracker: Loaded {len(self.patterns)} patterns from disk")
            except Exception as e:
                viki_logger.warning(f"Failed to load pattern tracker: {e}")
