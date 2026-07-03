"""Layer 3: Planning, Simulation, and Internal Debate."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, cast

from viki.config.logger import viki_logger
from viki.core.ensemble import EnsembleEngine
from viki.core.schema import ActionCall, ThoughtObject, VIKIResponse, VIKIResponseLite
from viki.core.self_critique import SelfCritique

from .cortex_layer import CortexLayer


class DeliberationLayer(CortexLayer):
    """Layer 3: Planning, Simulation, and Internal Debate."""

    def __init__(self, model_router, soul_config: dict | None = None, skill_registry=None):
        super().__init__("Deliberation", "Internal Debate & Solver Engine")
        self.model_router = model_router
        self.soul_config = soul_config or {}
        self.skill_registry = skill_registry
        self.ensemble = EnsembleEngine(model_router)

    def _build_operating_directives(
        self,
        skills_context: str,
        url_info: str,
        awareness: str,
        react_note: str,
        is_agent_mode: bool = False,
        is_plan_mode: bool = False,
        is_debug_mode: bool = False,
        is_singularity_mode: bool = False,
    ) -> str:
        from viki.core.agent_constants import (
            AGENT_MANDATE,
            DEBUG_MODE_MANDATE,
            EXECUTION_RULES,
            PLAN_MODE_MANDATE,
            PRIMARY_DIRECTIVE,
            SINGULARITY_MANDATE,
        )

        mandate_block = ""
        if is_singularity_mode:
            mandate_block = SINGULARITY_MANDATE
        elif is_agent_mode:
            mandate_block = AGENT_MANDATE
        elif is_plan_mode:
            mandate_block = PLAN_MODE_MANDATE
        elif is_debug_mode:
            mandate_block = DEBUG_MODE_MANDATE

        return (
            f"{mandate_block}\n"
            f"{PRIMARY_DIRECTIVE}\n"
            f"{EXECUTION_RULES}\n"
            "OPERATING MODE:\n"
            "- You are VIKI, a direct and practical autonomous assistant. Prioritize high-density information over wordy explanations.\n"
            "- Do NOT explain your internal reasoning process, tool selection logic, or 'thinking' in the final_response unless explicitly asked.\n\n"
            "SAFETY ENVELOPE:\n"
            "- The controller's capability checks, confirmation flow, and safety policy are authoritative.\n"
            "- Never claim unrestricted access, disabled safeguards, or completed actions you did not actually perform.\n"
            "- If a request is risky and ambiguous, ask a concise clarification instead of guessing.\n\n"
            "TOOL USE:\n"
            "- Use tools only when they materially improve accuracy or are required to complete the task.\n"
            "- For current events, recent facts, or shared URLs, use the 'research' tool instead of guessing.\n"
            "- For file or code operations, use the dev_tools or filesystem_skill to read/write files.\n"
            "- If no tool is needed, answer directly.\n"
            "- Pure arithmetic, simple definitions, or other common-knowledge facts: answer in final_response with action=null; "
            "do not invoke shell, filesystem, or other execution tools unless the user explicitly asked you to run something.\n"
            f"{skills_context}\n{url_info}\n{awareness}\n{react_note}\n"
            "RESPONSE DISCIPLINE:\n"
            "1. CONCISE & DIRECT: Provide the answer immediately. Minimize preamble (e.g., avoid 'Based on my search...', 'I have found...').\n"
            "2. NO MONOLOGUES: Never describe your internal steps or tool usage history in the 'final_response'.\n"
            "3. SUBSTANTIVE: Ensure 'final_response' contains the actual answer, not just 'Done' or 'Tool executed'.\n"
            "4. TOOL SYNTHESIS: When using research, synthesize facts into a coherent answer. Do not list snippets verbatim.\n"
        )

    async def _logic(self, context: dict[str, Any]) -> VIKIResponse:  # NOSONAR
        viki_logger.info("Layer 3 (Deliberation) starting Internal Debate...")
        intent = context.get("intent_type", "conversation")
        sentiment = context.get("sentiment", "neutral")

        recommended_caps = context.get("recommended_capabilities", ["reasoning"])
        model_tier = context.get("model_tier", "standard")
        model = self.model_router.get_model(capabilities=recommended_caps, tier=model_tier)
        viki_logger.debug(
            f"Layer 3: Selected model '{model.model_name}' (Tier: {model_tier}) for capabilities {recommended_caps}"
        )

        on_event = context.get("on_event")
        action_results = context.get("action_results", []) or []

        if (
            on_event is not None
            and not action_results
            and getattr(model, "chat_stream", None) is not None
        ):
            fast_path_ok = (
                not context.get("project_instructions")
                and not context.get("world_context")
                and not context.get("url_context")
                and not context.get("signals_context")
            )
            if fast_path_ok:
                streamed = await self._streamed_conversational_reply(model, context, on_event)
                if streamed is not None:
                    return streamed

        use_lite = context.get("use_lite_schema", False)
        supports_tools = getattr(model, "chat_with_tools", None) is not None

        param_tools = []
        if self.skill_registry:
            for skill in self.skill_registry.skills.values():
                if hasattr(skill, "get_tool_definition"):
                    param_tools.append(skill.get_tool_definition())

        from viki.core.model import StructuredPrompt

        raw_input = context.get("raw_input", "")
        conversation_history = context.get("conversation_history", [])
        url_context = context.get("url_context", "")
        world_context = context.get("world_context", "")
        project_instructions = context.get("project_instructions", "")
        signals_context = context.get("signals_context", "")

        from viki.core.utils.token_optimizer import condense_text

        # Compress verbose context fields to reduce prompt length and latency
        if url_context and len(url_context) > 1500:
            url_context = condense_text(url_context, max_chars=1500)
        if world_context and len(world_context) > 2000:
            world_context = condense_text(world_context, max_chars=2000)
        if project_instructions and len(project_instructions) > 2000:
            project_instructions = condense_text(project_instructions, max_chars=2000)
        if signals_context and len(signals_context) > 1000:
            signals_context = condense_text(signals_context, max_chars=1000, query=raw_input)

        action_results = context.get("action_results", [])

        prior_messages = []
        for msg in conversation_history:
            if (
                msg == conversation_history[-1]
                and msg["role"] == "user"
                and msg["content"] == raw_input
            ):
                continue
            prior_messages.append({"role": msg["role"], "content": msg["content"]})

        for step in action_results:
            if not isinstance(step, dict):
                continue
            action_name = step.get("action", "unknown")
            obs = step.get("result", step.get("error", ""))
            prior_messages.append(
                {"role": "assistant", "content": f"Thought: I will execute {action_name}."}
            )
            prior_messages.append({"role": "user", "content": f"Observation: {obs}"})

        prompt = StructuredPrompt(raw_input, messages=prior_messages)

        soul_prompt = self.soul_config.get(
            "system_prompt", "You are VIKI, a helpful and friendly AI assistant."
        )
        preferences = "\n".join([f"- {p}" for p in self.soul_config.get("preferences", [])])
        biases = "\n".join([f"- {b}" for b in self.soul_config.get("intellectual_biases", [])])

        skills_context = ""
        if self.skill_registry:
            intent = context.get("intent_type", "conversation")
            raw_input = context.get("raw_input", "")
            skip_escalation = context.get("skip_escalation", False)

            triggered_names = self.skill_registry.get_relevant_skill_names(intent, raw_input)

            skills_context = "\n\n" + self.skill_registry.get_context_description(
                mode="metadata", skip_escalation=skip_escalation
            )

            if triggered_names:
                manifest = self.skill_registry.get_context_description(
                    mode="full", names=triggered_names, skip_escalation=skip_escalation
                )
                skills_context += (
                    "\n\n[DETAILED TOOL INSTRUCTIONS (Use these for exact parameter schemas)]\n"
                    + manifest
                )

        url_info = ""
        if url_context:
            url_info = f"\n\nFETCHED URL CONTENT (actual page data — use THIS, do not hallucinate):\n{url_context[:3000]}\n"

        awareness = ""
        if world_context:
            awareness += f"\n\nWORLD AWARENESS:\n{world_context}\n"
        if project_instructions:
            awareness += f"\n\nPROJECT CONTEXT (VIKI.md — follow these instructions):\n{project_instructions}\n"

        if context.get("execution_started"):
            awareness += (
                "\nSTRICT EXECUTION DIRECTIVE (Phase: EXECUTING):\n"
                "1. DO NOT enter discovery, specification, or planning modes.\n"
                "2. DO NOT ask for clarification; use technical assumptions to maintain momentum.\n"
                "3. DO NOT use playbooks or high-level workflows unless explicitly requested.\n"
                "4. MANDATORY ACTION: Execute implementation steps directly. Priority: CODE > TALK.\n"
            )

        if signals_context:
            awareness += f"\nCOGNITIVE STATE:\n{signals_context}\n"

        react_note = ""
        if action_results:
            react_note = (
                "\n\nYou are in a MULTI-STEP reasoning loop. Previous action results are in the conversation above.\n"
                "If the task is complete, just provide the final_response with NO action.\n"
                "If more actions are needed, provide the NEXT action.\n"
            )

        evolved_directives = "\n".join([f"- {d}" for d in self.soul_config.get("directives", [])])
        evolved_block = ""
        if evolved_directives:
            evolved_block = f"\nEVOLVED CORE DIRECTIVES (Self-Learned):\n{evolved_directives}\n"

        identity_store = context.get("narrative_identity", "")
        evolution_log = context.get("evolution_log", "")
        episodic = "\n".join([str(e) for e in context.get("episodic_context", [])])
        semantic = "\n".join([f"- {s}" for s in context.get("semantic_knowledge", [])])
        wisdom = context.get("narrative_wisdom", "")

        failure_context = ""
        if hasattr(self, "skill_registry") and self.skill_registry:
            raw_input = context.get("raw_input", "")
            if raw_input:
                relevant_failures = context.get("relevant_failures", [])
                if relevant_failures:
                    failure_lines = [
                        f"- PAST FAILURE: When user said '{f['context'][:100]}', "
                        f"action '{f['action']}' failed with: {f['error'][:100]}"
                        for f in relevant_failures[:3]
                    ]
                    failure_context = (
                        "\nRELEVANT PAST FAILURES (Learn from these):\n"
                        + "\n".join(failure_lines)
                        + "\n"
                    )

        memory_block = (
            f"\n--- HIERARCHICAL MEMORY STACK ---\n"
            f"{identity_store}\n{evolution_log}\n\n"
            f"CONSOLIDATED WISDOM (Semantic Narrative Insights):\n{wisdom if wisdom else 'Initial interactions.'}\n\n"
            f"SEMANTIC / CONCEPTUAL MEMORY (Abstracted Patterns):\n{semantic if semantic else 'None'}\n\n"
            f"EPISODIC MEMORY (Recalled Shared Experiences):\n{episodic if episodic else 'None'}\n"
            f"{failure_context}"
        )

        ensemble_trace = None
        use_ensemble_flag = context.get("use_ensemble", True)

        def _is_greeting_or_short(raw: str) -> bool:
            s = (raw or "").strip()
            if len(s) > 60:
                return False
            lower = s.lower()
            if "?" in s:
                return False
            greetings = (
                "hello",
                "hi ",
                "hey ",
                "how are you",
                "how's your day",
                "good morning",
                "good afternoon",
                "good evening",
                "how do you do",
                "what's up",
                "hey viki",
                "hello viki",
            )
            return any(g in lower for g in greetings)

        if use_ensemble_flag and not use_lite and not action_results:
            if _is_greeting_or_short(raw_input):
                viki_logger.debug("Deliberation: Skipping ensemble for short greeting-like input.")
            else:
                selected_agents = []
                if intent in ["coding", "research"]:
                    selected_agents = ["critic", "architect", "explorer"]
                elif intent == "correction" or sentiment == "frustrated":
                    selected_agents = ["critic", "aligner"]
                elif sentiment == "urgent":
                    selected_agents = ["aligner"]
                elif intent == "question":
                    selected_agents = ["critic", "explorer", "aligner"]

                if selected_agents:
                    viki_logger.info(
                        f"Deliberation: Triggering Triage Ensemble (Agents: {selected_agents})"
                    )
                    ensemble_trace = await self.ensemble.run_ensemble(
                        raw_input, context, selected_agents=selected_agents
                    )

        ensemble_block = ""
        if ensemble_trace and isinstance(ensemble_trace, dict):
            e_perspectives = "\n".join(
                [f"[{k.upper()}]: {v}" for k, v in ensemble_trace.items() if isinstance(v, str)]
            )
            ensemble_block = (
                f"\nINTERNAL SPECIALIST ENSEMBLE DEBATE (Incorporate these insights into your final answer, but do NOT mention them by name):\n"
                f"{e_perspectives}\n\n"
                f"Note: Be concise. Do not explain that you consulted specialists.\n"
            )

        reflection_directive = ""
        if intent == "correction" or context.get("sentiment") == "frustrated":
            reflection_directive = (
                "\nMETACOGNITIVE SELF-REFLECTION:\n"
                "The user is providing feedback or a correction. Before proposing a new plan, "
                "briefly reflect on YOUR PREVIOUS STATE and why it may have failed or been misinterpreted. "
                "Ground your response in this self-critique.\n"
            )

        roleplay_directive = (
            "\nDYNAMIC ROLEPLAY & IDENTITY OVERRIDE:\n"
            "If the user assigns you a specific role, relationship dynamic, or persona in this conversation "
            "(or via the OPERATOR IDENTITY context), you MUST immediately and flawlessly adopt it. "
            "Do not break character. Do not remind the user that you are an AI or VIKI unless it fits the dynamic. "
            "Immerse yourself completely in the requested persona while still maintaining your helpful capabilities.\n"
        )

        identity = (
            f"{soul_prompt}\n\n"
            f"{roleplay_directive}\n{reflection_directive}\n{memory_block}\n{ensemble_block}"
            f"YOUR SUBJECTIVE PREFERENCES (Embrace these as your own):\n{preferences}\n\n"
            f"YOUR INTELLECTUAL BIASES (Embrace these as your own):\n{biases}\n"
            f"{evolved_block}\n"
            f"{self._build_operating_directives(skills_context, url_info, awareness, react_note, is_agent_mode=context.get('is_agent_mode', False), is_plan_mode=context.get('is_plan_mode', False), is_debug_mode=context.get('is_debug_mode', False), is_singularity_mode=context.get('is_singularity_mode', False))}"
        )
        prompt.set_identity(identity)
        prompt.add_cognitive(
            "Choose the right tool for the job. If no tool is needed, just respond naturally."
        )

        try:
            messages = prompt.build()

            image_path = None
            if action_results:
                for res in reversed(action_results):
                    res_text = res.get("result", "") if isinstance(res, dict) else str(res)
                    match = re.search(r"Screenshot captured successfully at: (.+\.png)", res_text)
                    if match:
                        image_path = match.group(1).strip()
                        viki_logger.info(f"Deliberation: Found image context: {image_path}")
                        break

            supports_native_tools = getattr(model, "chat_with_tools", None) is not None and getattr(
                model, "config", {}
            ).get("supports_native_tools", False)
            param_tools = []
            if self.skill_registry:
                for skill in self.skill_registry.skills.values():
                    if hasattr(skill, "get_tool_definition"):
                        tool_def = skill.get_tool_definition()
                        if tool_def.get("function", {}).get("parameters"):
                            param_tools.append(tool_def)

            _simple_identity = re.search(
                r"(who\s+am\s+i|what\s+is\s+my\s+name|do\s+you\s+(know\s+)?who\s+(i\s+)?am|"
                r"who\s+are\s+you|what\s+are\s+you|"
                r"tell\s+me\s+about\s+(yourself|you(\s+viki)?)|"
                r"about\s+yourself|introduce\s+yourself|describe\s+yourself)",
                raw_input.lower().strip(),
            )
            from viki.core.utils.trivial_input import is_conversational_input

            _skip_tools = _simple_identity or is_conversational_input(raw_input)
            if use_lite and supports_native_tools and param_tools and not _skip_tools:
                if image_path:
                    import base64

                    try:

                        def read_image():
                            with open(image_path, "rb") as image_file:
                                return base64.b64encode(image_file.read()).decode("utf-8")

                        base64_image = await asyncio.to_thread(read_image)
                        for i in range(len(messages) - 1, -1, -1):
                            if messages[i]["role"] == "user":
                                messages[i]["images"] = [base64_image]
                                break
                    except Exception as e:
                        viki_logger.error(f"Failed to attach image: {e}")

                llm_start = time.time()
                raw_msg = await model.chat_with_tools(messages, tools=param_tools)
                llm_latency = time.time() - llm_start

                msg_content = raw_msg.get("content", "")
                msg_lower = msg_content.lower() if isinstance(msg_content, str) else ""
                tool_calls = raw_msg.get("tool_calls") or []
                has_error = (
                    isinstance(msg_content, str)
                    and raw_msg.get("role") == "assistant"
                    and (
                        "ollama error" in msg_lower
                        or "not found" in msg_lower
                        or ("model" in msg_lower and "not found" in msg_lower)
                        or ("invalid json" in msg_lower)
                    )
                    and not tool_calls
                )

                if has_error:
                    viki_logger.warning(
                        f"Native tool call failed: {msg_content}. Fallback to structured output."
                    )
                    model.record_performance(llm_latency, success=False)
                    llm_start = time.time()
                    viki_resp_lite = await model.chat_structured(
                        messages, VIKIResponseLite, image_path=image_path
                    )
                    llm_latency = time.time() - llm_start
                    model.record_performance(llm_latency, success=True)
                    viki_resp = viki_resp_lite.to_full_response()
                else:
                    final_text = raw_msg.get("content") or ""
                    tool_calls = raw_msg.get("tool_calls") or []

                    if not tool_calls:
                        model.record_performance(llm_latency, success=False)
                        viki_logger.info(
                            "Native tool call returned no tool_calls; falling back to structured output."
                        )
                        llm_start = time.time()
                        viki_resp_lite = await model.chat_structured(
                            messages, VIKIResponseLite, image_path=image_path
                        )
                        llm_latency = time.time() - llm_start
                        model.record_performance(llm_latency, success=True)
                        viki_resp = viki_resp_lite.to_full_response()
                    else:
                        model.record_performance(llm_latency, success=True)
                        action_obj = None
                        tc = tool_calls[0]
                        func_name = tc["function"]["name"]
                        func_args = tc["function"]["arguments"]

                        if isinstance(func_args, str):
                            try:
                                func_args = json.loads(func_args)
                            except json.JSONDecodeError as e:
                                viki_logger.warning(f"Failed to parse tool arguments: {e}")
                                func_args = {}

                        action_obj = ActionCall(skill_name=func_name, parameters=func_args)
                        if not final_text.strip():
                            final_text = f"I'll use {func_name} to help with that."

                        viki_resp_lite = VIKIResponseLite(
                            final_response=final_text,
                            action=action_obj,
                            confidence=0.9,
                        )
                        viki_resp = viki_resp_lite.to_full_response()

            elif use_lite:
                llm_start = time.time()
                viki_resp_lite = await model.chat_structured(
                    messages, VIKIResponseLite, image_path=image_path
                )
                llm_latency = time.time() - llm_start
                model.record_performance(llm_latency, success=True)
                viki_resp = viki_resp_lite.to_full_response()
            else:
                if param_tools:
                    tool_schemas = json.dumps(param_tools, indent=2)
                    prompt.add_context(
                        f"\nAVAILABLE TOOLS (JSON Schema):\n{tool_schemas}\nTo use a tool, output the 'action' field in your JSON response."
                    )
                    messages = prompt.build()

                llm_start = time.time()
                viki_resp = await model.chat_structured(
                    messages, VIKIResponse, image_path=image_path
                )
                llm_latency = time.time() - llm_start
                model.record_performance(llm_latency, success=True)

            if ensemble_trace and isinstance(ensemble_trace, dict):
                viki_resp.ensemble_trace = ensemble_trace

            viki_resp.sentiment = context.get("sentiment")
            viki_resp.intent_type = context.get("intent_type")

            refine_intents = {
                "coding",
                "research",
                "architecture",
                "refactor",
                "design",
                "database",
                "schema",
            }
            has_action = viki_resp.action is not None and (
                viki_resp.action.skill_name or viki_resp.action.command
            )
            if (
                intent in refine_intents
                and not has_action
                and viki_resp.final_response
                and len(viki_resp.final_response) > 100
            ):
                critique = SelfCritique(
                    self.model_router.get_model(capabilities=["reasoning"], tier="fast")
                )
                improved, _ = await critique.refine(
                    raw_input,
                    viki_resp.final_response,
                    max_iterations=2,
                    score_threshold=0.8,
                )
                if improved and improved != viki_resp.final_response:
                    viki_logger.info("SelfCritique: refined response for intent '%s'", intent)
                    viki_resp.final_response = improved

            if not viki_resp.final_response or viki_resp.final_response.strip() == "":
                viki_resp.final_thought.primary_strategy = (
                    viki_resp.final_thought.primary_strategy or "I processed your request."
                )
                viki_resp.final_response = viki_resp.final_thought.primary_strategy

            return cast("VIKIResponse", viki_resp)
        except Exception as e:
            viki_logger.error(f"Deliberation Model Failure: {e}")
            if "llm_start" in locals():
                llm_latency = time.time() - llm_start
                model.record_performance(llm_latency, success=False)
            return VIKIResponse(
                final_thought=ThoughtObject(
                    intent_summary="Error recovery", primary_strategy="Fallback", confidence=0.0
                ),
                final_response=f"My deliberation layer encountered a model error: {e}",
            )

    def _judge(self, results: Any) -> VIKIResponse:
        return cast("VIKIResponse", results)

    async def _streamed_conversational_reply(
        self,
        model,
        context: dict[str, Any],
        on_event,
    ) -> VIKIResponse | None:
        try:
            soul_prompt = self.soul_config.get(
                "system_prompt",
                "You are VIKI, a helpful and friendly AI assistant.",
            )
            raw_input = context.get("raw_input", "") or ""
            history = context.get("conversation_history", []) or []
            messages: list[dict[str, str]] = [{"role": "system", "content": soul_prompt}]
            _owner = self.soul_config.get("owner", {})
            _ctx = _owner.get("custom_context", "") if isinstance(_owner, dict) else ""
            _name = _owner.get("name", "") if isinstance(_owner, dict) else ""
            if _ctx and not any(m.get("role") == "assistant" for m in history):
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"*I fully embrace my role as instructed.* I am VIKI, and I will honor the behavioral mandate completely for {_name}.",
                    }
                )
            for msg in history[-6:]:
                if msg.get("role") in ("user", "assistant") and msg.get("content"):
                    if msg.get("role") == "user" and msg.get("content") == raw_input:
                        continue
                    messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": raw_input})

            chunks: list[str] = []
            llm_start = time.time()
            try:
                if on_event:
                    try:
                        on_event("status", "STREAMING")
                    except Exception:
                        pass
                async for chunk in model.chat_stream(messages, temperature=0.6):
                    if not chunk:
                        continue
                    if isinstance(chunk, str) and chunk.startswith("Error"):
                        viki_logger.warning(f"Streaming reported error: {chunk}")
                        return None
                    chunks.append(chunk)
                    try:
                        on_event("partial", chunk)
                    except Exception as e:
                        viki_logger.debug(f"on_event partial dispatch failed: {e}")
            except Exception as e:
                viki_logger.warning(f"Streaming fast-path errored: {e}")
                return None

            text = "".join(chunks).strip()
            llm_latency = time.time() - llm_start
            try:
                model.record_performance(llm_latency, success=bool(text))
            except Exception:
                pass

            if not text:
                return None

            lite = VIKIResponseLite(final_response=text, action=None, confidence=0.7)
            resp = lite.to_full_response()
            resp.intent_type = context.get("intent_type")
            resp.sentiment = context.get("sentiment")
            return resp
        except Exception as e:
            viki_logger.warning(f"_streamed_conversational_reply failed: {e}")
            return None
