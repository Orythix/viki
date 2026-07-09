import asyncio
import os
import re
from typing import Any, cast

from viki.config.logger import viki_logger
from viki.core import command_handlers
from viki.core.cognitive_loop import CognitiveRoute, JudgmentOutcome, JudgmentResult
from viki.core.git_context import get_git_workspace_snapshot
from viki.core.request_pipeline import RequestContext
from viki.core.schema import VIKIResponse
from viki.ops.tenant_ops import ControllerTenantConnector, OpsPlan


class PipelineMixin:
    async def process_request(
        self,
        user_input: str,
        on_event=None,
        on_think=None,
        attachment_paths: list[str] | None = None,
        session_id: str | None = None,
    ) -> str:
        norm_session = self._normalize_session_id(session_id)
        baseline = self._router_usage_snapshot()
        try:
            result = await self._process_request_impl(
                user_input,
                on_event=on_event,
                on_think=on_think,
                attachment_paths=attachment_paths,
                session_id=norm_session,
            )
        finally:
            self._accumulate_session_usage_from_delta(norm_session, baseline)

        if result:
            from viki.core.security_guard import redact_secrets

            return redact_secrets(result)
        return result or ""

    async def _process_request_impl(
        self,
        user_input: str,
        on_event=None,
        on_think=None,
        attachment_paths: list[str] | None = None,
        session_id: str | None = None,
    ) -> str:
        session_id = self._normalize_session_id(session_id)
        self._last_response_meta_by_session[session_id] = {}

        if user_input is None:
            user_input = ""
        if not isinstance(user_input, str):
            user_input = str(user_input).strip() or ""

        try:
            from viki.core.input_validator import validate_user_input

            validated = validate_user_input(user_input)
            if validated is not None:
                user_input = validated
        except ImportError:
            pass

        pre_ctx = RequestContext(
            user_input=user_input,
            session_id=session_id,
            on_event=on_event,
            attachment_paths=attachment_paths,
        )
        preflight_response = await self._preflight_pipeline.run_preflight(self, pre_ctx)
        if preflight_response is not None:
            return preflight_response

        user_input = pre_ctx.user_input
        safe_input = pre_ctx.safe_input
        narrative_wisdom = pre_ctx.narrative_wisdom

        file_matches = re.findall(r"[\w\-\.\/]+\.(?:py|js|ts|css|html|yaml|md)", user_input)
        for match in file_matches:
            if os.path.sep in match or "." in match:
                self.world.set_active_file(match)

        reflex_resp, reflex_action = self.reflex.think(user_input)
        if reflex_resp is not None:
            viki_logger.info("Reflex hit (conversational). Returning immediately.")
            if "singularity" in reflex_resp.lower() and "activated" in reflex_resp.lower():
                self.is_singularity_mode = True
                viki_logger.info("SINGULARITY ACTIVATED via Reflex.")
            return reflex_resp

        if reflex_action is not None:
            viki_logger.info(
                f"Reflex hit (action: {reflex_action.skill_name}). Bypassing deliberation."
            )
            reflex_route = CognitiveRoute(
                outcome=JudgmentOutcome.REFLEX,
                judgment=JudgmentResult(
                    outcome=JudgmentOutcome.REFLEX,
                    recommendation="proceed",
                    reason="Reflex hit (bypass deliberation)",
                    risk=0.0,
                    clarity=1.0,
                    novelty=0.0,
                    complexity_score=0.1,
                ),
                model_tier="fast",
                action_override=reflex_action,
                use_lite_schema=True,
                source="reflex",
            )
            return await self._process_reflex_outcome(reflex_route, safe_input, session_id)

        if self._should_plan_ops(safe_input):
            tenant_id = self.settings.get("system", {}).get("tenant_id", "default")
            ops_plan = await self.ops_planner.plan(tenant_id, safe_input)

            if ops_plan.approval and ops_plan.approval.required:
                self.pending_ops_plans[session_id] = ops_plan
                what = ", ".join(ops_plan.approval.what_to_approve or [])
                return (
                    "OpsPlan created (approval gate active).\n"
                    f"Update type: {ops_plan.update_type}\n"
                    f"Proposed changes: {ops_plan.proposed_changes}\n"
                    f"ApprovalRequirement: require approval for {what or 'side effects'}.\n"
                    "Confirm with yes/confirm or cancel with no/reject."
                )

            return await self._apply_ops_plan(ops_plan, session_id=session_id)

        task_type = self._classify_task(safe_input)
        budget = self.budgets.get(task_type, self.budgets["general"])

        self.memory.working.add_message("user", safe_input, session_id=session_id)

        url_context = await self._fetch_url_content(safe_input)

        cmd_result = await self._detect_and_handle_modes(
            user_input, safe_input, task_type, budget, session_id, on_event
        )
        if isinstance(cmd_result, str):
            return cmd_result
        user_input, safe_input, task_type, budget = cmd_result
        url_context = await self._fetch_url_content(safe_input)

        cmd_result = await self._detect_and_handle_modes(
            user_input, safe_input, task_type, budget, session_id, on_event
        )
        if isinstance(cmd_result, str):
            return cmd_result
        user_input, safe_input, task_type, budget = cmd_result

        workspace_dir = self.settings.get("system", {}).get(
            "workspace_dir", self.DEFAULT_WORKSPACE_DIR
        )

        (
            memory_context,
            project_instructions,
            git_snapshot,
            relevant_failures,
        ) = await self._fetch_pipeline_context(
            safe_input, narrative_wisdom, task_type, session_id, workspace_dir
        )

        memory_context["project_instructions"] = project_instructions
        if git_snapshot:
            base = memory_context.get("project_instructions") or ""
            memory_context["project_instructions"] = (
                (base + "\n\n" + git_snapshot).strip() if base else git_snapshot
            )
        memory_context["relevant_failures"] = relevant_failures

        if task_type == "coding" and not self.is_plan_mode:
            memory_context["skip_escalation"] = True

        world_understanding = self.world.get_understanding()

        result = await self._route_cognitively(
            safe_input,
            task_type,
            url_context,
            session_id,
        )
        if isinstance(result, str):
            return result
        cognitive_route, outcome, use_lite = result

        return await self._dispatch_to_react_loop(
            user_input,
            safe_input,
            session_id,
            on_event,
            on_think,
            memory_context,
            url_context,
            world_understanding,
            cognitive_route,
            use_lite,
            task_type,
            budget,
            outcome,
        )

    async def _fetch_url_content(self, safe_input: str) -> str:
        urls = re.findall(r'https?://[^\s<>"]+', safe_input)
        if not urls:
            return ""
        url_context = ""
        try:
            research_skill = self.skill_registry.get_skill("research")
            if research_skill:
                url_content = await asyncio.wait_for(
                    asyncio.gather(
                        *[research_skill.execute({"url": u}) for u in urls[:2]],
                        return_exceptions=True,
                    ),
                    timeout=35.0,
                )
                for i, res in enumerate(url_content):
                    if isinstance(res, str) and res:
                        url_context += f"\n{res}\n"
                    elif isinstance(res, Exception):
                        viki_logger.debug(
                            "URL fetch failed for %s: %s",
                            urls[i] if i < len(urls) else "?",
                            res,
                        )
        except TimeoutError:
            viki_logger.warning("URL fetch timed out (35s); continuing without page content.")
        except Exception as e:
            viki_logger.warning("URL fetch failed: %s", e)
        return url_context

    async def _route_cognitively(
        self,
        safe_input: str,
        task_type: str,
        url_context: str,
        session_id: str,
    ) -> str | tuple:
        task_type = self._classify_task(safe_input)
        try:
            cognitive_route: CognitiveRoute | None = await self.cognitive_router.classify(
                safe_input,
                context={
                    "task_type": "question"
                    if task_type == "reasoning" and safe_input.strip().endswith("?")
                    else task_type,
                    "is_protected_zone": False,
                    "url_context_present": bool(url_context),
                },
                skill_registry=self.skill_registry,
                history=self.memory.working.get_trace(session_id=session_id),
            )
        except Exception as e:
            viki_logger.warning("Cognitive routing failed (%s); defaulting to DEEP.", e)
            cognitive_route = None

        if cognitive_route is not None:
            outcome = cognitive_route.outcome
            use_lite = cognitive_route.use_lite_schema or task_type in ("general", "reasoning")
        else:
            outcome = JudgmentOutcome.DEEP
            use_lite = task_type in ("general", "reasoning")

        if cognitive_route is not None and cognitive_route.refusal_reason:
            self._last_response_meta_by_session[session_id] = {
                "cognitive_route": cognitive_route.as_dict(),
            }
            self.memory.working.add_message(
                "assistant",
                f"I cannot proceed with this request. {cognitive_route.refusal_reason}",
                session_id=session_id,
            )
            return f"I cannot proceed with this request. {cognitive_route.refusal_reason}"

        if cognitive_route is not None and cognitive_route.cached_response:
            self._last_response_meta_by_session[session_id] = {
                "cognitive_route": cognitive_route.as_dict(),
            }
            self.memory.working.add_message(
                "assistant", cognitive_route.cached_response, session_id=session_id
            )
            return cognitive_route.cached_response

        return cognitive_route, outcome, use_lite

    async def _dispatch_to_react_loop(
        self,
        user_input: str,
        safe_input: str,
        session_id: str,
        on_event,
        on_think,
        memory_context: dict,
        url_context: str,
        world_understanding: str,
        cognitive_route,
        use_lite: bool,
        task_type: str,
        budget: dict[str, Any],
        outcome,
    ) -> str:
        from viki.core.agent_constants import SAFE_FOLLOWUP_MESSAGES

        lower_input = safe_input.lower().strip()
        is_continuation = lower_input in SAFE_FOLLOWUP_MESSAGES or (
            len(lower_input.split()) <= 4 and any(k in lower_input for k in SAFE_FOLLOWUP_MESSAGES)
        )
        task_type = self._classify_task(safe_input)

        mods = self.signals.get_modulation()
        signals_state = (
            f"Verbosity: {mods.get('verbosity', 'standard')}, "
            f"Planning: {mods.get('planning_depth', 'adaptive')}, "
            f"Safety: {mods.get('safety_bias', 'standard')}"
        )
        agency_weights = self.evolution.get_agent_weightings()

        if is_continuation and self.world.state.active_goal:
            self._resume_execution(cognitive_route)
        elif task_type == "coding":
            self._handle_coding_fsm(safe_input)

        if not self.world.state.current_phase:
            self.world.state.current_phase = "IDLE"
        viki_logger.info(
            "FSM State: %s | Goal: %s...",
            self.world.state.current_phase,
            self.world.state.active_goal[:30] if self.world.state.active_goal else "None",
        )
        self.world.save()

        from viki.core.react_loop import run_react_loop

        return await run_react_loop(
            self,
            user_input=user_input,
            safe_input=safe_input,
            session_id=session_id,
            on_event=on_event,
            on_think=on_think,
            memory_context=memory_context,
            url_context=url_context,
            world_understanding=world_understanding,
            cognitive_route=cognitive_route,
            use_lite=use_lite,
            signals_state=signals_state,
            agency_weights=agency_weights,
            project_instructions=memory_context.get("project_instructions", ""),
            is_continuation=is_continuation,
            task_type=task_type,
            budget=budget,
            outcome=outcome,
        )

    def _resume_execution(self, cognitive_route) -> None:
        viki_logger.info(
            "FSM: Continuation Intent Detected. Resuming goal: %s...",
            self.world.state.active_goal[:50] if self.world.state.active_goal else "None",
        )
        if self.world.state.current_phase in ("EXECUTING", "TESTING", "DEBUGGING"):
            viki_logger.debug(
                "FSM: Maintaining execution state: %s", self.world.state.current_phase
            )
        else:
            self.world.state.current_phase = "EXECUTING"
            self.world.state.execution_started = True
        if cognitive_route:
            cognitive_route.outcome = JudgmentOutcome.SHALLOW
            cognitive_route.use_lite_schema = True

    def _handle_coding_fsm(self, safe_input: str) -> None:
        from viki.core.agent_constants import MAX_PLANNING_CYCLES

        if self.world.state.active_goal != safe_input and len(safe_input) > 10:
            viki_logger.info("FSM: New Coding Goal: %s...", safe_input[:50])
            self.world.state.active_goal = safe_input
            self.world.state.planning_depth = 0
            self.world.state.retry_count = 0
            self.world.state.execution_started = False
            if self.should_execute_directly(safe_input):
                viki_logger.info(
                    "FSM: SUFFICIENT REQUIREMENTS. Bypassing planning; Locking EXECUTING state."
                )
                self.world.state.current_phase = "EXECUTING"
                self.world.state.execution_started = True
            else:
                self.world.state.current_phase = "PLANNING"
        if self.world.state.current_phase == "PLANNING":
            self.world.state.planning_depth += 1
            if self.world.state.planning_depth > MAX_PLANNING_CYCLES:
                viki_logger.warning("FSM: MAX_PLANNING_CYCLES exceeded. Forcing EXECUTING state.")
                self.world.state.current_phase = "EXECUTING"
                self.world.state.execution_started = True

    async def _detect_and_handle_modes(
        self,
        user_input: str,
        safe_input: str,
        task_type: str,
        budget: dict[str, Any],
        session_id: str,
        on_event,
    ) -> str | tuple[str, str, str, dict]:
        self.is_agent_mode = user_input.strip().lower().startswith("/agent")
        if self.is_agent_mode:
            viki_logger.info("AGENT MODE ACTIVATED: Engaging autonomous engineering loop.")
            user_input = re.sub(r"^/agent\s*", "", user_input, flags=re.IGNORECASE).strip()
            if not user_input:
                return "Agent Mode activated. Please provide a task (e.g., /agent implement feature X)."
            safe_input = self.safety.validate_request(user_input)

        self.is_plan_mode = user_input.strip().lower().startswith("/plan")
        if self.is_plan_mode:
            viki_logger.info("PLAN MODE ACTIVATED: Engaging senior architect loop.")
            user_input = re.sub(r"^/plan\s*", "", user_input, flags=re.IGNORECASE).strip()
            if not user_input:
                return "Plan Mode activated. Please provide a request for architectural analysis or implementation strategy."
            safe_input = self.safety.validate_request(user_input)

        self.is_debug_mode = user_input.strip().lower().startswith("/debug")
        if self.is_debug_mode:
            viki_logger.info("DEBUG MODE ACTIVATED: Engaging diagnostic loop.")
            user_input = re.sub(r"^/debug\s*", "", user_input, flags=re.IGNORECASE).strip()
            if not user_input:
                return "Debug Mode activated. Please provide an error message, log, or issue description to diagnose."
            safe_input = self.safety.validate_request(user_input)

        is_research = "/research" in user_input
        if is_research:
            viki_logger.info("Entering Research Mode: Exploratory & Verbose.")
            budget["time"] = cast(float, budget["time"]) * 2

        cmd_check = user_input.strip().lower()
        if cmd_check.startswith("/benchmark"):
            return await command_handlers.handle_benchmark_command(self, user_input)
        if "/scorecard" in user_input:
            return await command_handlers.handle_scorecard_command(self)
        if "/model" in user_input:
            return await command_handlers.handle_model_command(self)
        if "/evolve" in user_input:
            return await command_handlers.handle_evolve_command(self)
        if user_input.startswith("/approve"):
            return await command_handlers.handle_approve_command(self, user_input)
        if user_input.startswith(self.REJECT_TOKEN):
            return await command_handlers.handle_reject_command(self, user_input)
        if "/crystallize" in user_input:
            return await command_handlers.handle_crystallize_command(self)
        if user_input.startswith("/forge"):
            return await command_handlers.handle_forge_command(self, user_input, session_id)
        if "/dream" in user_input:
            return await command_handlers.handle_dream_command(self)
        if "/scan" in user_input:
            return await command_handlers.handle_scan_command(self)
        if cmd_check.startswith("/restore"):
            return await command_handlers.handle_restore_command(self, user_input)
        if cmd_check in ("/undo", "/undo last"):
            return await command_handlers.handle_undo_command(self)
        if cmd_check.startswith("/save"):
            return await command_handlers.handle_save_command(self, user_input, session_id)
        if cmd_check.startswith("/load"):
            return await command_handlers.handle_load_command(self, user_input, session_id)
        if cmd_check.startswith("/fork"):
            return await command_handlers.handle_fork_command(self, user_input, session_id)
        if cmd_check.startswith("/switch"):
            return await command_handlers.handle_switch_command(self, user_input)
        if cmd_check in ("/branches", "/branch"):
            return await command_handlers.handle_branches_command(self)
        if cmd_check.startswith("/diff"):
            return await command_handlers.handle_diff_command(self, user_input)
        if cmd_check.startswith("/test-gen"):
            return await command_handlers.handle_test_gen_command(self, user_input)
        if cmd_check.startswith("/skills"):
            return await command_handlers.handle_skills_command(self, user_input)

        if on_event:
            on_event("status", "DELIBERATING")
        return user_input, safe_input, task_type, budget

    async def _fetch_pipeline_context(
        self,
        safe_input: str,
        narrative_wisdom: str | None,
        task_type: str,
        session_id: str,
        workspace_dir: str,
    ) -> tuple[dict, str, str, list]:
        async def _fetch_memory_context() -> dict:
            return await asyncio.to_thread(
                self.memory.get_full_context,
                safe_input,
                narrative_wisdom=narrative_wisdom,
                session_id=session_id,
            )

        async def _fetch_project_instructions() -> str:
            result = ""
            for name in ("VIKI.md", "VIKI_CONTEXT.md"):
                p = os.path.join(workspace_dir, name)
                if not os.path.isfile(p):
                    continue
                try:
                    trunc_limit = 32768
                    if task_type == "general" and not (
                        self.is_agent_mode or self.is_plan_mode or self.is_debug_mode
                    ):
                        trunc_limit = 4096
                        rag_context = await self.context_retriever.get_relevant_context(safe_input)
                        if rag_context:
                            result = (result or "") + rag_context
                    raw = await asyncio.to_thread(self._read_text_truncated, p, trunc_limit)
                    result = (result or "") + raw
                    break
                except Exception as e:
                    viki_logger.debug("Could not read %s: %s", p, e)
            return result

        async def _fetch_git_snapshot() -> str:
            if not self.settings.get("system", {}).get("git_workspace_context"):
                return ""
            try:
                snap = await asyncio.to_thread(get_git_workspace_snapshot, workspace_dir)
                return snap or ""
            except Exception as e:
                viki_logger.debug("git_workspace_context: %s", e)
                return ""

        async def _fetch_relevant_failures() -> list:
            return await asyncio.to_thread(self.learning.get_relevant_failures, safe_input, limit=3)

        return await asyncio.gather(
            _fetch_memory_context(),
            _fetch_project_instructions(),
            _fetch_git_snapshot(),
            _fetch_relevant_failures(),
        )

    async def _process_reflex_outcome(
        self, cognitive_route, safe_input, session_id, on_event=None
    ) -> str:
        reflex_action_override = cognitive_route.action_override
        if reflex_action_override is None:
            return "Reflex logic error: no action provided."

        skill_name = reflex_action_override.skill_name
        params = (reflex_action_override.parameters or {}).copy()
        budget = self.budgets.get("general", self.budgets["general"])

        check_res = self.capabilities.check_permission(skill_name, params=params)
        if not check_res.allowed:
            viki_logger.warning(f"Reflex blocked: {check_res.reason}")
            return f"Reflex blocked: {check_res.reason}"

        if not self.safety.validate_action(skill_name, params):
            viki_logger.warning("Reflex blocked: safety policy.")
            return "Reflex blocked: safety policy."

        severity = self._skill_action_severity(skill_name, params)
        if severity in ("medium", "destructive"):
            self.pending_actions[session_id] = reflex_action_override
            return (
                f"Reflex matched '{skill_name}'. Safety Check: this is a {severity} action. "
                "Confirm to proceed, or say no to cancel."
            )

        if on_event:
            on_event("status", f"REFLEX EXECUTING {skill_name}")

        result, err, latency = await self._execute_skill(skill_name, params, budget)
        if err:
            try:
                self.reflex.report_failure(safe_input)
            except Exception as e:
                viki_logger.debug(f"Reflex failure reporting failed: {e}")
            return f"Reflex execution failed: {err}"

        self.skill_registry.record_execution(skill_name, True, latency)
        msg = self._compress_output(f"Done. {result}")
        self.memory.working.add_message("assistant", msg, session_id=session_id)

        self._last_response_meta_by_session[session_id] = {
            "cognitive_route": cognitive_route.as_dict(),
            "reflex_executed": True,
            "latency": latency,
        }

        return msg

    def _get_planner_callbacks(
        self, session_id: str, budget: dict[str, Any], on_event: Any | None
    ) -> dict[str, Any]:
        async def _generic_exec(task: Any, skill: str, forced_params: dict[str, Any] | None = None):
            if on_event:
                on_event("status", f"PLANNER: {task.description}")
            params = (task.parameters if isinstance(task.parameters, dict) else {}).copy()
            if forced_params:
                params.update(forced_params)

            res, err, lat = await self._execute_skill(skill, params, budget)
            if err:
                raise RuntimeError(err)
            return res

        async def _analyze(task: Any):
            if on_event:
                on_event("status", f"PLANNER ANALYZING: {task.description}")
            model = self.model_router.get_model(["reasoning", "fast_response"])
            prompt = (
                f"You are the VIKI Execution Agent.\n"
                f"Goal: {self.world.state.active_goal}\n"
                f"Current Task: {task.description}\n"
                f"Context: {task.parameters}\n\n"
                f"Provide a technical analysis or plan for this specific step."
            )
            return await model.chat([{"role": "user", "content": prompt}])

        return {
            "search_repo": lambda t: _generic_exec(t, "code_search"),
            "read_file": lambda t: _generic_exec(t, "dev_tools", {"action": "read_file"}),
            "write": lambda t: _generic_exec(t, "dev_tools", {"action": "write_file"}),
            "patch": lambda t: _generic_exec(t, "dev_tools", {"action": "patch_file"}),
            "run_tests": lambda t: _generic_exec(t, "shell"),
            "refactor": lambda t: _generic_exec(t, "dev_tools", {"action": "patch_file"}),
            "analyze": _analyze,
            "reflect": _analyze,
            "shell": lambda t: _generic_exec(t, "shell"),
            "create": lambda t: _generic_exec(t, "shell"),
        }

    def should_execute_directly(self, text: str) -> bool:
        s = text.lower()
        from viki.core.agent_constants import CODING_KEYWORDS

        intents = ["create", "build", "make", "generate", "develop", "scaffold", "implement"]
        tech = CODING_KEYWORDS
        products = ["app", "website", "dashboard", "frontend", "backend", "api", "ui", "script"]

        has_intent = any(i in s for i in intents)
        has_tech = any(t in s for t in tech)
        has_product = any(p in s for p in products)

        signals = sum([has_intent, has_tech, has_product])
        return signals >= 2

    def _classify_task(self, input_text: str) -> str:
        s = input_text.strip().lower()
        if any(k in s for k in ["see", "look", "screen", "vision", "screenshot"]):
            return "vision"
        question_words = [
            "what",
            "who",
            "where",
            "when",
            "why",
            "how",
            "is",
            "are",
            "can",
            "do",
            "does",
        ]
        if s.endswith("?"):
            return "reasoning"
        if any(s == w or s.startswith(w + " ") for w in question_words):
            return "reasoning"
        from viki.core.agent_constants import CODING_KEYWORDS

        if any(k in s for k in CODING_KEYWORDS):
            return "coding"
        if any(k in s for k in ["plan", "think", "analyze", "sequence"]):
            return "reasoning"
        return "general"

    def _is_explanation_requested(self, input_text: str) -> bool:
        explanation_keywords = [
            "why",
            "explain",
            "details",
            "elaborate",
            "how",
            "what happened",
            "reason",
        ]
        return any(k in input_text.lower() for k in explanation_keywords)

    _KNOWLEDGE_GAP_MARKERS = (
        "i don't know",
        "i do not know",
        "not sure",
        "i'm not sure",
        "i am not sure",
        "cannot say",
        "can't say",
        "no information",
        "beyond my knowledge",
        "outside my knowledge",
        "not in my training",
        "i wasn't trained",
        "i was not trained",
        "unable to verify",
        "i cannot verify",
        "can't verify",
        "would need to search",
        "i don't have access to",
        "i have no access to",
        "not certain",
        "unclear to me",
        "i lack",
        "don't have current",
        "do not have current",
        "cannot find any",
        "can't find any",
    )

    def _auto_web_research_setting_enabled(self) -> bool:
        if getattr(self, "air_gap", False) or getattr(self, "shadow_mode", False):
            return False
        sys = self.settings.get("system") or {}
        return bool(sys.get("auto_web_research_when_uncertain", True))

    def _response_indicates_knowledge_gap(self, text: str) -> bool:
        if not text or len(text.strip()) < 8:
            return False
        low = text.lower()
        if "--- search results" in low or "web lookup (automatic)" in low:
            return False
        return any(m in low for m in self._KNOWLEDGE_GAP_MARKERS)

    async def _synthesize_answer_with_web_snippets(
        self, question: str, draft: str, web: str
    ) -> str | None:
        if not self.model_router or not web.strip():
            return None
        web_trunc = web[:7000] if len(web) > 7000 else web
        try:
            model = self.model_router.get_model(["reasoning"])
        except Exception:
            try:
                model = self.model_router.get_model(["general"])
            except Exception:
                return None
        messages = [
            {
                "role": "system",
                "content": (
                    "You are VIKI. The user asked a question. A draft answer may lack current facts. "
                    "Web search results follow. Write ONE updated answer: use snippets for facts, "
                    "cite source domains or URLs briefly, and do not invent details not in the snippets. "
                    "If snippets are irrelevant, say so in one sentence and keep the draft answer."
                ),
            },
            {
                "role": "user",
                "content": f"Question:\n{question}\n\nDraft answer:\n{draft}\n\nWeb results:\n{web_trunc}",
            },
        ]
        try:
            text = await asyncio.wait_for(model.chat(messages, temperature=0.25), timeout=120.0)
        except Exception as e:
            viki_logger.debug("Auto web synthesis LLM failed: %s", e)
            return None
        text = (text or "").strip()
        if len(text) < 20:
            return None
        return text

    async def _maybe_auto_web_research(
        self,
        safe_input: str,
        final_output: str,
        viki_resp: VIKIResponse | None,
        action_results: list[dict[str, Any]],
        session_id: str,
        on_event=None,
    ) -> str:
        if not self._auto_web_research_setting_enabled():
            return final_output
        if not safe_input or len(safe_input.strip()) < 8:
            return final_output

        _self_ref = re.search(
            r"(who\s+are\s+you|what\s+are\s+you|tell\s+me\s+about\s+(yourself|you(\s+viki)?)|"
            r"about\s+yourself|introduce\s+yourself|describe\s+yourself)",
            safe_input.lower().strip(),
        )
        if _self_ref:
            return final_output

        rs = self.skill_registry.get_skill("research")
        if not rs:
            return final_output

        for r in action_results:
            act = (r.get("action") or "").lower()
            if act.startswith("research("):
                return final_output

        conf = 1.0
        if viki_resp and viki_resp.final_thought:
            try:
                conf = float(getattr(viki_resp.final_thought, "confidence", 1.0) or 1.0)
            except (TypeError, ValueError):
                conf = 1.0

        uncertain_phrase = self._response_indicates_knowledge_gap(final_output)
        if conf >= 0.5 and not uncertain_phrase:
            return final_output

        query = safe_input.strip()[:500]
        viki_logger.info(
            "Auto web research: triggered (confidence=%.2f, uncertain_phrase=%s).",
            conf,
            uncertain_phrase,
        )
        if on_event:
            on_event("status", "AUTO WEB RESEARCH (uncertain answer)")

        try:
            web = await asyncio.wait_for(rs.execute({"query": query}), timeout=28.0)
        except TimeoutError:
            viki_logger.warning("Auto web research timed out.")
            return final_output
        except Exception as e:
            viki_logger.warning("Auto web research failed: %s", e)
            return final_output

        if not web or "No results found" in web or web.startswith(("Search error", "Error:")):
            return final_output

        synthesized = await self._synthesize_answer_with_web_snippets(safe_input, final_output, web)
        if synthesized:
            meta = self._last_response_meta_by_session.get(session_id) or {}
            meta["auto_web_research"] = True
            self._last_response_meta_by_session[session_id] = meta
            return synthesized

        meta = self._last_response_meta_by_session.get(session_id) or {}
        meta["auto_web_research"] = True
        self._last_response_meta_by_session[session_id] = meta
        appendix = web[:8000] if len(web) > 8000 else web
        return f"{final_output}\n\n---\n**Web lookup (automatic)**\n{appendix}"

    async def _trigger_evolution_if_needed(self, force: bool = False):
        if self._should_skip_evolution(force):
            self._handle_plateau_redirect()
            return

        stable_lessons = self.learning.get_stable_lesson_count()
        current_total = self.learning.get_total_lesson_count()

        state_path = self._get_evolution_state_path()

        last_total = 0
        if os.path.exists(state_path):
            try:
                state = await asyncio.to_thread(self._read_json, state_path)
                last_total = state.get("last_forge_lesson_count", 0)
            except Exception as e:
                viki_logger.debug(f"Could not load evolution state: {e}")

        if force or (stable_lessons >= 10 and current_total - last_total >= 5):
            viki_logger.info(
                f"Initiating Neural Forge Evolution (Stable Lessons: {stable_lessons})..."
            )

            forge_skill = self.skill_registry.get_skill("internal_forge")
            if forge_skill:
                result = await forge_skill.execute({"strategy": "auto", "steps": 60})
                viki_logger.info(f"Forge Result: {result}")

                if "SUCCESS" in result:
                    await asyncio.to_thread(
                        self._write_json,
                        state_path,
                        {"last_forge_lesson_count": current_total},
                        indent=None,
                    )
            else:
                viki_logger.warning("Forge skill not found.")

        recs = self.skill_registry.get_refactor_recommendations()
        for rec in recs:
            viki_logger.warning(f"Self-Awareness Alert: {rec}")
            self.learning.save_lesson(f"INTERNAL_SYSTEM_ADVISORY: {rec}")

    def _should_plan_ops(self, text: str) -> bool:
        t = (text or "").lower()
        has_schedule_intent = any(k in t for k in ("schedule", "appointment", "meeting", "event"))
        has_time_hint = any(k in t for k in ("tomorrow", "today", "at ")) or bool(
            re.search(r"\d{1,2}(:\d{2})?\s*(am|pm)", t)
        )
        has_cancel_intent = any(
            k in t for k in ("cancel", "cancellation", "remove", "delete")
        ) and any(k in t for k in ("meeting", "appointment", "event"))
        return (has_schedule_intent and has_time_hint) or has_cancel_intent

    async def _apply_ops_plan(self, plan: OpsPlan, session_id: str) -> str:
        if self.shadow_mode:
            return (
                f"[Shadow Mode] Would apply OpsPlan: {plan.update_type} ({plan.proposed_changes})."
            )

        connector = ControllerTenantConnector(self, tenant_id=plan.tenant_id)

        changes = dict(plan.proposed_changes or {})
        changes["update_type"] = plan.update_type
        apply_res = await connector.apply_changes(changes)
        if not apply_res.get("ok", False):
            return f"Ops execution failed: {apply_res.get('error', 'unknown error')}"

        send_res = await connector.send_messages(plan.message_drafts or [])

        cal_res = (
            (apply_res.get("calendar") or {}).get("result")
            if isinstance(apply_res.get("calendar"), dict)
            else None
        )
        msg_results = send_res.get("results", []) if isinstance(send_res, dict) else []
        msg_summary = "; ".join(
            f"{r.get('channel')}={r.get('result') or r.get('error')}"
            for r in msg_results
            if isinstance(r, dict)
        )

        self.pending_ops_plans.pop(session_id, None)

        return (
            f"OpsPlan applied: {plan.update_type}.\n"
            f"Calendar: {cal_res or 'n/a'}\n"
            f"Messages: {msg_summary or 'n/a'}"
        )
