"""Tests for CurriculumBuilder."""

from __future__ import annotations

from pathlib import Path

import pytest

from viki.core.curriculum_builder import CurriculumBuilder, CurriculumTopic


class TestCurriculumTopic:
    def test_defaults(self) -> None:
        t = CurriculumTopic(name="test-topic")
        assert t.name == "test-topic"
        assert t.status == "identified"
        assert t.priority == 0.5
        assert t.source == "knowledge_gap"


class TestCurriculumBuilder:
    @pytest.fixture
    def controller(self) -> object:
        class _StubKGD:
            def __init__(self) -> None:
                self.gaps: list[str] = []

            def get_gaps(self, limit: int = 10) -> list[str]:
                return self.gaps

        class _StubLM:
            pass

        class _StubController:
            def __init__(self) -> None:
                self.learning_module = _StubLM()
                self.knowledge_gap_detector = _StubKGD()
                self.system_settings = {}

        return _StubController()

    @pytest.fixture
    def builder(self, controller: object, tmp_path: Path) -> CurriculumBuilder:
        controller.system_settings = {"data_dir": str(tmp_path / "viki_curriculum")}  # type: ignore[attr-defined]
        return CurriculumBuilder(controller)

    def test_no_gaps_returns_empty(self, builder: CurriculumBuilder) -> None:
        import asyncio

        result = asyncio.run(builder.run_pipeline())
        assert result["gaps_found"] == 0
        assert result["topics_created"] == 0
        assert result["lessons_added"] == 0

    def test_gap_creates_topic(self, controller: object, builder: CurriculumBuilder) -> None:
        controller.knowledge_gap_detector.gaps = ["What is quantum computing"]  # type: ignore[attr-defined]
        import asyncio

        result = asyncio.run(builder.run_pipeline())
        assert result["gaps_found"] == 1
        assert result["topics_created"] == 1
        topics = builder.get_pending_topics()
        assert len(topics) == 1
        assert "quantum" in topics[0].name.lower()

    def test_duplicate_gap_skipped(self, builder: CurriculumBuilder) -> None:
        builder._topics.append(
            CurriculumTopic(
                name="quantum computing",
                description="What is quantum computing",
                created_at=0,
            )
        )
        topic = builder._topic_from_gap("Quantum computing")
        assert topic is None

    def test_short_gap_skipped(self, builder: CurriculumBuilder) -> None:
        topic = builder._topic_from_gap("abc")
        assert topic is None

    def test_get_stats_empty(self, builder: CurriculumBuilder) -> None:
        stats = builder.get_stats()
        assert stats["total_topics"] == 0
        assert stats["completed"] == 0

    def test_get_stats_with_topics(self, builder: CurriculumBuilder) -> None:
        builder._topics.append(
            CurriculumTopic(
                name="t1",
                status="ingested",
                lessons_created=3,
                created_at=0,
            )
        )
        builder._topics.append(
            CurriculumTopic(
                name="t2",
                status="trained",
                lessons_created=5,
                created_at=0,
                completed_at=100,
            )
        )
        stats = builder.get_stats()
        assert stats["total_topics"] == 2
        assert stats["completed"] == 1
        assert stats["total_lessons"] == 8

    def test_pending_topics_excludes_trained(self, builder: CurriculumBuilder) -> None:
        builder._topics.append(CurriculumTopic(name="active", status="ingested", created_at=0))
        builder._topics.append(CurriculumTopic(name="done", status="trained", created_at=0))
        pending = builder.get_pending_topics()
        assert len(pending) == 1
        assert pending[0].name == "active"

    def test_persistence_saves_and_loads(self, controller: object, tmp_path: Path) -> None:
        data_dir = str(tmp_path / "persist_curriculum")
        controller.system_settings = {"data_dir": data_dir}  # type: ignore[attr-defined]
        b1 = CurriculumBuilder(controller)
        b1._topics.append(CurriculumTopic(name="saved", description="test", created_at=0))
        b1._save()

        b2 = CurriculumBuilder(controller)
        assert len(b2._topics) == 1
        assert b2._topics[0].name == "saved"

    def test_empty_run_does_not_crash(self, builder: CurriculumBuilder) -> None:
        import asyncio

        result = asyncio.run(builder.run_pipeline(max_topics=0))
        assert result["gaps_found"] == 0
