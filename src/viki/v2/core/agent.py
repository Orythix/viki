"""Core agent — main LLM session + ReAct loop + multi-agent + task planning + critique."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from ..agents.manager import AgentManager
from ..config import V2Config, get_config
from ..llm import get_llm_client
from ..tools.registry import ToolRegistry
from ..workflow.definitions import BUILTIN_WORKFLOWS, list_workflows
from ..workflow.engine import WorkflowEngine
from .context_builder import ContextBuilder
from .context_manager import ContextManager
from .intent_analyzer import IntentAnalyzer
from .permission_manager import PermissionManager
from .repo_analyzer import RepoAnalyzer
from .response_generator import ResponseGenerator
from .self_critique import SelfCritique
from .session_manager import SessionManager
from .task_planner import TaskPlanner
from .tool_selector import ToolSelector

logger = logging.getLogger(__name__)

# Responses that skip self-critique (cheap heuristic to avoid an extra LLM call)
_TRIVIAL_PATTERNS = (
    "the time is",
    "the current time",
    "it is now",
    "the date is",
    "today is",
    "the weather",
    "temperature is",
    "sorry",
    "i don't know",
    "i cannot",
    "i'm not sure",
    "error:",
    "failed:",
)

_MULTI_AGENT_KEYWORDS = [
    "review",
    "audit",
    "analyze project",
    "inspect",
    "evaluate",
    "code review",
    "security review",
    "quality check",
]

_WORKFLOW_KEYWORDS: dict[str, str] = {
    "lint": "lint-and-fix",
    "fix lint": "lint-and-fix",
    "deploy": "deploy-preview",
    "audit dep": "audit-dependencies",
    "dependency": "audit-dependencies",
    "backup": "backup-project",
}


class CoreAgent:
    """Main agent orchestrator. Owns the LLM session and ReAct loop.

    Supports multi-agent dispatch for compound tasks, task planning for
    multi-step goals, self-critique for quality assurance, and named
    workflow execution.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        permission_manager: PermissionManager | None = None,
        session_manager: SessionManager | None = None,
        agent_manager: AgentManager | None = None,
        config: V2Config | None = None,
    ):
        self.config = config or get_config()
        self.tool_registry = tool_registry or ToolRegistry()
        self.permission_manager = permission_manager or PermissionManager(self.tool_registry)
        self.session_manager = session_manager or SessionManager()
        self.agent_manager = agent_manager or AgentManager(
            llm_client=get_llm_client(),
            tool_registry=self.tool_registry,
        )
        self.intent_analyzer = IntentAnalyzer(self.tool_registry)
        self.tool_selector = ToolSelector(self.tool_registry)
        self.context_builder = ContextBuilder(self.tool_registry)
        self.response_generator = ResponseGenerator()
        self.self_critique = SelfCritique()
        self.task_planner = TaskPlanner(
            self.tool_registry,
            permission_manager=self.permission_manager,
        )
        self.workflow_engine = WorkflowEngine(self.tool_registry)
        self.context_manager = ContextManager()
        self.repo_analyzer = RepoAnalyzer()
        self._llm = get_llm_client()

    async def process(
        self,
        user_input: str,
        session_id: str | None = None,
        on_token: Callable[[str], None] | None = None,
        on_workflow_step: Callable[[str, str, bool | None], None] | None = None,
        on_agent_status: Callable[[str, str], None] | None = None,
    ) -> str:
        """Process a single user request through the full pipeline.

        Parameters
        ----------
        on_token :
            Called with each token as it arrives from the LLM (streaming).
        on_workflow_step :
            Called with ``(workflow_name, step_name, success_or_None)``
            during named workflow execution. ``success=None`` means step
            is starting, ``True/False`` means completed.
        on_agent_status :
            Called with ``(agent_name, status)`` during multi-agent
            dispatch. Status is ``"start"`` or ``"complete"``.

        Routing:
          1. Named workflow (e.g., "run lint-and-fix")
          2. Multi-agent task (e.g., "review this repo")
          3. Standard ReAct loop with self-critique
        """
        workflow_name = self._match_workflow(user_input)
        if workflow_name:
            return await self._execute_named_workflow(
                workflow_name,
                user_input,
                on_step=lambda n, s=None: on_workflow_step(workflow_name, n, s)
                if on_workflow_step
                else None,  # noqa: E501
            )

        if self._is_multi_agent_task(user_input):
            return await self._dispatch_multi_agent(
                user_input,
                on_agent=on_agent_status,
            )

        session = self.session_manager.get_or_create(session_id)
        session.last_active = time.time()

        messages = self.context_builder.build_messages(user_input)

        max_steps = self.config.max_steps
        final_response = None
        using_stream = on_token is not None
        for _step in range(max_steps):
            if using_stream:
                collected = []
                async for token in self._llm.chat_stream(messages):
                    # Don't show tool_calls JSON in the live stream to the user
                    if not (token.startswith("{") and '"tool_calls"' in token):
                        on_token(token)
                    collected.append(token)
                response = "".join(collected)
            else:
                response = await self._llm.chat(messages)

            tool_call = self._parse_tool_call(response)
            if not tool_call:
                final_response = response
                break

            tool_name = tool_call["tool"]
            params = tool_call.get("parameters", {})

            check = await self.permission_manager.check(tool_name, params, session.id)
            if not check.allowed:
                denial = f"Permission denied: {check.reason}"
                messages = self.context_builder.add_observation(messages, tool_name, denial)
                continue

            result = await self.tool_registry.execute(tool_name, params)

            obs = (
                result.to_llm_observation()
                if hasattr(result, "to_llm_observation")
                else str(result)
            )
            # Truncate long tool results to prevent context overflow
            if len(obs) > 4000:
                obs = obs[:4000] + "\n... [truncated]"
            messages = self.context_builder.add_observation(messages, tool_name, obs)

        if final_response is None:
            final_response = "Max steps reached. Please try a more specific request."

        # Self-critique — skip for trivial / error responses to save an LLM call
        if not self._is_trivial(final_response):
            critique = await self.self_critique.critique(user_input, final_response)
            if not critique.passed:
                improved = await self.self_critique.improve(user_input, final_response, critique)
                session.history.append({"user": user_input, "assistant": improved})
                return improved

        session.history.append({"user": user_input, "assistant": final_response})
        return final_response

    @staticmethod
    def _is_trivial(response: str) -> bool:
        """Cheap heuristic: skip self-critique for obvious single-sentence answers."""
        lower = response.lower().strip()
        if len(lower) < 40:
            return True  # very short response
        if any(lower.startswith(p) for p in _TRIVIAL_PATTERNS):
            return True
        if lower.startswith("tool") and "returned" in lower:
            return True
        return False

    # ------------------------------------------------------------------
    # Workflow execution
    # ------------------------------------------------------------------

    def _match_workflow(self, user_input: str) -> str | None:
        """Check if user input matches a named workflow."""
        lower = user_input.lower()
        for keyword, wf_name in _WORKFLOW_KEYWORDS.items():
            if keyword in lower:
                return wf_name
        return None

    async def _execute_named_workflow(
        self,
        workflow_name: str,
        user_input: str,
        on_step: Callable[[str, bool | None], None] | None = None,
    ) -> str:
        """Execute a named workflow and return a formatted report."""
        wf = BUILTIN_WORKFLOWS.get(workflow_name)
        if not wf:
            available = ", ".join(list_workflows())
            return f"Unknown workflow '{workflow_name}'. Available: {available}"

        result = await self.workflow_engine.execute(wf, on_step=on_step)

        parts = [f"# Workflow: {wf.name}\n"]
        for step_name, step_result in result.step_results.items():
            status = "OK" if self.workflow_engine._is_success(step_result) else "FAIL"
            parts.append(f"- **{step_name}**: {status}")

        if not result.success:
            parts.append(f"\n**Failed at:** {result.failed_at}")
            parts.append(f"**Error:** {result.error}")
            if result.rolled_back:
                parts.append("**Rollback executed**")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Multi-agent dispatch
    # ------------------------------------------------------------------

    def _is_multi_agent_task(self, user_input: str) -> bool:
        lower = user_input.lower()
        return any(kw in lower for kw in _MULTI_AGENT_KEYWORDS)

    async def _dispatch_multi_agent(
        self,
        user_input: str,
        on_agent: Callable[[str, str], None] | None = None,
    ) -> str:
        context = await self._build_repo_context()
        report = await self.agent_manager.dispatch_all(user_input, context, on_agent=on_agent)

        parts = [f"# Multi-Agent Report\n\n**Goal:** {user_input}\n"]
        for agent_name, findings in report.results.items():
            parts.append(f"## {agent_name.title()}")
            parts.append(f"**Summary:** {findings.summary}")
            parts.append(f"**Confidence:** {findings.confidence:.0%}")
            if findings.risks:
                parts.append("**Risks:**")
                for r in findings.risks:
                    parts.append(f"  - {r}")
            if findings.recommendations:
                parts.append("**Recommendations:**")
                for rec in findings.recommendations:
                    parts.append(f"  - {rec}")
            parts.append("")

        if report.errors:
            parts.append("## Errors")
            for name, err in report.errors.items():
                parts.append(f"  - **{name}:** {err}")

        return "\n".join(parts)

    async def _build_repo_context(self) -> dict:
        ctx = {}
        try:
            result = await self.tool_registry.execute("dev", {"action": "analyze", "path": "."})
            if result and result.success:
                ctx["repo_info"] = str(result.data)
        except Exception:
            ctx["repo_info"] = ""
        return ctx

    # ------------------------------------------------------------------
    # Tool call parsing
    # ------------------------------------------------------------------

    def _parse_tool_call(self, response: str) -> dict | None:
        try:
            import re

            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                if "tool" in data:
                    return data
        except Exception:
            pass
        return None


class AgentResponse:
    def __init__(self, content: str, requires_confirmation: bool = False):
        self.content = content
        self.requires_confirmation = requires_confirmation
