"""Tests for skill registry."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))  # noqa: E402

from viki.skills.base import BaseSkill  # noqa: E402
from viki.skills.registry import SkillRegistry  # noqa: E402


class MockSkill(BaseSkill):
    """Mock skill for testing."""

    name = "mock_skill"
    description = "A mock skill for testing"

    async def execute(self, **kwargs):
        return {"result": "mock executed"}

    def get_tool_definition(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}},
            },
        }


class TestSkillRegistry:
    """Test SkillRegistry."""

    def setup_method(self):
        """Create fresh registry for each test."""
        self.registry = SkillRegistry()
        # Clear any pre-discovered dynamic skills for test isolation
        self.registry.skills.clear()
        self.registry.metrics.clear()

    def test_register_and_get_skill(self):
        skill = MockSkill()
        self.registry.register_skill(skill)

        retrieved = self.registry.get_skill("mock_skill")
        assert retrieved is skill
        assert retrieved.name == "mock_skill"

    def test_get_nonexistent_skill_returns_none(self):
        result = self.registry.get_skill("nonexistent")
        assert result is None

    def test_list_skills(self):
        skill1 = MockSkill()
        skill1.name = "skill_a"
        skill2 = MockSkill()
        skill2.name = "skill_b"
        self.registry.register_skill(skill1)
        self.registry.register_skill(skill2)

        skills = self.registry.list_skills()
        assert len(skills) == 2
        assert "skill_a" in skills
        assert "skill_b" in skills

    def test_reliability_score_tracking(self):
        skill = MockSkill()
        self.registry.register_skill(skill)

        # Initially no metrics
        metrics = self.registry.get_reliability_score("mock_skill")
        assert metrics == "(Untested)"

        # Record success
        self.registry.record_execution("mock_skill", success=True, latency=0.1)
        metrics = self.registry.get_reliability_score("mock_skill")
        assert "100%" in metrics
        assert "RELIABLE" in metrics

        # Record failure
        self.registry.record_execution("mock_skill", success=False, latency=0.2)
        metrics = self.registry.get_reliability_score("mock_skill")
        assert "50%" in metrics
