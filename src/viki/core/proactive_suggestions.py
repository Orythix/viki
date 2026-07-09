"""
Proactive suggestions with politeness budget.

VIKI may surface at most N proactive items per day, learned from acceptance
rate. Uses an overlay badge (not modal) to avoid interrupting flow.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from viki.config.logger import viki_logger


@dataclass
class Suggestion:
    """A proactive suggestion item."""

    id: str = ""
    title: str = ""
    description: str = ""
    category: str = "general"  # insight, reminder, tip, discovery
    priority: float = 0.5  # 0.0 – 1.0
    source: str = ""  # e.g., "knowledge_gap", "pattern_detection"
    context: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    expires_at: float = 0.0
    accepted: bool | None = None  # None = pending, True = accepted, False = dismissed


class ProactiveSuggestionEngine:
    """
    Manages proactive suggestions with a daily politeness budget.

    The engine learns from acceptance rate and adjusts daily suggestion
    count accordingly.  Suggestions are surfaced as overlay badges (not
    modals) to avoid interrupting user flow.
    """

    def __init__(
        self,
        data_dir: str = "./data",
        max_daily_suggestions: int = 5,
    ):
        self._data_dir = data_dir
        self._max_daily = max_daily_suggestions
        self._suggestions: list[Suggestion] = []
        self._history: list[Suggestion] = []
        self._today_count = 0
        self._last_date = ""
        self._persistence_path = os.path.join(data_dir, "suggestions.json")
        os.makedirs(data_dir, exist_ok=True)
        self._load()

    # ---- Public API ----

    def add_suggestion(
        self,
        title: str,
        description: str,
        category: str = "general",
        priority: float = 0.5,
        source: str = "",
        context: dict[str, Any] | None = None,
        ttl_hours: float = 24.0,
    ) -> str | None:
        """Add a suggestion if the daily budget allows. Returns suggestion ID or None."""
        if not self._has_budget():
            viki_logger.debug("ProactiveSuggestion: daily budget exhausted, dropping '%s'", title)
            return None

        import uuid

        now = time.time()
        sug = Suggestion(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            category=category,
            priority=priority,
            source=source,
            context=context or {},
            created_at=now,
            expires_at=now + ttl_hours * 3600,
        )
        self._suggestions.append(sug)
        self._today_count += 1
        self._save()
        viki_logger.info(
            "ProactiveSuggestion: added '%s' (%d/%d today)",
            title,
            self._today_count,
            self._max_daily,
        )
        return sug.id

    def get_pending(self, max_items: int = 3) -> list[Suggestion]:
        """Return pending, non-expired suggestions sorted by priority."""
        now = time.time()
        valid = [s for s in self._suggestions if s.accepted is None and s.expires_at > now]
        valid.sort(key=lambda s: -s.priority)
        return valid[:max_items]

    def accept(self, suggestion_id: str) -> bool:
        """Mark a suggestion as accepted."""
        for s in self._suggestions:
            if s.id == suggestion_id:
                s.accepted = True
                self._history.append(s)
                self._suggestions.remove(s)
                self._save()
                self._update_budget()
                return True
        return False

    def dismiss(self, suggestion_id: str) -> bool:
        """Dismiss a suggestion without accepting."""
        for s in self._suggestions:
            if s.id == suggestion_id:
                s.accepted = False
                self._history.append(s)
                self._suggestions.remove(s)
                self._save()
                return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Return acceptance statistics."""
        total = len(self._history)
        accepted = sum(1 for s in self._history if s.accepted)
        return {
            "total_suggestions": total,
            "accepted": accepted,
            "acceptance_rate": (accepted / total * 100) if total > 0 else 0.0,
            "daily_budget": self._max_daily,
            "today_count": self._today_count,
            "pending_count": len(self._suggestions),
        }

    # ---- Internal ----

    def _has_budget(self) -> bool:
        """Check if we have budget for another suggestion today."""
        self._check_date()
        return self._today_count < self._max_daily

    def _check_date(self) -> None:
        """Reset daily counter if date changed."""
        today = time.strftime("%Y-%m-%d")
        if today != self._last_date:
            self._today_count = 0
            self._last_date = today

    def _update_budget(self) -> None:
        """Adjust the daily budget based on recent acceptance rate."""
        recent = [s for s in self._history[-50:] if s.accepted is not None]
        if len(recent) < 10:
            return
        rate = sum(1 for s in recent if s.accepted) / len(recent)
        if rate > 0.6 and self._max_daily < 10:
            self._max_daily += 1
            viki_logger.info(
                "ProactiveSuggestion: increased daily budget to %d (acceptance rate: %.0f%%)",
                self._max_daily,
                rate * 100,
            )
        elif rate < 0.2 and self._max_daily > 1:
            self._max_daily = max(1, self._max_daily - 1)
            viki_logger.info(
                "ProactiveSuggestion: decreased daily budget to %d (acceptance rate: %.0f%%)",
                self._max_daily,
                rate * 100,
            )

    def _save(self) -> None:
        try:
            data = {
                "max_daily": self._max_daily,
                "today_count": self._today_count,
                "last_date": self._last_date,
                "suggestions": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "description": s.description,
                        "category": s.category,
                        "priority": s.priority,
                        "source": s.source,
                        "context": s.context,
                        "created_at": s.created_at,
                        "expires_at": s.expires_at,
                        "accepted": s.accepted,
                    }
                    for s in self._suggestions + self._history[-200:]
                ],
            }
            with open(self._persistence_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            viki_logger.error("ProactiveSuggestion: failed to save: %s", e)

    def _load(self) -> None:
        if not os.path.exists(self._persistence_path):
            return
        try:
            with open(self._persistence_path) as f:
                data = json.load(f)
            self._max_daily = data.get("max_daily", self._max_daily)
            self._today_count = data.get("today_count", 0)
            self._last_date = data.get("last_date", "")
            for item in data.get("suggestions", []):
                s = Suggestion(
                    id=item["id"],
                    title=item["title"],
                    description=item["description"],
                    category=item.get("category", "general"),
                    priority=item.get("priority", 0.5),
                    source=item.get("source", ""),
                    context=item.get("context", {}),
                    created_at=item.get("created_at", 0),
                    expires_at=item.get("expires_at", 0),
                    accepted=item.get("accepted"),
                )
                if s.accepted is None and s.expires_at > time.time():
                    self._suggestions.append(s)
                else:
                    self._history.append(s)
        except Exception as e:
            viki_logger.error("ProactiveSuggestion: failed to load: %s", e)
