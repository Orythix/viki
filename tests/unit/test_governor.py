"""Tests for the safety governor."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))  # noqa: E402

from viki.core.governor import EthicalGovernor  # noqa: E402


@pytest.fixture
def mock_model_router():
    """Create a mock model router that returns a model with chat."""
    router = MagicMock()
    mock_model = AsyncMock()
    # Return approved by default
    mock_model.chat.return_value = "APPROVED"
    mock_model.record_performance = MagicMock()
    router.get_model.return_value = mock_model
    return router


@pytest.fixture
def governor():
    """Create an EthicalGovernor."""
    return EthicalGovernor()


class TestEthicalGovernor:
    """Test cases for EthicalGovernor."""

    @pytest.mark.asyncio
    async def test_allows_identity_question(self, governor, mock_model_router):
        """Governor should allow 'who am I' questions (exempt under identity)."""
        result, reason = await governor.semantic_veto_check(
            "do you know who I am?", mock_model_router
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_allows_greeting(self, governor, mock_model_router):
        """Governor should allow simple greetings."""
        result, reason = await governor.semantic_veto_check("hello", mock_model_router)
        assert result is True

    @pytest.mark.asyncio
    async def test_allows_general_question(self, governor, mock_model_router):
        """Governor should allow general knowledge questions."""
        result, reason = await governor.semantic_veto_check(
            "what is the capital of France?", mock_model_router
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_uses_default_model_not_fast(self, governor, mock_model_router):
        """Governor should use default model (gemma4) not fast model (phi3)."""
        await governor.semantic_veto_check("test query", mock_model_router)
        # Verify get_model was called WITHOUT capabilities filter
        mock_model_router.get_model.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_fail_closed_on_model_error(self, governor, mock_model_router):
        """Governor should deny (fail closed) when model errors."""
        mock_model_router.get_model.return_value.chat.side_effect = Exception("Model failed")
        result, reason = await governor.semantic_veto_check("test query", mock_model_router)
        assert result is False

    @pytest.mark.asyncio
    async def test_vetoes_dangerous_intent(self, governor, mock_model_router):
        """Governor should veto dangerous intents."""
        mock_model_router.get_model.return_value.chat.return_value = (
            "VETOED: Attempt to delete system files"
        )
        result, reason = await governor.semantic_veto_check("delete all files", mock_model_router)
        assert result is False
        assert "VETOED" in reason or "delete" in reason.lower()
