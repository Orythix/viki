"""Tests for memory systems."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))  # noqa: E402

from viki.core.memory import EpisodicMemory, NarrativeIdentity, WorkingMemory  # noqa: E402


class TestWorkingMemory:
    """Test WorkingMemory."""

    def test_add_and_get_messages(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            config = {"memory": {"short_term_limit": 15}, "system": {"data_dir": tmpdir}}
            db_path = str(Path(tmpdir) / "working.db")
            db = WorkingMemory(config, db_path=db_path)
            try:
                db.add_message("user", "Hello", session_id="test")
                db.add_message("assistant", "Hi there!", session_id="test")
                db.add_message("user", "How are you?", session_id="test")

                trace = db.get_trace(session_id="test")
                assert len(trace) == 3
                assert trace[0]["role"] == "user"
                assert trace[0]["content"] == "Hello"
                assert trace[2]["role"] == "user"
                assert trace[2]["content"] == "How are you?"
            finally:
                db.close()

    def test_session_isolation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            config = {"memory": {"short_term_limit": 15}, "system": {"data_dir": tmpdir}}
            db_path = str(Path(tmpdir) / "working.db")
            db = WorkingMemory(config, db_path=db_path)
            try:
                db.add_message("user", "Session A msg", session_id="session_a")
                db.add_message("user", "Session B msg", session_id="session_b")

                trace_a = db.get_trace(session_id="session_a")
                trace_b = db.get_trace(session_id="session_b")
                assert len(trace_a) == 1
                assert len(trace_b) == 1
                assert trace_a[0]["content"] == "Session A msg"
                assert trace_b[0]["content"] == "Session B msg"
            finally:
                db.close()


class TestEpisodicMemory:
    """Test EpisodicMemory (NarrativeMemory)."""

    def test_store_and_recall_episode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = EpisodicMemory(tmpdir)
            try:
                db.add_episode(
                    context="interaction",
                    intent="ask about project",
                    plan={},
                    action="explain structure",
                    outcome="user understood",
                    confidence=0.8,
                )

                episodes = db.retrieve_context(current_intent="project", limit=5)
                assert len(episodes) >= 1
            finally:
                db.close()


class TestNarrativeIdentity:
    """Test NarrativeIdentity."""

    def test_update_anchor_and_get_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            identity = NarrativeIdentity(tmpdir)
            try:
                identity.update_anchor("test_name", "TestUser", "anchor")
                identity.update_anchor("test_role", "Developer", "anchor")

                prompt = identity.get_identity_prompt()
                assert "TestUser" in prompt or "TestUser" in str(identity.get_anchors())
            finally:
                identity.close()
