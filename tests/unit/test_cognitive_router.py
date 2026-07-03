"""Tests for cognitive router."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))  # noqa: E402

from viki.core.cognitive_loop import CognitiveRouter  # noqa: E402
from viki.core.output_verifier import JudgmentEngine, JudgmentOutcome, JudgmentResult  # noqa: E402


@pytest.fixture
def mock_judgment_engine():
    """Create a mock judgment engine."""
    engine = MagicMock(spec=JudgmentEngine)
    engine.evaluate = AsyncMock(
        return_value=JudgmentResult(
            outcome=JudgmentOutcome.SHALLOW,
            recommendation="proceed",
            reason="Simple query",
            risk=0.1,
            clarity=0.9,
            novelty=0.1,
            complexity_score=0.2,
        )
    )
    return engine


@pytest.fixture
def mock_reflex_brain():
    """Create a mock reflex brain."""
    reflex = MagicMock()
    reflex.think = MagicMock(return_value=(None, None))
    return reflex


@pytest.fixture
def cognitive_router(mock_reflex_brain, mock_judgment_engine):
    """Create a CognitiveRouter with mocked dependencies."""
    return CognitiveRouter(mock_reflex_brain, mock_judgment_engine)


class TestCognitiveRouter:
    """Test cases for CognitiveRouter."""

    @pytest.mark.asyncio
    async def test_simple_query_routes_shallow(self, cognitive_router):
        """Simple queries should route to SHALLOW with lite schema."""
        route = await cognitive_router.classify("hello")
        assert route.outcome == JudgmentOutcome.SHALLOW
        assert route.use_lite_schema is True
        assert route.model_tier == "fast"

    @pytest.mark.asyncio
    async def test_complex_query_routes_deep(self, cognitive_router, mock_judgment_engine):
        """Complex queries should route to DEEP with full schema."""
        mock_judgment_engine.evaluate.return_value = JudgmentResult(
            outcome=JudgmentOutcome.DEEP,
            recommendation="proceed",
            reason="Complex analysis needed",
            risk=0.3,
            clarity=0.6,
            novelty=0.8,
            complexity_score=0.9,
        )
        route = await cognitive_router.classify(
            "analyze the entire codebase architecture and propose improvements"
        )
        assert route.outcome == JudgmentOutcome.DEEP
        assert route.use_lite_schema is False
        assert route.model_tier == "heavy"
