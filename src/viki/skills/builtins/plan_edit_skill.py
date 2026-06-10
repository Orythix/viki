"""
Phase 3: `plan_edit` skill — exposes the Planner/Executor + patch-and-verify loop
as a single skill the cortex can call.

When invoked it:
1. Asks the Planner for a typed task graph for the given goal.
2. Wires task callbacks to: `code_search`, `dev_tools` (read), `dev_tools` (patch
   via PatchVerify), interpreter for `run_tests`, and a noop for `analyze`.
3. Runs the graph; rolls back any patch whose verify step fails.
4. Returns a short summary plus the full graph state.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from viki.skills.base import BaseSkill
from viki.core.task_planner import PlannerExecutor, TaskType
from viki.core.patch_verify import PatchVerify


class PlanEditSkill(BaseSkill):
    def __init__(self, controller):
        self._controller = controller

    @property
    def name(self) -> str:
        return "plan_edit"

    @property
    def description(self) -> str:
        return (
            "Plan and apply a multi-step code change with patch-and-verify rollback. "
            "Usage: plan_edit(goal='describe the change', verify_cmd='pytest -q')"
        )

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "Human goal for the edit."},
                "verify_cmd": {
                    "type": "string",
                    "description": "Shell command used to verify each patch (default: pytest -q).",
                },
            },
            "required": ["goal"],
        }

    @property
    def safety_tier(self) -> str:
        return "medium"

    async def execute(self, params: Dict[str, Any]) -> str:
        goal = (params.get("goal") or "").strip()
        if not goal:
            return "plan_edit: goal is required."

        controller = self._controller
        registry = controller.skill_registry
        workspace = controller.settings.get("system", {}).get("workspace_dir", "./workspace")
        verify_cmd_str = params.get("verify_cmd")
        verify_cmd = verify_cmd_str.split() if verify_cmd_str else None
        patch_verify = PatchVerify(workspace_dir=workspace, verify_cmd=verify_cmd)

        async def _do_search(task) -> str:
            skill = registry.get_skill("code_search")
            if not skill:
                return "code_search skill unavailable"
            return await skill.execute(
                {"action": "search", "query": task.parameters.get("query") or goal, "top_k": 5}
            )

        async def _do_read(task) -> str:
            dev = registry.get_skill("dev_tools")
            path = task.parameters.get("path")
            if not (dev and path):
                return "read_file requires dev_tools skill and 'path' param."
            return await dev.execute({"action": "read_file", "path": path})

        async def _do_patch(task) -> str:
            path = task.parameters.get("path")
            new_content = task.parameters.get("new_content")
            if not (path and new_content):
                return "patch task requires 'path' and 'new_content' parameters."
            target = os.path.join(workspace, path) if not os.path.isabs(path) else path
            result = patch_verify.apply_and_verify(target, new_content)
            return json.dumps(result.as_dict())

        async def _do_run_tests(task) -> str:
            verify = patch_verify._run_verify(verify_cmd or patch_verify.DEFAULT_VERIFY_CMD)
            return json.dumps(verify)

        async def _do_analyze(task) -> str:
            # Light-weight analysis: just record the goal/task so the planner trace is auditable.
            return f"analysis recorded: {task.description[:200]}"

        async def _do_reflect(task) -> str:
            return "reflection complete"

        async def _do_refactor(task) -> str:
            # Treat as a sequence of patches; the planner should already have decomposed it.
            return "refactor delegated to downstream patch tasks."

        callbacks = {
            TaskType.SEARCH_REPO.value: _do_search,
            TaskType.READ_FILE.value: _do_read,
            TaskType.PATCH.value: _do_patch,
            TaskType.RUN_TESTS.value: _do_run_tests,
            TaskType.ANALYZE.value: _do_analyze,
            TaskType.REFLECT.value: _do_reflect,
            TaskType.REFACTOR.value: _do_refactor,
        }

        planner = PlannerExecutor(model_router=controller.model_router, executor_callbacks=callbacks)
        repo_context = ""
        try:
            cs = registry.get_skill("code_search")
            if cs:
                repo_context = await cs.execute({"action": "search", "query": goal, "top_k": 5})
        except Exception:
            repo_context = ""

        graph = await planner.plan(goal, repo_context=repo_context)
        graph = await planner.execute(graph)
        summary = graph.summary()
        ok = summary["done"] - summary["failed"]
        return (
            f"plan_edit: {summary['done']} task(s) succeeded, "
            f"{summary['failed']} failed (graph={len(summary['tasks'])} nodes).\n\n"
            + json.dumps(summary, indent=2)
        )
