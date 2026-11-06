"""Leftover 2026 items: tokenizer asset, forge seed, coding BoN helper."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from viki.core.react_loop import _CODING_BON_SKILLS, run_coding_best_of_n
from viki.core.schema import ActionCall
from viki.core.utils.token_optimizer import (
    _package_tokenizer_path,
    count_tokens,
    reset_tokenizer_cache,
)


def test_shipped_cl100k_asset_exists():
    path = _package_tokenizer_path()
    assert path is not None
    assert os.path.isfile(path)
    assert os.path.getsize(path) > 100_000


def test_airgap_tokenizer_loads_from_package():
    reset_tokenizer_cache()
    # Force package path by clearing env overrides
    os.environ.pop("VIKI_TIKTOKEN_CACHE", None)
    os.environ.pop("VIKI_TOKENIZER_CACHE", None)
    n = count_tokens("def hello_world():\n    return 42\n")
    assert n >= 5


@pytest.mark.asyncio
async def test_seed_pinned_eval_writes_jsonl(tmp_path):
    from viki.core.forge_eval_seed import seed_pinned_eval_results

    controller = MagicMock()
    controller.settings = {"system": {"data_dir": str(tmp_path)}}
    controller.model_router = MagicMock()
    controller.model_router.models = {}
    ab = MagicMock()
    ab.test_prompts = [
        {"id": "t1", "prompt": "x", "category": "coding", "test_code": "assert False"},
    ]
    ab._test_model = AsyncMock(return_value=("nope", 0.01, True))
    ab._score_response = MagicMock(return_value=0.0)
    controller.model_ab_test = ab
    controller.ab_tester = ab

    summary = await seed_pinned_eval_results(controller, "cand", incumbent_model="inc")
    assert os.path.isfile(summary["path"])
    lines = open(summary["path"], encoding="utf-8").read().strip().splitlines()
    assert any(json.loads(l).get("__metadata__") for l in lines)
    assert "cand" in summary["scores"]


@pytest.mark.asyncio
async def test_coding_bon_skips_non_coding_skill():
    controller = MagicMock()
    action = ActionCall(skill_name="research", parameters={"query": "x"})
    assert action.skill_name not in _CODING_BON_SKILLS
    out = await run_coding_best_of_n(controller, action, {}, user_input="x")
    assert out is None
