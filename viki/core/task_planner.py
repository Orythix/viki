"""
Phase 3: Planner / Executor split for the coding agent.

The planner converts a high-level user goal into a typed task graph, the
executor consumes one node at a time with a bounded scratchpad. Each node has
explicit dependencies and a success/failure observation so we can self-heal.

Task types (extensible):
- SearchRepoTask  : query the repo via `code_search` skill
- ReadFileTask    : read a specific file region
- PatchTask       : apply a targeted edit (patch + verify)
- RunTestsTask    : run project tests in interpreter sandbox
- RefactorTask    : multi-file structural change
- AnalyzeTask     : LLM analysis with no side effects
- ReflectTask     : evaluate prior outcomes and choose the next step

The planner uses the model router's "planning" capability slot.
The executor maps each task type to a registered VIKI skill and the patch-and-
verify loop in `viki.core.patch_verify`.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from viki.config.logger import viki_logger


class TaskType(str, Enum):
    SEARCH_REPO = "search_repo"
    READ_FILE = "read_file"
    WRITE = "write"
    PATCH = "patch"
    RUN_TESTS = "run_tests"
    REFACTOR = "refactor"
    ANALYZE = "analyze"
    REFLECT = "reflect"
    SHELL = "shell"
    CREATE = "create"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class PlanTask:
    id: str
    type: TaskType
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    observation: str = ""
    started_ts: float = 0.0
    finished_ts: float = 0.0
    attempts: int = 0
    max_attempts: int = 2

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "description": self.description,
            "parameters": self.parameters,
            "depends_on": list(self.depends_on),
            "status": self.status.value,
            "observation": (self.observation or "")[:500],
            "attempts": self.attempts,
            "started_ts": self.started_ts,
            "finished_ts": self.finished_ts,
        }


@dataclass
class TaskGraph:
    goal: str
    tasks: List[PlanTask] = field(default_factory=list)
    created_ts: float = field(default_factory=time.time)

    def by_id(self, tid: str) -> Optional[PlanTask]:
        for t in self.tasks:
            if t.id == tid:
                return t
        return None

    def ready_tasks(self) -> List[PlanTask]:
        out: List[PlanTask] = []
        for t in self.tasks:
            if t.status != TaskStatus.PENDING:
                continue
            if all(self.by_id(d) and self.by_id(d).status == TaskStatus.DONE for d in t.depends_on):
                out.append(t)
        return out

    def is_done(self) -> bool:
        return all(t.status in (TaskStatus.DONE, TaskStatus.FAILED) for t in self.tasks)

    def summary(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "task_count": len(self.tasks),
            "tasks": [t.as_dict() for t in self.tasks],
            "done": sum(1 for t in self.tasks if t.status == TaskStatus.DONE),
            "failed": sum(1 for t in self.tasks if t.status == TaskStatus.FAILED),
        }


class PlannerExecutor:
    """
    Thin orchestrator: produce a TaskGraph from user goal, run nodes by deps,
    and report back. Designed for embedding inside the existing Cortex ReAct
    loop on the DEEP path when the request looks code-modifying.
    """

    PLAN_SYSTEM_PROMPT = (
        "You are VIKI's planner. Decompose the user's coding goal into a typed task graph.\n"
        "Output ONLY a JSON array of tasks with fields {id, type, description, parameters, depends_on}.\n"
        "Allowed task types: search_repo, read_file, write, patch, run_tests, refactor, analyze, reflect, shell, create.\n"
        "CRITICAL: 'shell' and 'create' tasks MUST have a 'command' parameter.\n"
        "CRITICAL: 'write' and 'read_file' tasks MUST have a 'path' parameter.\n"
        "CRITICAL: ALL shell commands MUST be NON-INTERACTIVE. Use --yes, --force, or -y flags.\n"
        "Example: For npx, use 'npx -y create-vite@latest ...'. For npm, use 'npm init -y'.\n"
        "Keep the plan minimal (<=12 tasks). Each task should be small and verifiable.\n"
        "Tasks must reference other task ids in depends_on for ordering.\n"
        "Example: [{\"id\":\"t1\",\"type\":\"shell\",\"description\":\"init project\",\"parameters\":{\"command\":\"npx -y create-vite@latest . --template react\"},\"depends_on\":[]}]"
    )

    def __init__(self, model_router, executor_callbacks: Optional[Dict[str, Any]] = None):
        self.model_router = model_router
        self.callbacks = executor_callbacks or {}

    async def plan(self, goal: str, repo_context: str = "", skill_context: str = "") -> TaskGraph:
        """Ask the planning model for a task graph; fall back to a heuristic if parsing fails."""
        try:
            model = self.model_router.get_model(["planning", "reasoning"])
        except Exception:
            model = None

        graph = TaskGraph(goal=goal)
        if model is None:
            graph.tasks = self._fallback_plan(goal)
            return graph

        try:
            messages = [
                {"role": "system", "content": self.PLAN_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"GOAL:\n{goal}\n\n"
                        f"AVAILABLE SKILLS (SCHEMAS):\n{skill_context}\n\n"
                        f"REPO CONTEXT (snippets):\n{(repo_context or '')[:4000]}\n\n"
                        f"Produce the task graph as JSON only."
                    ),
                },
            ]
            raw = await model.chat(messages, temperature=0.2)
            graph.tasks = self._parse_plan(raw)
        except Exception as e:
            viki_logger.warning("Planner failed, using fallback plan: %s", e)
            graph.tasks = self._fallback_plan(goal)

        if not graph.tasks:
            graph.tasks = self._fallback_plan(goal)
        return graph

    @staticmethod
    def _parse_plan(raw: Any) -> List[PlanTask]:
        text = raw if isinstance(raw, str) else str(raw or "")
        text = text.strip()
        # Find first JSON array.
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        tasks: List[PlanTask] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                t_type = TaskType(str(entry.get("type", "analyze")).lower())
            except ValueError:
                t_type = TaskType.ANALYZE
            tasks.append(
                PlanTask(
                    id=str(entry.get("id") or f"t{len(tasks)+1}"),
                    type=t_type,
                    description=str(entry.get("description", "")),
                    parameters=dict(entry.get("parameters") or {}),
                    depends_on=list(entry.get("depends_on") or []),
                )
            )
        return tasks

    @staticmethod
    def _fallback_plan(goal: str) -> List[PlanTask]:
        """Conservative plan when the planner model is unavailable."""
        lower_goal = goal.lower()
        if any(w in lower_goal for w in ["create", "build", "make", "generate", "scaffold"]):
             return [
                 PlanTask(
                     id="t1",
                     type=TaskType.ANALYZE,
                     description=f"Plan the project structure for: {goal[:100]}",
                     parameters={"goal": goal},
                     depends_on=[]
                 ),
                 PlanTask(
                     id="t2",
                     type=TaskType.SHELL,
                     description="Initialize project directory",
                     parameters={"command": "powershell -NoProfile -Command \"New-Item -ItemType Directory -Path project -Force\""},
                     depends_on=["t1"]
                 ),
                 PlanTask(
                     id="t3",
                     type=TaskType.WRITE,
                     description="Create initial entry point",
                     parameters={"path": "project/README.md", "content": f"# Project\nGenerated for: {goal}"},
                     depends_on=["t2"]
                 )
             ]
             
        return [
            PlanTask(
                id="t1",
                type=TaskType.SEARCH_REPO,
                description=f"Locate code related to: {goal[:200]}",
                parameters={"query": goal[:200]},
                depends_on=[],
            ),
            PlanTask(
                id="t2",
                type=TaskType.ANALYZE,
                description="Analyze candidates and propose minimal change.",
                parameters={"goal": goal[:200]},
                depends_on=["t1"],
            ),
            PlanTask(
                id="t3",
                type=TaskType.RUN_TESTS,
                description="Run project tests to confirm no regression.",
                parameters={},
                depends_on=["t2"],
            ),
        ]

    async def execute(self, graph: TaskGraph) -> TaskGraph:
        """Run a graph until all nodes terminate. Caller-supplied callbacks dispatch each task type."""
        max_iterations = max(3 * len(graph.tasks), 10)
        for _ in range(max_iterations):
            ready = graph.ready_tasks()
            if not ready and graph.is_done():
                break
            if not ready:
                # No ready tasks but not done -> dependency cycle or all blocked.
                for t in graph.tasks:
                    if t.status == TaskStatus.PENDING:
                        t.status = TaskStatus.BLOCKED
                break
            for task in ready:
                viki_logger.info(f"PlannerExecutor: Running task {task.id} ({task.type.value}): {task.description}")
                await self._run_task(task)
                viki_logger.info(f"PlannerExecutor: Task {task.id} finished with status {task.status.value}")
        return graph

    async def _run_task(self, task: PlanTask) -> None:
        task.status = TaskStatus.RUNNING
        task.started_ts = time.time()
        task.attempts += 1
        callback = self.callbacks.get(task.type.value)
        if callback is None:
            task.status = TaskStatus.FAILED
            task.observation = f"No executor registered for task type {task.type.value}"
            task.finished_ts = time.time()
            return
        try:
            result = await callback(task)
            task.observation = str(result)[:1000]
            task.status = TaskStatus.DONE
        except Exception as e:
            task.observation = f"Error: {e}"
            if task.attempts < task.max_attempts:
                task.status = TaskStatus.PENDING
            else:
                task.status = TaskStatus.FAILED
        finally:
            task.finished_ts = time.time()
