"""
Thin compatibility shim.

Live deliberation lives in ``viki.core.layers.deliberation_layer.DeliberationLayer``.
Verifier-backed branch selection for deep coding/planning/complex routes uses
``viki.core.react_loop.run_mcts_tree_search``.

``DeliberationEngine`` remains only so ``VIKIController`` / tests that still
construct it do not break; callers should not rely on ``deliberate()``.
"""

from __future__ import annotations

from typing import Any

from viki.config.logger import viki_logger
from viki.core.model import LLMProvider


class DeliberationEngine:
    """
    Deprecated stub. Prefer DeliberationLayer + MCTS on the live request path.
    """

    def __init__(self, llm: LLMProvider | Any, self_model: Any = None):
        self.llm = llm
        self.self_model = self_model

    def deliberate(self, user_input: str, context: list[dict]) -> tuple[dict, float]:
        """
        Compatibility no-op: returns a single pass-through plan so legacy callers
        defer to the cortex / MCTS path instead of hardcoded 0.8 scores.
        """
        viki_logger.debug(
            "DeliberationEngine.deliberate is a shim; use DeliberationLayer / MCTS."
        )
        plan = {
            "id": "cortex",
            "action": "defer_to_cortex",
            "reasoning": "Delegated to DeliberationLayer + optional MCTS",
            "steps": ["cortex", "optional_mcts", "execute"],
            "input": user_input,
            "context_len": len(context or []),
        }
        return plan, 0.0
