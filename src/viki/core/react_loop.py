import time
from typing import Any

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
    agency_weights: str,
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
                result, err, latency = await controller._execute_skill(skill_name, params, budget)
                if not err and result is not None:
                    try:
                        controller.skill_registry.record_execution(skill_name, True, latency)
                        controller.signals.update_signal("confidence", 0.05)
                        controller.world.track_app_usage(skill_name)
                    except Exception:
                        pass
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
                    return reflex_msg
                if err:
                    try:
                        controller.reflex.report_failure(safe_input)
                    except Exception:
                        pass
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

            if on_event:
                on_event("thought", viki_resp.final_thought.intent_summary)
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
            skill_name = viki_resp.action.skill_name
            params = (viki_resp.action.parameters or {}).copy()

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
                controller.pending_actions[session_id] = viki_resp.action
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
        llm_response = viki_resp.final_response
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
        viki_logger.debug(f"Evolution proposal skipped: {e}")

    controller.memory.working.add_message("assistant", final_output, session_id=session_id)
    return final_output
