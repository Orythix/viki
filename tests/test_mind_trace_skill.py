import pytest
from viki.skills.builtins.mind_trace_skill import MindTraceSkill


class MockController:
    def __init__(self):
        self.meta = {
            "model_tier": "standard",
            "source": "judgment",
            "elapsed_ms": 1500.0,
            "use_ensemble": False,
            "judgment": {
                "complexity_score": 0.45,
                "clarity": 0.9,
                "risk": 0.1,
                "novelty": 0.3,
                "reason": "Test judgment",
            },
            "usage": {"input_tokens": 100, "output_tokens": 50, "total_cost_usd": 0.0001},
        }

    def get_last_response_meta(self, session_id=None):
        return self.meta


@pytest.mark.asyncio
async def test_mind_trace_last():
    ctrl = MockController()
    skill = MindTraceSkill(ctrl)

    result = await skill.execute({"action": "last"})
    assert "STANDARD" in result
    assert "0.450" in result
    assert "Test judgment" in result
    assert "Input:  100 tokens" in result


@pytest.mark.asyncio
async def test_mind_trace_no_meta():
    ctrl = MockController()
    ctrl.meta = {}  # Empty
    skill = MindTraceSkill(ctrl)

    result = await skill.execute({"action": "last"})
    assert "No recent cognitive trace" in result
