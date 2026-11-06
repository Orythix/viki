from __future__ import annotations

import time
from typing import Any, cast

from viki.config.logger import viki_logger
from viki.core.agent_constants import DEFAULT_AGENT_MAX_STEPS, MAX_CLARIFICATION_REQUESTS
from viki.core.schema import ActionCall, ThoughtObject, VIKIResponse
from viki.core.security_guard import safe_for_log

PLACEHOLDERS = ["processing...", "executing", "thinking", "one moment", "working on it"]


async def run_react_loop(
    controller: Any,
    *,
    user_input: str,
    safe_input: str,
    session_id: str,
    on_event,
    on_think,
    memory_context: dict[str, Any],
    url_context: str,
    world_understanding: str,
    cognitive_route,
    use_lite: bool,
    signals_state: str,
    agency_weights: dict[str, float],
    project_instructions: str,
    is_continuation: bool,
    task_type: str,
    budget: dict[str, Any],
    outcome,
) -> str:
    # --- ReAct LOOP: Reason → Act → Observe → Reason → ... ---
    if controller.is_agent_mode:
        max_react_steps = DEFAULT_AGENT_MAX_STEPS
    elif controller.is_plan_mode:
        max_react_steps = 10
    elif controller.is_debug_mode:
        max_react_steps = 20
    else:
        max_react_steps = 5

    action_results: list[dict[str, Any]] = []
    final_output: str | None = None

    reflex_action_override: ActionCall | None = (
        cognitive_route.action_override if cognitive_route is not None else None
    )
    if reflex_action_override is not None and controller.skill_registry.get_skill(
        reflex_action_override.skill_name
    ):
        skill_name = reflex_action_override.skill_name
        params = (reflex_action_override.parameters or {}).copy()
        check_res = controller.capabilities.check_permission(skill_name, params=params)
        if check_res.allowed and controller.safety.validate_action(skill_name, params):
            severity = controller._skill_action_severity(skill_name, params)
            if severity in ("medium", "destructive"):
                controller.pending_actions[session_id] = reflex_action_override
                diff_preview = controller._diff_preview(skill_name, params)
                msg = (
                    f"Reflex matched '{skill_name}'. Safety Check: this is a {severity} action. "
                    f"Confirm to proceed."
                )
                if diff_preview:
                    msg += f"\n\n{diff_preview}"
                controller._last_response_meta_by_session[session_id] = {
                    "cognitive_route": cognitive_route.as_dict(),
                }
                return msg
            if not controller.shadow_mode:
                if on_event:
                    on_event("status", f"REFLEX EXECUTING {skill_name}")
                    on_event("tool_call", {"name": skill_name, "params": params})
                result, err, latency = await controller._execute_skill(skill_name, params, budget)
                if on_event:
                    on_event("tool_result", result if result and not err else err or "no result")
                if not err and result is not None:
                    try:
                        controller.skill_registry.record_execution(skill_name, True, latency)
                        controller.signals.update_signal("confidence", 0.05)
                        controller.world.track_app_usage(skill_name)
                    except Exception:
                        viki_logger.warning("failed to record reflex skill execution")
                    controller._last_response_meta_by_session[session_id] = {
                        "cognitive_route": cognitive_route.as_dict(),
                        "subtasks": [
                            {
                                "action": f"{skill_name}({params})",
                                "result": str(result)[:1000],
                                "step": 1,
                            }
                        ],
                        "total_steps": 1,
                        "reflex_executed": True,
                    }
                    reflex_msg = controller._compress_output(f"Done. {result[:1000]}")
                    controller.memory.working.add_message(
                        "assistant", reflex_msg, session_id=session_id
                    )
                    return cast("str", reflex_msg)
                if err:
                    try:
                        controller.reflex.report_failure(safe_input)
                    except Exception:
                        viki_logger.warning("failed to report reflex failure")
                    controller.skill_registry.record_execution(skill_name, False, 0.0)
                    viki_logger.info(
                        "Reflex action %s failed (%s); falling through to cortex.", skill_name, err
                    )

    for react_step in range(max_react_steps):
        if on_event:
            on_event("progress", {"step": react_step + 1, "total_steps": max_react_steps})
        step_label = f"[ReAct Step {react_step + 1}/{max_react_steps}]" if react_step > 0 else ""
        if step_label:
            viki_logger.info(f"{step_label} Continuing multi-step reasoning...")
            if on_event:
                on_event("status", f"THINKING {step_label}")

        try:
            controller._reflex_recursion_depth += 1
            if controller._reflex_recursion_depth > controller._max_reflex_recursion:
                viki_logger.error(
                    f"Reflex recursion depth exceeded ({controller._max_reflex_recursion})"
                )
                return "Safety: Maximum reflex retry depth exceeded. Please rephrase your request."
            use_ensemble_setting = controller.settings.get("system", {}).get("use_ensemble", True)
            if cognitive_route is not None:
                use_ensemble_setting = use_ensemble_setting and cognitive_route.use_ensemble

            if task_type == "coding" and controller.world.state.execution_started:
                use_lite = True
                use_ensemble_setting = False
                if controller.world.state.current_phase == "PLANNING":
                    viki_logger.warning(
                        "FSM Lock: Execution in progress. Forcing return to EXECUTING phase."
                    )
                    controller.world.state.current_phase = "EXECUTING"

            if task_type == "coding" and controller.world.state.current_phase == "UNDERSTANDING":
                controller.world.state.current_phase = "EXECUTING"
                controller.world.state.execution_started = True

            viki_resp = None
            if (
                task_type == "coding"
                and controller.world.state.current_phase == "EXECUTING"
                and not action_results
                and not is_continuation
            ):
                skill_context = controller.skill_registry.get_context_description(
                    mode="full",
                    names=["shell", "dev_skill", "filesystem_skill", "research", "lsp_tools"],
                )
                graph = await controller.planner.plan(
                    controller.world.state.active_goal,
                    repo_context=project_instructions,
                    skill_context=skill_context,
                )
                controller.planner.callbacks = controller._get_planner_callbacks(
                    session_id, budget, on_event
                )
                executed_graph = await controller.planner.execute(graph)

                controller.world.state.current_phase = "TESTING"
                controller.world.save()

                summary = executed_graph.summary()
                action_results.append(
                    {
                        "action": "task_graph_execution",
                        "result": f"Executed {summary['done']} tasks. Status: {'Success' if summary['failed'] == 0 else 'Partial Failure'}",
                        "step": react_step + 1,
                    }
                )

                if summary["failed"] == 0 and summary["done"] > 0:
                    status_msg = f"I've successfully completed the implementation for '{controller.world.state.active_goal}'."
                elif summary["done"] > 0:
                    status_msg = f"I've partially completed the implementation for '{controller.world.state.active_goal}', but {summary['failed']} tasks failed. Please review the logs."
                else:
                    status_msg = f"I attempted to execute the task graph for '{controller.world.state.active_goal}', but no tasks were completed successfully."

                viki_resp = VIKIResponse(
                    final_thought=ThoughtObject(
                        intent_summary="Task Graph Execution",
                        primary_strategy="Direct implementation via sovereign task planner",
                        confidence=1.0,
                    ),
                    final_response=status_msg + " Moving to verification.",
                    action=None,
                )

            if viki_resp is None:
                cached_resp = None
                if (
                    react_step == 0
                    and not action_results
                    and hasattr(controller, "cognitive_router")
                ):
                    try:
                        cached = controller.cognitive_router.semantic_cache.lookup(safe_input)
                        if cached is not None:
                            viki_logger.info("Semantic cache HIT for input (latency saved)")
                            cached_resp = cached
                            if isinstance(cached, dict):
                                viki_resp = VIKIResponse.model_validate(cached)
                    except Exception as e:
                        viki_logger.debug("Semantic cache lookup failed: %s", e)

                if cached_resp is None:
                    viki_resp = await controller.cortex.process(
                        safe_input,
                        memory_context=memory_context,
                        url_context=url_context,
                        use_lite_schema=use_lite,
                        world_context=world_understanding,
                        signals_context=signals_state + f", AgencyWeights: {agency_weights}",
                        evolution_log=controller.evolution.get_evolution_summary(),
                        action_results=action_results,
                        use_ensemble=use_ensemble_setting,
                        on_event=on_event,
                        on_think=on_think,
                        model_tier=cognitive_route.model_tier if cognitive_route else "standard",
                        is_agent_mode=controller.is_agent_mode,
                        is_plan_mode=controller.is_plan_mode,
                        is_debug_mode=controller.is_debug_mode,
                        is_singularity_mode=controller.is_singularity_mode,
                        execution_started=controller.world.state.execution_started,
                    )

            assert viki_resp is not None

            if task_type == "coding" and viki_resp:
                if viki_resp.intent_type == "clarification":
                    controller.world.state.retry_count += 1
                    if controller.world.state.retry_count > MAX_CLARIFICATION_REQUESTS:
                        viki_logger.warning(
                            "FSM: MAX_CLARIFICATION_REQUESTS exceeded. Forcing autonomous assumptions."
                        )
                        viki_resp.intent_type = "execution"
                        if viki_resp.final_thought:
                            viki_resp.final_thought.primary_strategy = "Proceeding with best-guess technical assumptions to maintain execution momentum."

                if controller.world.state.execution_started and viki_resp.intent_type in (
                    "planning",
                    "discovery",
                ):
                    viki_logger.warning(
                        f"FSM: FORBIDDEN TRANSITION ({viki_resp.intent_type}) detected during EXECUTION. Forcing bypass."
                    )
                    viki_resp.intent_type = "execution"
                    if viki_resp.final_thought:
                        viki_resp.final_thought.primary_strategy = "Forced execution path: bypass planning recursion and proceed with implementation."

                if controller.world.state.execution_started and react_step == 0:
                    viki_logger.info(
                        "FSM: Enforcing Style Mimicry policy. Nudging for contextual inspection."
                    )

            if len(controller.internal_trace) > 10:
                controller.internal_trace.pop(0)

            if viki_resp.intent_type == "correction" or viki_resp.sentiment == "frustrated":
                trace = controller.memory.working.get_trace(session_id=session_id)
                if len(trace) >= 2:
                    prev_messages = trace[-3:] if len(trace) >= 3 else trace
                    prev_response = next(
                        (m["content"] for m in reversed(prev_messages) if m["role"] == "assistant"),
                        None,
                    )

                    if prev_response:
                        controller.learning.save_lesson(
                            trigger=f"CORRECTION: {user_input[:100]}",
                            fact=f"When I said '{prev_response[:200]}', user corrected/expressed frustration: {user_input}",
                            source_task="user_correction",
                        )
                        viki_logger.info("Learning: Captured user correction as lesson")

            if hasattr(viki_resp, "final_thought") and viki_resp.final_thought:
                confidence = viki_resp.final_thought.confidence
                if confidence < 0.4:
                    controller.knowledge_gaps.record_low_confidence(user_input, confidence)

            if on_event and hasattr(viki_resp, "final_thought") and viki_resp.final_thought:
                on_event("thought", viki_resp.final_thought.intent_summary)
            if on_event:
                on_event("model", f"{task_type.capitalize()} Core")
                on_event("budget", budget.get("time", 0))

            if viki_resp.needs_escalation and use_lite:
                viki_logger.info(
                    "Escalation Triggered: Retrying current step with DEEP reasoning..."
                )
                use_lite = False
                if on_event:
                    on_event("status", "ESCALATING (Higher Reasoning)")
                continue
        except Exception as e:
            viki_logger.error(f"Consciousness Stack failure: {e}")
            controller.signals.update_signal("frustration", 0.2)
            controller._reflex_recursion_depth = 0
            return f"My deliberation layer encountered an error: {e}"
        finally:
            controller._reflex_recursion_depth -= 1
            if controller._reflex_recursion_depth < 0:
                controller._reflex_recursion_depth = 0

        if viki_resp.action:
            # Deep coding/planning/complex: verifier-backed MCTS over ≥2 candidates.
            chosen_action = viki_resp.action
            coding_bon_done = False
            if should_run_mcts(cognitive_route, task_type) and (task_type or "").lower() == "coding":
                if on_event:
                    on_event("status", "Best-of-N worktree coding attempts")
                try:
                    bon = await run_coding_best_of_n(
                        controller, chosen_action, budget, user_input=user_input
                    )
                    if bon is not None:
                        coding_bon_done = True
                        meta = controller._last_response_meta_by_session.get(session_id) or {}
                        meta["coding_best_of_n"] = {
                            "passed": bon.get("passed"),
                            "score": bon.get("score"),
                            "attempts": len(bon.get("attempts") or []),
                            "diff_preview": (bon.get("diff") or "")[:1500],
                        }
                        controller._last_response_meta_by_session[session_id] = meta
                        # Winner already ran in a worktree; return scored summary (no double apply).
                        if bon.get("passed"):
                            return (
                                f"Best-of-N coding succeeded (score={bon.get('score')}).\n"
                                f"Winning diff preview:\n```\n{(bon.get('diff') or '')[:3000]}\n```\n"
                                "Re-run with merge_winner / apply the patch to land it on HEAD."
                            )
                        viki_logger.info(
                            "Best-of-N coding did not pass verify; falling through to MCTS/execute"
                        )
                except Exception as e:
                    viki_logger.warning("coding Best-of-N failed: %s", e)

            if should_run_mcts(cognitive_route, task_type) and not coding_bon_done:
                extras = budget.get("mcts_extra_actions") if isinstance(budget, dict) else None
                candidates = collect_mcts_candidates(
                    viki_resp.action,
                    viki_resp,
                    extras=extras if isinstance(extras, list) else None,
                    task_type=task_type,
                    user_input=user_input,
                )
                if len(candidates) >= 2:
                    if on_event:
                        on_event("status", f"MCTS evaluating {len(candidates)} branches")
                    try:
                        best, mcts_score = await run_mcts_tree_search(
                            controller, user_input, candidates, budget
                        )
                        if best is not None:
                            chosen_action = best
                            viki_logger.info(
                                "MCTS selected %s (score=%.2f) from %d candidates",
                                best.skill_name,
                                mcts_score,
                                len(candidates),
                            )
                            meta = controller._last_response_meta_by_session.get(session_id) or {}
                            meta["mcts"] = {
                                "candidates": [c.skill_name for c in candidates],
                                "winner": best.skill_name,
                                "score": mcts_score,
                            }
                            controller._last_response_meta_by_session[session_id] = meta
                    except Exception as e:
                        viki_logger.warning("MCTS search failed; using primary action: %s", e)

            skill_name = chosen_action.skill_name
            params = (chosen_action.parameters or {}).copy()

            check_res = controller.capabilities.check_permission(skill_name, params=params)

            viki_logger.info(
                f"[CAPABILITY LOG] Skill: {skill_name} | "
                f"Allowed: {check_res.allowed} | "
                f"JudgmentOutcome: {outcome.name}"
            )

            if not check_res.allowed:
                msg = f"Action '{skill_name}' planned, but capability check failed: {check_res.reason}"
                viki_logger.warning(msg)
                action_results.append({"action": skill_name, "error": msg, "step": react_step + 1})
                continue
            if not controller.safety.validate_action(skill_name, params):
                viki_logger.warning(f"Safety: validate_action blocked {skill_name}")
                action_results.append(
                    {
                        "action": skill_name,
                        "error": "Action blocked by safety policy.",
                        "step": react_step + 1,
                    }
                )
                continue

            severity = controller._skill_action_severity(skill_name, params)
            if severity in ["medium", "destructive"]:
                controller.pending_actions[session_id] = chosen_action
                reply = (viki_resp.final_response or "").strip()
                if not reply or reply.lower() in PLACEHOLDERS:
                    reply = "I understand. I have an action ready that needs your confirmation."
                diff_preview = controller._diff_preview(skill_name, params)
                safety_msg = (
                    f"{reply}\n\nSafety Check: This is a {severity} action. Confirm to proceed."
                )
                if diff_preview:
                    safety_msg += f"\n\n{diff_preview}"
                return safety_msg

            if controller.world.state.safety_zones.get(params.get("path", "")) == "protected":
                viki_logger.warning("Safety: Action targeting protected zone. Aborting.")
                return "Safety Block: My world model flags this target as protected."

            if controller.shadow_mode:
                viki_logger.info(
                    f"Shadow Mode: Simulating {skill_name}({safe_for_log(str(params))})"
                )
                return f"[Shadow Mode] Would execute: {skill_name}({params}). Set shadow_mode: false to run for real."

            if on_event:
                on_event("status", f"EXECUTING {skill_name}")
                on_event("tool_call", {"name": skill_name, "params": params})
            controller.history.take_snapshot(
                "ACTION_START", f"Executing {skill_name}", {"params": params}
            )

            contract_err = controller._validate_tool_contract_params(skill_name, params)
            if contract_err:
                controller.signals.update_signal("frustration", 0.35)
                selected_model = controller.model_router.get_model(capabilities=[task_type])
                selected_model.record_performance(0.0, False)
                controller.skill_registry.record_execution(skill_name, False, 0.0)
                controller.learning.save_failure(skill_name, contract_err, user_input)
                controller._last_response_meta_by_session[session_id] = {
                    "contract_error": contract_err
                }
                if react_step < max_react_steps - 1:
                    action_results.append(
                        {
                            "action": f"{skill_name}({params})",
                            "error": contract_err,
                            "step": react_step + 1,
                        }
                    )
                    continue
                return (
                    f"I must apologize. My tool contract rejected '{skill_name}': {contract_err}."
                )

            result, err, latency = await controller._execute_skill(skill_name, params, budget)

            if on_event:
                on_event("tool_result", result if result and not err else err or "no result")

            if not err and result is not None:
                output_err = controller._validate_skill_output(skill_name, result)
                if output_err:
                    err = output_err
                    result = None

            if err:
                controller.signals.update_signal("frustration", 0.3)
                controller.skill_registry.record_execution(skill_name, False, 0.0)
                controller.learning.save_failure(skill_name, err, user_input)

                controller.world.state.retry_count += 1
                viki_logger.info(
                    f"FSM: Tool failure detected. Retry count: {controller.world.state.retry_count}"
                )

                if controller.world.state.retry_count <= 3:
                    viki_logger.info(
                        "FSM: Transitioning to DEBUGGING state for autonomous repair. FORBIDDING REPLAN."
                    )
                    controller.world.state.current_phase = "DEBUGGING"
                    controller.world.save()

                    action_results.append(
                        {
                            "action": f"{skill_name}({params})",
                            "error": f"EXECUTION_FAILURE: {err}. Analysis required. DO NOT return to PLANNING phase. STAY in DEBUGGING/EXECUTING.",
                            "step": react_step + 1,
                        }
                    )
                    continue

                if "timed out" in err:
                    return f"I couldn't complete '{skill_name}' in time. Try a simpler request or retry."
                return f"I must apologize. My attempt to execute '{skill_name}' failed after {controller.world.state.retry_count} retries: {err}."
            selected_model = controller.model_router.get_model(capabilities=[task_type])
            selected_model.record_performance(latency, True)
            controller.skill_registry.record_execution(skill_name, True, latency)
            controller.signals.update_signal("confidence", 0.05)
            controller.world.track_app_usage(skill_name)
            action_results.append(
                {
                    "action": f"{skill_name}({params})",
                    "result": result[:1000],
                    "step": react_step + 1,
                }
            )
            if len(action_results) >= 2:
                last_two = action_results[-2:]
                act0 = (last_two[0].get("action") or "").split("(")[0]
                act1 = (last_two[1].get("action") or "").split("(")[0]
                res0 = (last_two[0].get("result") or last_two[0].get("error") or "").lower()
                res1 = (last_two[1].get("result") or last_two[1].get("error") or "").lower()
                no_result = (
                    "no results found" in res0
                    or "search error" in res0
                    or "no results found" in res1
                    or "search error" in res1
                )
                if act0 == act1 and no_result:
                    viki_logger.info(
                        f"ReAct: Stopping early after repeated empty results from {act0}."
                    )
                    controller.last_interaction_time = time.time()
                    summary = "\n".join(
                        [
                            f"Step {r['step']}: {r.get('result') or r.get('error')}"
                            for r in action_results
                        ]
                    )
                    final_output = controller._compress_output(
                        f"I tried {len(action_results)} search steps but didn't find useful results for that. "
                        f"You can rephrase or try a different question.\n\nExecution log:\n{summary}"
                    )
                    controller._last_response_meta_by_session[session_id] = {
                        "subtasks": action_results,
                        "total_steps": react_step + 1,
                    }
                    break
            if react_step < max_react_steps - 1:
                continue
            controller.last_interaction_time = time.time()
            controller._last_response_meta_by_session[session_id] = {
                "subtasks": action_results,
                "total_steps": max_react_steps,
            }
            llm_response = viki_resp.final_response or "Directive sequence concluded."
            all_results = "\n".join(
                [f"Step {r['step']}: {r.get('result') or r.get('error')}" for r in action_results]
            )
            final_output = controller._compress_output(
                f"{llm_response}\n\nExecution Logs:\n{all_results}"
            )
            break

        controller.last_interaction_time = time.time()
        assert viki_resp is not None
        llm_response = viki_resp.final_response or ""
        if not llm_response or llm_response.lower().strip() in PLACEHOLDERS:
            llm_response = "Intelligence stack synchronized. Directive processed."

        if action_results:
            clean_logs = []
            for r in action_results:
                res = r.get("result") or r.get("error") or ""
                if "Searching for" in res and len(res) < 100:
                    continue
                clean_logs.append(f"• {res}")

            if clean_logs:
                logs_str = "\n".join(clean_logs)
                final_output = controller._compress_output(
                    f"{llm_response}\n\n[SYSTEM_TRACE]\n{logs_str}"
                )
            else:
                final_output = controller._compress_output(llm_response)
        else:
            final_output = controller._compress_output(llm_response)
        controller._last_response_meta_by_session[session_id] = {
            "subtasks": action_results,
            "total_steps": max_react_steps,
        }
        break

    if final_output:
        try:
            final_output = await controller._maybe_auto_web_research(
                safe_input,
                final_output,
                viki_resp,
                action_results,
                session_id,
                on_event=on_event,
            )
        except Exception as e:
            viki_logger.warning("auto_web_research: %s", e)

    if task_type == "coding" and controller.world.state.execution_started:
        viki_logger.debug("Reflection bypassed: active execution session.")
    else:
        pass
    if (
        "viki_resp" in locals()
        and viki_resp
        and cognitive_route
        and cognitive_route.source != "cache"
        # Only cache pure-text answers: replaying a response whose turn ran
        # tools would claim side effects that never re-executed.
        and not action_results
        # confidence=0.0 is the deliberation layer's dedicated failure sentinel
        # (set only on its exception path) — never cache an error as an answer.
        and getattr(getattr(viki_resp, "final_thought", None), "confidence", 1.0) > 0.0
    ):
        try:
            resp_data = (
                viki_resp.model_dump() if hasattr(viki_resp, "model_dump") else viki_resp.dict()
            )
            controller.cognitive_router.store_response(safe_input, resp_data)
        except Exception as e:
            viki_logger.debug(f"Failed to cache response: {e}")

    try:
        intent_summ = "General Interaction"
        confidence = 1.0
        if "viki_resp" in locals() and viki_resp:
            if viki_resp.final_thought:
                intent_summ = (
                    getattr(viki_resp.final_thought, "intent_summary", None) or intent_summ
                )
            confidence = getattr(viki_resp, "confidence", 1.0)

        controller.memory.record_interaction(
            intent=intent_summ,
            action=str(action_results) if action_results else "reply",
            outcome=(final_output or "")[:500],
            confidence=confidence,
        )
        controller._create_tracked_task(
            controller.learning.analyze_session(
                controller.model_router.get_model(["reasoning"]),
                controller.memory.working.get_trace(session_id=session_id),
                (final_output or "")[:200],
            ),
            "session_learning",
        )

        try:
            cur = controller.memory.episodic.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM episodes")
            count = cur.fetchone()[0]
            if count > 0 and count % 20 == 0:
                controller._create_tracked_task(
                    controller.memory.episodic.consolidate(controller.model_router),
                    "memory_consolidation",
                )
        except Exception as db_err:
            viki_logger.debug(f"Dream cycle trigger check failed: {db_err}")
    except Exception as e:
        viki_logger.warning(f"Failed to reinforce memory: {e}")

    if final_output is None:
        final_output = "I completed processing but have no output to show."

    try:
        if cognitive_route is not None:
            meta = controller._last_response_meta_by_session.get(session_id) or {}
            meta["cognitive_route"] = cognitive_route.as_dict()
            meta["router_telemetry"] = controller.get_router_telemetry()
            controller._last_response_meta_by_session[session_id] = meta
    except Exception as e:
        viki_logger.debug("Cognitive route meta decoration failed: %s", e)

    try:
        if hasattr(controller.cortex, "get_reflex_candidates"):
            candidates = controller.cortex.get_reflex_candidates()
            for candidate in candidates:
                controller.evolution.propose_mutation(
                    m_type="reflex",
                    description=f"Add reflex shortcut for '{candidate['input']}' -> {candidate['skill']}",
                    value={
                        "input": candidate["input"],
                        "skill": candidate["skill"],
                        "params": candidate["params"],
                    },
                    pattern_id=candidate["input"],
                )
                controller.evolution.record_success(candidate["input"])
    except Exception as e:
        viki_logger.debug("Evolution proposal skipped: %s", e)

    try:
        from viki.core.resource_budget import RAMBudgetOptimizer

        RAMBudgetOptimizer().optimize_memory()
    except Exception as e:
        viki_logger.debug("RAM optimization cleanup skipped: %s", e)

    controller.memory.working.add_message("assistant", final_output, session_id=session_id)
    return final_output


class MCTSNode:
    """
    Node in the Monte Carlo Tree Search for agent step planning & action evaluation.
    """

    def __init__(self, action: ActionCall | None = None, parent: MCTSNode | None = None):
        self.action = action
        self.parent = parent
        self.children: list[MCTSNode] = []
        self.visits: int = 0
        self.score: float = 0.0  # cumulative reward
        self.observation: str | None = None
        self.untried: list[ActionCall] = []

    def ucb1(self, exploration_weight: float = 1.414) -> float:
        """Calculate Upper Confidence Bound for Tree Search node selection."""
        import math

        if self.visits == 0:
            return float("inf")
        parent_visits = self.parent.visits if self.parent else 1
        return (self.score / self.visits) + exploration_weight * math.sqrt(
            math.log(max(parent_visits, 1)) / self.visits
        )

    def select_best_child(self) -> MCTSNode | None:
        if not self.children:
            return None
        return max(self.children, key=lambda child: child.ucb1())

    def most_visited_child(self) -> MCTSNode | None:
        if not self.children:
            return None
        return max(self.children, key=lambda child: (child.visits, child.score))


def _mcts_budget_limits(budget: dict[str, Any]) -> tuple[int, float]:
    """Return (max_simulations, max_seconds) with hard caps."""
    max_sims = int(budget.get("mcts_max_simulations") or budget.get("mcts_sims") or 8)
    max_sims = max(2, min(max_sims, 32))
    max_seconds = float(budget.get("mcts_max_seconds") or budget.get("time") or 12.0)
    max_seconds = max(1.0, min(max_seconds, 60.0))
    return max_sims, max_seconds


async def _score_mcts_rollout(
    controller: Any,
    user_input: str,
    action: ActionCall,
    result: str | None,
    err: str | None,
    budget: dict[str, Any],
) -> float:
    """
    Verifier-backed process reward in roughly [-1, 1].

    Prefers ExecutionEvaluator / LLMJudge when present; never uses output length.
    """
    if err:
        return -0.8
    if result is None:
        return -0.5

    task = budget.get("mcts_eval_task") if isinstance(budget.get("mcts_eval_task"), dict) else None
    candidate = str(result)

    # Coding path: sandboxed execution grader when tests are supplied.
    if task and (task.get("test_code") or task.get("expected_stdout")):
        try:
            from viki.core.evaluators import ExecutionEvaluator

            scored = ExecutionEvaluator().evaluate(task, candidate)
            return max(-1.0, min(1.0, (scored.score * 2.0) - 1.0))
        except Exception as e:
            viki_logger.debug("MCTS ExecutionEvaluator failed: %s", e)

    # Optional LLM judge (explicit flag — avoid extra cost by default).
    if budget.get("mcts_use_llm_judge") and hasattr(controller, "model_router"):
        try:
            from viki.core.evaluators import LLMJudgeEvaluator

            judge = LLMJudgeEvaluator(controller.model_router)
            judge_task = task or {
                "question": user_input,
                "rubric": "Reward actions that correctly advance the user goal without errors.",
            }
            scored = await judge.evaluate(judge_task, candidate)
            return max(-1.0, min(1.0, (scored.score * 2.0) - 1.0))
        except Exception as e:
            viki_logger.debug("MCTS LLMJudge failed: %s", e)

    # Process reward: success + self-critique signal when available.
    reward = 0.35
    lower = candidate.lower()
    if any(tok in lower for tok in ("error", "failed", "traceback", "exception", "denied")):
        reward -= 0.45
    if any(tok in lower for tok in ("done", "success", "passed", "ok", "completed")):
        reward += 0.2
    try:
        critique = getattr(controller, "self_critique", None)
        if critique is not None and hasattr(critique, "quick_score"):
            qs = critique.quick_score(user_input, candidate)
            if isinstance(qs, (int, float)):
                reward = 0.5 * reward + 0.5 * (float(qs) * 2.0 - 1.0)
    except Exception as e:
        viki_logger.debug("MCTS self_critique skipped: %s", e)
    return max(-1.0, min(1.0, reward))


_CODING_BON_SKILLS = frozenset(
    {"plan_edit", "plan_edit_skill", "coding_workflow", "dev_skill", "dev_tools"}
)


def should_run_mcts(cognitive_route: Any, task_type: str) -> bool:
    """True for deep coding/planning/complex routes (Reflex/Chatter unchanged)."""
    tt = (task_type or "").lower()
    if tt not in {"coding", "planning", "complex"}:
        return False
    if cognitive_route is None:
        return False
    if getattr(cognitive_route, "use_mcts", False):
        return True
    outcome = getattr(cognitive_route, "outcome", None)
    outcome_val = getattr(outcome, "value", str(outcome or "")).lower()
    return outcome_val == "deep" or bool(getattr(cognitive_route, "use_ensemble", False))


async def run_coding_best_of_n(
    controller: Any,
    action: ActionCall,
    budget: dict[str, Any],
    user_input: str = "",
) -> dict[str, Any] | None:
    """
    Best-of-N coding attempts in isolated git worktrees, scored by pytest.

    Temporarily points ``settings.system.workspace_dir`` at each worktree so
    ``plan_edit`` / patch verify run against the sandboxed tree.
    """
    if action is None or action.skill_name not in _CODING_BON_SKILLS:
        return None
    if budget.get("best_of_n") in (0, "0", False):
        return None

    import os

    from viki.core.worktree_runner import WorktreeRunner

    settings = getattr(controller, "settings", None)
    if not isinstance(settings, dict):
        return None
    system = settings.setdefault("system", {})
    original_ws = system.get("workspace_dir", "./workspace")
    workspace = os.path.abspath(
        budget.get("workspace_dir")
        or system.get("repo_dir")
        or system.get("workspace_dir")
        or os.getcwd()
    )
    n = max(2, min(int(budget.get("best_of_n") or 3), 5))
    verify_cmd = budget.get("verify_cmd")
    if isinstance(verify_cmd, str):
        verify_cmd = verify_cmd.split()
    runner = WorktreeRunner(
        workspace_dir=workspace,
        verify_cmd=verify_cmd if isinstance(verify_cmd, list) else None,
        verify_timeout=int(budget.get("verify_timeout") or 120),
    )

    async def _attempt(wt_path: str) -> dict[str, Any]:
        system["workspace_dir"] = wt_path
        try:
            params = dict(action.parameters or {})
            if user_input and "goal" not in params:
                params["goal"] = user_input[:500]
            result, err, _lat = await controller._execute_skill(action.skill_name, params, budget)
            return {
                "score": 0.0 if err else 0.5,
                "result": result,
                "error": err,
            }
        finally:
            system["workspace_dir"] = original_ws

    from viki.core.telemetry_service import start_span

    with start_span(
        "mcts.coding_best_of_n",
        attributes={"n": n, "skill": action.skill_name, "workspace": workspace},
    ) as span:
        try:
            winner, results = await runner.run(_attempt, n=n, merge_winner=False)
        except Exception as e:
            viki_logger.debug("coding Best-of-N failed: %s", e)
            system["workspace_dir"] = original_ws
            return None
        system["workspace_dir"] = original_ws
        span["attributes"]["winner_passed"] = bool(winner and winner.passed)
        span["attributes"]["winner_score"] = float(winner.score) if winner else -1.0
        if winner is None:
            return None
        return {
            "winner": winner.as_dict(),
            "attempts": [r.as_dict() for r in results],
            "action": action,
            "passed": winner.passed,
            "score": winner.score,
            "diff": winner.diff,
        }


# Sibling skills proposed when the cortex emits only one ActionCall.
_MCTS_SIBLINGS: dict[str, list[str]] = {
    "coding": ["plan_edit", "shell", "filesystem_skill", "code_search", "dev_skill"],
    "planning": ["research", "plan_edit", "memory", "code_search"],
    "complex": ["research", "shell", "plan_edit", "swarm_control"],
    "research": ["research", "browser", "memory"],
}


def propose_mcts_siblings(
    primary: ActionCall | None,
    task_type: str = "coding",
    user_input: str = "",
    max_extras: int = 2,
) -> list[ActionCall]:
    """Propose alternate ActionCalls so MCTS always has ≥2 branches when possible."""
    if primary is None or not primary.skill_name:
        return []
    pool = list(_MCTS_SIBLINGS.get((task_type or "").lower(), _MCTS_SIBLINGS["complex"]))
    extras: list[ActionCall] = []
    for skill in pool:
        if skill == primary.skill_name:
            continue
        # Carry over a useful query/path hint when present.
        params: dict[str, Any] = {}
        src = primary.parameters or {}
        for key in ("query", "path", "instruction", "goal", "prompt", "cmd", "command"):
            if key in src:
                params[key] = src[key]
        if "query" not in params and user_input:
            params["query"] = user_input[:240]
        extras.append(ActionCall(skill_name=skill, parameters=params))
        if len(extras) >= max_extras:
            break
    return extras


def collect_mcts_candidates(
    primary: ActionCall | None,
    viki_resp: Any = None,
    extras: list[ActionCall] | None = None,
    task_type: str = "coding",
    user_input: str = "",
) -> list[ActionCall]:
    """Deduplicate primary action + any alternate ActionCalls for MCTS expansion."""
    seen: set[str] = set()
    out: list[ActionCall] = []

    def _add(act: ActionCall | None) -> None:
        if act is None or not act.skill_name:
            return
        key = f"{act.skill_name}:{sorted((act.parameters or {}).items())}"
        if key in seen:
            return
        seen.add(key)
        out.append(act)

    _add(primary)
    if extras:
        for a in extras:
            _add(a)
    # Ensemble may attach alternate suggested actions on the response.
    if viki_resp is not None:
        for alt in getattr(viki_resp, "alternate_actions", None) or []:
            if isinstance(alt, ActionCall):
                _add(alt)
            elif isinstance(alt, dict) and alt.get("skill_name"):
                _add(ActionCall(skill_name=alt["skill_name"], parameters=alt.get("parameters") or {}))
        thought = getattr(viki_resp, "final_thought", None)
        rejected = getattr(thought, "rejected_strategies", None) or []
        for strat in rejected:
            if isinstance(strat, ActionCall):
                _add(strat)
            elif isinstance(strat, str) and strat.strip() and " " not in strat.strip():
                # Bare skill name from rejected_strategies
                _add(ActionCall(skill_name=strat.strip(), parameters={}))
    # Ensure ≥2 candidates for deep routes via sibling skills.
    if len(out) < 2 and primary is not None:
        for sib in propose_mcts_siblings(primary, task_type=task_type, user_input=user_input):
            _add(sib)
            if len(out) >= 3:
                break
    return out


async def run_mcts_tree_search(
    controller: Any,
    user_input: str,
    candidate_actions: list[ActionCall],
    budget: dict[str, Any],
) -> tuple[ActionCall | None, float]:
    """
    Real MCTS over candidate actions: select (UCB1) → expand → simulate (verifier) → backprop.

    Hard-capped by simulation count and wall-clock from ``budget``. Scoring never uses
    output length; see ``_score_mcts_rollout``.
    """
    if not candidate_actions:
        return None, -1.0

    max_sims, max_seconds = _mcts_budget_limits(budget)
    t0 = time.perf_counter()
    root = MCTSNode()
    root.untried = list(candidate_actions)

    # Seed first-level children so UCB has something to select immediately.
    for act in candidate_actions:
        child = MCTSNode(action=act, parent=root)
        root.children.append(child)

    from viki.core.telemetry_service import start_span

    with start_span(
        "mcts.search",
        attributes={
            "candidates": len(candidate_actions),
            "max_sims": max_sims,
            "max_seconds": max_seconds,
        },
    ) as span:
        for sim in range(max_sims):
            if (time.perf_counter() - t0) >= max_seconds:
                span["attributes"]["budget_abort"] = True
                span["attributes"]["sims_completed"] = sim
                break

            # --- Select ---
            node = root
            while node.children and not node.untried:
                nxt = node.select_best_child()
                if nxt is None:
                    break
                node = nxt

            # --- Expand (one untried action at this depth, if any) ---
            if node.untried:
                act = node.untried.pop()
                child = MCTSNode(action=act, parent=node)
                node.children.append(child)
                node = child

            if not node.action:
                continue

            skill_name = node.action.skill_name
            params = node.action.parameters or {}
            check_res = controller.capabilities.check_permission(skill_name, params=params)
            if not check_res.allowed:
                reward = -1.0
                node.observation = f"permission denied: {check_res.reason}"
            else:
                # --- Simulate ---
                # Never mutate during search for medium/destructive skills; score dry.
                # Safe/read skills may execute once for a real observation.
                with start_span(
                    "mcts.simulate",
                    attributes={"skill": skill_name, "sim": sim},
                ) as sim_span:
                    severity = "low"
                    try:
                        severity = controller._skill_action_severity(skill_name, params)
                    except Exception:
                        severity = "low"
                    result: str | None
                    err: str | None
                    if severity in ("medium", "destructive") and not budget.get(
                        "mcts_force_execute"
                    ):
                        result = (
                            f"[dry-run] would execute {skill_name}({params}) "
                            f"for goal: {user_input[:200]}"
                        )
                        err = None
                        sim_span["attributes"]["dry_run"] = True
                    else:
                        result, err, _latency = await controller._execute_skill(
                            skill_name, params, budget
                        )
                        sim_span["attributes"]["dry_run"] = False
                    reward = await _score_mcts_rollout(
                        controller, user_input, node.action, result, err, budget
                    )
                    node.observation = (err or str(result or ""))[:500]
                    sim_span["attributes"]["verifier_score"] = reward
                    sim_span["attributes"]["error"] = bool(err)

            # --- Backprop ---
            cursor: MCTSNode | None = node
            while cursor is not None:
                cursor.visits += 1
                cursor.score += reward
                cursor = cursor.parent

        span["attributes"]["sims_completed"] = span["attributes"].get(
            "sims_completed", max_sims
        )

    winner = root.most_visited_child()
    if winner is None or winner.action is None:
        return candidate_actions[0], -1.0
    avg = (winner.score / winner.visits) if winner.visits else -1.0
    # Map average reward [-1,1] to a positive display score for callers/tests.
    display = 5.0 + (avg * 5.0)
    return winner.action, display
