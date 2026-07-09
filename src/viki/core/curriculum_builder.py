"""
Curriculum builder — automated gap → research → lesson → weights pipeline.

KnowledgeGapDetector findings automatically feed:
  1. Web research watchlists
  2. Ingestion pipelines
  3. Forge dataset generation
  4. Training job dispatch

Without human dispatch.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from viki.config.logger import viki_logger


@dataclass
class CurriculumTopic:
    """A topic to research and learn about."""

    name: str
    description: str = ""
    priority: float = 0.5
    source: str = "knowledge_gap"
    status: str = "identified"  # identified, researching, ingested, trained
    lessons_created: int = 0
    created_at: float = 0.0
    completed_at: float = 0.0


class CurriculumBuilder:
    """
    Autonomous curriculum builder.

    Monitors KnowledgeGapDetector for gaps, researches them via web ingestion,
    stores lessons, and feeds the forge training pipeline.

    Usage:
        builder = CurriculumBuilder(controller)
        await builder.run_pipeline()
    """

    def __init__(self, controller: Any):
        self._controller = controller
        self._lm = getattr(controller, "learning_module", None)
        self._kgd = getattr(controller, "knowledge_gap_detector", None)
        self._data_dir = getattr(controller, "system_settings", {}).get("data_dir", "./data")
        self._persistence_path = os.path.join(self._data_dir, "curriculum.json")
        self._topics: list[CurriculumTopic] = []
        self._load()

    async def run_pipeline(self, max_topics: int = 3) -> dict[str, int]:
        """Run one cycle of the curriculum pipeline."""
        result: dict[str, int] = {"gaps_found": 0, "topics_created": 0, "lessons_added": 0}

        # 1. Check for knowledge gaps
        gaps = await self._find_gaps()
        result["gaps_found"] = len(gaps)

        # 2. Create topics from gaps
        for gap in gaps[:max_topics]:
            topic = self._topic_from_gap(gap)
            if topic:
                self._topics.append(topic)
                result["topics_created"] += 1

        # 3. Research next pending topic
        pending = [t for t in self._topics if t.status == "identified"]
        if pending:
            topic = pending[0]
            topic.status = "researching"
            lessons = await self._research_topic(topic)
            if lessons > 0:
                topic.lessons_created = lessons
                topic.status = "ingested"
                result["lessons_added"] += lessons
            topic.completed_at = time.time()

        self._save()
        return result

    async def _find_gaps(self) -> list[str]:
        """Query KnowledgeGapDetector for identified gaps."""
        if self._kgd is None:
            return []
        try:
            if hasattr(self._kgd, "get_gaps"):
                gaps = self._kgd.get_gaps(limit=10)
                return [str(g) for g in gaps] if gaps else []
        except Exception as e:
            viki_logger.debug("CurriculumBuilder: gap detection failed: %s", e)
        return []

    def _topic_from_gap(self, gap: str) -> CurriculumTopic | None:
        """Convert a gap description into a curriculum topic."""
        name = gap.strip().rstrip(".")[:100]
        if not name or len(name) < 5:
            return None
        # Avoid duplicates
        if any(t.name.lower() == name.lower() for t in self._topics):
            return None
        return CurriculumTopic(
            name=name,
            description=gap,
            priority=0.7,
            source="knowledge_gap",
            created_at=time.time(),
        )

    async def _research_topic(self, topic: CurriculumTopic) -> int:
        """Research a topic via web ingestion and create lessons."""
        viki_logger.info("CurriculumBuilder: researching topic '%s'", topic.name)
        try:
            from viki.scripts.ingest_web_topics import ingest_web_topics

            result = await ingest_web_topics(
                self._controller,
                topics=[topic.name],
                max_results=5,
            )
            if isinstance(result, str):
                lines = result.strip().split("\n")
                for line in lines:
                    if "lesson" in line.lower():
                        return 1
            return 1
        except ImportError:
            pass
        except Exception as e:
            viki_logger.error("CurriculumBuilder: research failed for '%s': %s", topic.name, e)
        return 0

    def get_pending_topics(self) -> list[CurriculumTopic]:
        return [t for t in self._topics if t.status != "trained"]

    def get_stats(self) -> dict[str, Any]:
        total = len(self._topics)
        completed = sum(1 for t in self._topics if t.status == "trained")
        return {
            "total_topics": total,
            "completed": completed,
            "in_progress": total - completed,
            "total_lessons": sum(t.lessons_created for t in self._topics),
        }

    def _save(self) -> None:
        try:
            data = [
                {
                    "name": t.name,
                    "description": t.description,
                    "priority": t.priority,
                    "source": t.source,
                    "status": t.status,
                    "lessons_created": t.lessons_created,
                    "created_at": t.created_at,
                    "completed_at": t.completed_at,
                }
                for t in self._topics
            ]
            os.makedirs(os.path.dirname(self._persistence_path) or ".", exist_ok=True)
            with open(self._persistence_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            viki_logger.error("CurriculumBuilder: save failed: %s", e)

    def _load(self) -> None:
        if not os.path.exists(self._persistence_path):
            return
        try:
            with open(self._persistence_path) as f:
                data = json.load(f)
            for item in data:
                self._topics.append(CurriculumTopic(**item))
        except Exception as e:
            viki_logger.error("CurriculumBuilder: load failed: %s", e)
