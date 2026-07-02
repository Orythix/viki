import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from viki.skills.builtins.memory_skill import MemorySkill


@pytest.fixture
def mock_controller():
    controller = MagicMock()
    # Mock LearningModule
    controller.learning.save_lesson = MagicMock()
    controller.learning.get_lessons = MagicMock(
        return_value=[{"id": "test-1", "source_task": "manual", "text_representation": "Test Fact"}]
    )
    controller.learning.delete_lesson = MagicMock(return_value=True)
    controller.learning.update_lesson = MagicMock(return_value=True)
    controller.learning.get_total_lesson_count = MagicMock(return_value=10)
    controller.learning.get_stable_lesson_count = MagicMock(return_value=5)
    controller.learning._vector_backend.backend_name = "NumpyBackend"

    # Mock HierarchicalMemory
    controller.memory.episodic.conn.cursor.return_value.fetchone.return_value = [20]
    controller.memory.episodic.consolidate = AsyncMock()

    # Mock WorkingMemory
    controller.memory.working.get_all_sessions = MagicMock(
        return_value=[{"session_id": "sess-1", "message_count": 5, "last_active": "2026-05-14"}]
    )

    return controller


@pytest.mark.asyncio
async def test_memory_save(mock_controller):
    skill = MemorySkill(mock_controller)
    result = await skill.execute(
        {"action": "save", "text": "Python is great", "category": "coding"}
    )
    assert "SUCCESS" in result
    mock_controller.learning.save_lesson.assert_called_once()


@pytest.mark.asyncio
async def test_memory_list(mock_controller):
    skill = MemorySkill(mock_controller)
    result = await skill.execute({"action": "list", "category": "manual"})
    assert "COLLECTION LIST" in result
    assert "test-1" in result
    mock_controller.learning.get_lessons.assert_called_once()


@pytest.mark.asyncio
async def test_memory_stats(mock_controller):
    skill = MemorySkill(mock_controller)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = str(Path(tmpdir) / "test_memory.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS episodes (id INTEGER PRIMARY KEY, content TEXT)")
        for i in range(20):
            conn.execute("INSERT INTO episodes (content) VALUES (?)", (f"episode_{i}",))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS semantic_knowledge (id INTEGER PRIMARY KEY, content TEXT)"
        )
        for i in range(5):
            conn.execute("INSERT INTO semantic_knowledge (content) VALUES (?)", (f"wisdom_{i}",))
        conn.commit()
        conn.close()
        mock_controller.memory.episodic.db_path = db_path
        result = await skill.execute({"action": "stats"})
    assert "Semantic Lessons: 10" in result
    assert "Episodic Moments: 20" in result
    assert "Active Sessions:  1" in result


@pytest.mark.asyncio
async def test_memory_delete(mock_controller):
    skill = MemorySkill(mock_controller)
    result = await skill.execute({"action": "delete", "id": "test-1"})
    assert "SUCCESS" in result
    mock_controller.learning.delete_lesson.assert_called_with("test-1")


@pytest.mark.asyncio
async def test_memory_consolidate(mock_controller):
    skill = MemorySkill(mock_controller)
    result = await skill.execute({"action": "consolidate"})
    assert "Dream Cycle complete" in result
    mock_controller.memory.episodic.consolidate.assert_called_once()


@pytest.mark.asyncio
async def test_memory_sessions(mock_controller):
    skill = MemorySkill(mock_controller)
    result = await skill.execute({"action": "sessions"})
    assert "ACTIVE SESSIONS" in result
    assert "sess-1" in result
