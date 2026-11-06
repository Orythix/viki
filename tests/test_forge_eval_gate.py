"""Forge eval gate: CapabilityIndex promotion rules."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from viki.core.forge_eval_gate import ForgeEvalGate


@pytest.mark.asyncio
async def test_refuse_promotion_on_non_positive_delta(tmp_path):
    controller = MagicMock()
    controller.settings = {"system": {"data_dir": str(tmp_path)}}
    controller.system_settings = {"data_dir": str(tmp_path)}
    controller.model_router = MagicMock()
    controller.model_router.primary_model = "incumbent"
    controller.scorecard = None

    ab = MagicMock()
    ab.compare = AsyncMock(
        return_value={
            "model_a_score": 0.8,
            "model_b_score": 0.7,
            "significant": True,
            "source": "pinned_eval",
        }
    )
    controller.model_ab_test = ab

    gate = ForgeEvalGate(controller)
    result = await gate.evaluate_candidate("candidate", "incumbent", min_improvement_pct=1.0)
    assert result.promoted is False
    assert result.metrics.get("refuse_reason") == "non_positive_capability_delta"


@pytest.mark.asyncio
async def test_promote_on_positive_significant_win(tmp_path):
    controller = MagicMock()
    controller.settings = {"system": {"data_dir": str(tmp_path)}}
    controller.system_settings = {"data_dir": str(tmp_path)}
    controller.model_router = MagicMock()
    controller.model_router.primary_model = "incumbent"
    controller.model_router.set_primary_model = AsyncMock()
    controller.scorecard = MagicMock()

    ab = MagicMock()
    ab.compare = AsyncMock(
        return_value={
            "model_a_score": 0.5,
            "model_b_score": 0.8,
            "significant": True,
            "source": "pinned_eval",
        }
    )
    controller.model_ab_test = ab

    gate = ForgeEvalGate(controller)
    result = await gate.evaluate_candidate("candidate", "incumbent", min_improvement_pct=5.0)
    assert result.promoted is True
    controller.model_router.set_primary_model.assert_awaited()
