"""
Self-healing recovery (Phase 4).

Watches MissionGraph nodes that fail and uses Failure Memory + a recovery
planner LLM to generate a remediation. Three remediation attempts max, then
escalate via the controller's Nexus / signals so the user is asked.

This module is purposely independent of MissionGraphRunner so it can be wired
in either before / after a run, or invoked manually.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from viki.config.logger import viki_logger
from viki.core.mission_graph import MissionGraph, MissionNode, NodeStatus

RECOVERY_SYSTEM_PROMPT = (
    "You are VIKI's self-healing planner. A mission node failed. "
    "Given the original goal, the failed node, the captured error, and any "
    "similar historical failures, propose a JSON object describing how to "
    "recover. The schema is:\n"
    '{"strategy": "retry"|"rewrite"|"split"|"escalate",\n'
    ' "rationale": str,\n'
    ' "new_title": str|null,\n'
    ' "new_description": str|null,\n'
    ' "new_parameters": dict|null,\n'
    ' "subtasks": [ {"title": str, "description": str} ]|null }\n'
    "Reply with JSON only."
)


class SelfHealer:
    """
    Bridges failed mission nodes to the planner so a recovery patch can be
    generated automatically.
    """

    def __init__(
        self,
        model_router: Any,
        learning_module: Optional[Any] = None,
        max_recoveries_per_node: int = 3,
    ):
        self.router = model_router
        self.learning = learning_module
        self.max_recoveries = max(1, int(max_recoveries_per_node))

    async def heal(self, graph: MissionGraph, node: MissionNode) -> Dict[str, Any]:
        """
        Attempt to heal a failed node. Mutates the graph in-place when a
        retry / rewrite / split is chosen. Returns the recovery decision dict.
        """
        if node.status != NodeStatus.FAILED:
            return {"strategy": "noop", "rationale": "node not failed"}

        prior = node.metadata.get("recoveries", 0)
        if prior >= self.max_recoveries:
            viki_logger.warning(
                "SelfHealer: node %s exceeded recovery cap (%d); escalating.",
                node.id,
                self.max_recoveries,
            )
            return {"strategy": "escalate", "rationale": "max recoveries exceeded"}

        similar = self._fetch_similar_failures(node)
        proposal = await self._propose_recovery(graph, node, similar)
        node.metadata["recoveries"] = prior + 1
        node.metadata.setdefault("recovery_log", []).append(proposal)
        self._apply_recovery(graph, node, proposal)
        return proposal

    def _fetch_similar_failures(self, node: MissionNode) -> List[str]:
        if self.learning is None or not hasattr(self.learning, "get_relevant_failures"):
            return []
        try:
            ctx = f"{node.title}\n{node.description}\n{node.error or ''}"
            return self.learning.get_relevant_failures(ctx, limit=3) or []
        except Exception as e:
            viki_logger.debug("SelfHealer: failure-memory lookup failed: %s", e)
            return []

    async def _propose_recovery(
        self, graph: MissionGraph, node: MissionNode, similar: List[str]
    ) -> Dict[str, Any]:
        if self.router is None or not hasattr(self.router, "get_model"):
            return self._fallback_recovery(node)

        try:
            model = self.router.get_model(capabilities=["reasoning", "planning"])
        except Exception:
            try:
                model = self.router.get_model()
            except Exception:
                return self._fallback_recovery(node)
        if model is None:
            return self._fallback_recovery(node)

        prompt = (
            f"Goal: {graph.goal}\n"
            f"Failed node: {node.title}\n"
            f"Description: {node.description}\n"
            f"Skill: {node.skill}\n"
            f"Parameters: {json.dumps(node.parameters or {})[:800]}\n"
            f"Error: {node.error}\n"
            f"Similar prior failures:\n- "
            + ("\n- ".join(similar) if similar else "(none)")
        )

        try:
            raw = await model.chat(
                [
                    {"role": "system", "content": RECOVERY_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
        except Exception as e:
            viki_logger.debug("SelfHealer: recovery LLM call failed: %s", e)
            return self._fallback_recovery(node)

        return self._parse_recovery(raw, node)

    @staticmethod
    def _parse_recovery(raw: str, node: MissionNode) -> Dict[str, Any]:
        try:
            text = raw.strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].lstrip()
            decision = json.loads(text)
            if not isinstance(decision, dict):
                raise ValueError("response is not a JSON object")
            strategy = decision.get("strategy", "retry")
            if strategy not in ("retry", "rewrite", "split", "escalate"):
                raise ValueError(f"invalid strategy: {strategy}")
            decision["strategy"] = strategy
            for key in ("new_title", "new_description"):
                val = decision.get(key)
                if val is not None and not isinstance(val, str):
                    decision[key] = str(val)
            params = decision.get("new_parameters")
            if params is not None and not isinstance(params, dict):
                decision["new_parameters"] = None
            subtasks = decision.get("subtasks")
            if subtasks is not None:
                if not isinstance(subtasks, list):
                    subtasks = []
                validated = []
                for s in subtasks:
                    if isinstance(s, dict) and "title" in s:
                        validated.append({
                            "title": str(s.get("title", "")),
                            "description": str(s.get("description", "")),
                        })
                decision["subtasks"] = validated or None
            return decision
        except Exception:
            return SelfHealer._fallback_recovery(node)

    @staticmethod
    def _fallback_recovery(node: MissionNode) -> Dict[str, Any]:
        if node.attempts >= node.max_attempts:
            return {"strategy": "escalate", "rationale": "no remaining attempts"}
        return {
            "strategy": "retry",
            "rationale": "deterministic retry fallback",
            "new_title": None,
            "new_description": None,
            "new_parameters": None,
            "subtasks": None,
        }

    @staticmethod
    def _apply_recovery(
        graph: MissionGraph, node: MissionNode, decision: Dict[str, Any]
    ) -> None:
        strategy = decision.get("strategy", "retry")
        if strategy == "retry":
            node.status = NodeStatus.PENDING
            node.error = None
            node.attempts = max(0, node.max_attempts - 1)
            return
        if strategy == "rewrite":
            node.status = NodeStatus.PENDING
            node.error = None
            node.attempts = 0
            if decision.get("new_title"):
                node.title = decision["new_title"]
            if decision.get("new_description"):
                node.description = decision["new_description"]
            if decision.get("new_parameters") is not None:
                node.parameters = dict(decision["new_parameters"])
            return
        if strategy == "split":
            subtasks = decision.get("subtasks") or []
            node.status = NodeStatus.DONE
            node.result = "split into subtasks"
            for st in subtasks:
                graph.add(
                    title=st.get("title", "subtask"),
                    description=st.get("description", ""),
                    parent_id=node.id,
                    skill=node.skill,
                    parameters=node.parameters,
                )
            return
        # escalate / unknown -> leave failed; runner will treat it as terminal.
        node.metadata["escalated"] = True
        node.error = f"escalated: {decision.get('rationale', node.error or 'failed')}"
