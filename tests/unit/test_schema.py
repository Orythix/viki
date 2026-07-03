"""Tests for Pydantic schemas."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))  # noqa: E402

from viki.core.schema import ThoughtObject, VIKIResponse, VIKIResponseLite, WorldState  # noqa: E402


class TestVIKIResponseLite:
    """Test VIKIResponseLite schema."""

    def test_minimal_valid_response(self):
        """Minimal valid lite response should parse."""
        data = {"final_response": "Hello!", "action": None, "confidence": 0.8}
        resp = VIKIResponseLite(**data)
        assert resp.final_response == "Hello!"
        assert resp.confidence == 0.8

    def test_response_with_action(self):
        """Lite response with action should parse."""
        data = {
            "final_response": "I'll search for that.",
            "action": {"skill_name": "research", "parameters": {"query": "test"}},
            "confidence": 0.9,
        }
        resp = VIKIResponseLite(**data)
        assert resp.action is not None
        assert resp.action.skill_name == "research"

    def test_confidence_bounds(self):
        """Confidence should be bounded 0-1."""
        with pytest.raises(ValueError):
            VIKIResponseLite(final_response="test", confidence=1.5)
        with pytest.raises(ValueError):
            VIKIResponseLite(final_response="test", confidence=-0.1)

    def test_to_full_response_conversion(self):
        """Lite response should convert to full response."""
        lite = VIKIResponseLite(final_response="Test response", action=None, confidence=0.7)
        full = lite.to_full_response()
        assert isinstance(full, VIKIResponse)
        assert full.final_response == "Test response"
        assert full.final_thought.confidence == 0.7


class TestVIKIResponse:
    """Test full VIKIResponse schema."""

    def test_minimal_valid_response(self):
        """Minimal valid full response should parse."""
        data = {
            "final_thought": {
                "intent_summary": "Test",
                "primary_strategy": "Direct",
                "confidence": 0.7,
                "assumptions": [],
                "constraints": [],
                "rejected_strategies": [],
                "risk_score": 0.1,
            },
            "action": None,
            "final_response": "Test response",
            "internal_metacognition": None,
            "ensemble_trace": None,
            "sentiment": None,
            "intent_type": None,
            "needs_escalation": False,
        }
        resp = VIKIResponse(**data)
        assert resp.final_response == "Test response"

    def test_thought_object_validation(self):
        """ThoughtObject should validate required fields."""
        with pytest.raises(ValueError):
            ThoughtObject(primary_strategy="test")  # missing intent_summary

    def test_thought_object_confidence_bounds(self):
        """ThoughtObject confidence should be 0-1."""
        with pytest.raises(ValueError):
            ThoughtObject(intent_summary="test", primary_strategy="test", confidence=1.5)


class TestWorldState:
    """Test WorldState schema."""

    def test_default_values(self):
        """WorldState should have sensible defaults."""
        state = WorldState()
        assert state.current_phase == "IDLE"
        assert state.execution_started is False
        assert state.planning_depth == 0
        assert state.retry_count == 0
