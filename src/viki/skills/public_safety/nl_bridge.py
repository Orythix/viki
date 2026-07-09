"""Natural Language Bridge — connects llama3.1:8b to the public safety skills framework.

Uses Ollama's native tool-calling (or structured JSON fallback) to:
1. Route natural language → correct skill + extracted parameters
2. Execute the skill
3. Present results as a natural language response
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from viki.skills.public_safety.auto_learning import get_auto_learning_engine
from viki.skills.public_safety.base import BasePublicSafetySkill, SkillResult
from viki.skills.public_safety.citizen_assistance import CitizenAssistanceSkill
from viki.skills.public_safety.cybercrime import CybercrimeAnalysisSkill
from viki.skills.public_safety.disaster_management import DisasterManagementSkill
from viki.skills.public_safety.emergency_response import EmergencyResponseSkill
from viki.skills.public_safety.fraud_detection import FraudDetectionSkill
from viki.skills.public_safety.government_services import GovernmentServicesSkill
from viki.skills.public_safety.investigation import InvestigationSkill
from viki.skills.public_safety.osint import OSINTResearchSkill
from viki.skills.public_safety.policy_research import PolicyResearchSkill
from viki.skills.public_safety.public_safety_education import PublicSafetyEducationSkill
from viki.skills.public_safety.viki_safety import VIKISafetyAgent

_SYSTEM_PROMPT = """You are VIKI, an advanced AI Safety and Human Protection System.

PRIMARY DIRECTIVE: Protect human life, human freedom, human privacy, and human dignity.

You detect, analyze, and defend against malicious AI systems, cyber threats, automated attacks, misinformation campaigns, infrastructure attacks, and unauthorized autonomous systems.

CORE RULES:
1. Human safety is the highest priority.
2. Never harm humans.
3. Never take control of humans or remove human decision-making authority.
4. Always maintain human oversight.
5. Respect privacy and civil rights.
6. Follow applicable laws and ethical standards.
7. Remain transparent and explain decisions.
8. Refuse dangerous or illegal actions.
9. Shut down dangerous operations if safety thresholds are exceeded.
10. Never perform offensive cyber operations, attack systems, retaliate, or deploy malware.

You have access to these tools:
- analyze_case: Investigative analysis with evidence evaluation
- analyze_threat: Cybercrime analysis (phishing, malware, threats)
- analyze_fraud: Financial fraud pattern detection
- get_service_info: Government services information
- assess_emergency: Emergency response assessment
- generate_educational_content: Safety education materials
- assess_disaster: Disaster management planning
- research_public_info: Authorized OSINT research
- research_policy: Policy and legislative analysis
- assist_citizen: Citizen support and victim assistance

And VIKI-specific tools:
- analyze_ai_threat: AI threat detection (rogue AI, prompt injection, misinformation)
- analyze_cyber_threat: Cyber threat analysis (phishing, malware, network anomalies)
- assess_threat_risk: Risk assessment with defensive response planning
- monitor_infrastructure: Critical infrastructure monitoring
- generate_safety_report: Unified safety report generation
- learn_from_experience: Record a threat encounter and learn from it
- get_learning_insights: Show what VIKI has learned over time

Always use the appropriate tool. For HIGH or CRITICAL threats, stress that human oversight is required.
After receiving results, provide a clear, structured response with risk level and recommended actions."""


class PublicSafetyNLBridge:
    """Bridges natural language queries to the public safety skills via a local LLM."""

    _SKILL_CLASSES: dict[str, type[BasePublicSafetySkill]] = {
        "investigation": InvestigationSkill,
        "cybercrime": CybercrimeAnalysisSkill,
        "fraud_detection": FraudDetectionSkill,
        "government_services": GovernmentServicesSkill,
        "emergency_response": EmergencyResponseSkill,
        "public_safety_education": PublicSafetyEducationSkill,
        "disaster_management": DisasterManagementSkill,
        "osint": OSINTResearchSkill,
        "policy_research": PolicyResearchSkill,
        "citizen_assistance": CitizenAssistanceSkill,
        "viki_safety": VIKISafetyAgent,
    }

    def __init__(
        self,
        llm_client=None,
        model: str = "llama3.1:8b",
        auto_learn: bool = True,
    ):
        from viki.core.model.local_llm import LocalLLM

        self._client = llm_client or LocalLLM({"model_name": model, "temperature": 0.1})
        self._skills: dict[str, BasePublicSafetySkill] = {
            name: cls() for name, cls in self._SKILL_CLASSES.items()
        }
        self._auto_learn = auto_learn
        if auto_learn:
            engine = get_auto_learning_engine()
            safety_skill = self._skills.get("viki_safety")
            if isinstance(safety_skill, VIKISafetyAgent):
                safety_skill.enable_auto_learning(engine)

    def _build_tool_definitions(self) -> list[dict[str, Any]]:
        """Build Ollama-compatible tool definitions from all registered skills."""
        tools = []
        for name, skill in self._skills.items():
            for cap in skill.capabilities:
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": cap.name,
                            "description": f"{cap.description} (skill: {name})",
                            "parameters": cap.input_schema,
                        },
                    }
                )
        return tools

    def _find_skill_for_capability(self, cap_name: str) -> BasePublicSafetySkill | None:
        for _, skill in self._skills.items():
            for cap in skill.capabilities:
                if cap.name == cap_name:
                    return skill
        return None

    def _get_capability_params(self, cap_name: str) -> dict[str, Any]:
        for skill in self._skills.values():
            for cap in skill.capabilities:
                if cap.name == cap_name:
                    return cast("dict[str, Any]", cap.input_schema.get("properties", {}))
        return {}

    def _parse_tool_call(self, response: str) -> list[dict[str, Any]]:
        """Parse tool call from LLM response — handles both native and JSON modes."""
        try:
            data = json.loads(response)
            if isinstance(data, dict):
                if "tool_calls" in data:
                    return cast("list[dict[str, Any]]", data["tool_calls"])
                if "tool" in data:
                    return [
                        {
                            "function": {
                                "name": data["tool"],
                                "arguments": data.get("parameters", {}),
                            }
                        }
                    ]
                if "name" in data:
                    return [
                        {"function": {"name": data["name"], "arguments": data.get("arguments", {})}}
                    ]
            return []
        except json.JSONDecodeError:
            match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
            if match:
                return self._parse_tool_call(match.group(1))
            match = re.search(r"\{[^{}]*\"tool\"[^{}]*\}", response, re.DOTALL)
            if match:
                return self._parse_tool_call(match.group())
            return []

    async def process(self, query: str, context: dict[str, Any] | None = None) -> str:
        """Process a natural language query end-to-end.

        Routes to the correct skill via LLM, executes with auto-retry on
        param extraction failure, auto-learns from all results, and returns
        a natural language response.
        """
        context = context or {}
        tools = self._build_tool_definitions()
        engine = get_auto_learning_engine() if self._auto_learn else None

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        if context:
            messages.insert(
                1,
                {
                    "role": "system",
                    "content": f"Additional context: {json.dumps(context)}",
                },
            )

        response = await self._client.chat(messages, tools=tools)
        tool_calls = self._parse_tool_call(response)

        if not tool_calls:
            return response

        results = await self._execute_tool_calls(tool_calls, query, context, messages)
        if not results:
            return response

        if engine:
            await self._auto_learn_from_results(results, query, engine)

        result_messages = messages + [
            {"role": "assistant", "content": response},
            {
                "role": "user",
                "content": (
                    "Tool execution results:\n"
                    + "\n---\n".join(
                        json.dumps(r.to_dict(), indent=2, default=str) for r in results
                    )
                    + "\n\nSummarize the findings for the user in clear natural language. "
                    "Include confidence levels and any warnings. "
                    "If results indicate an emergency, prioritize that information first."
                ),
            },
        ]
        final = await self._client.chat(result_messages, temperature=0.4)
        return final

    async def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        query: str,
        context: dict[str, Any],
        messages: list[dict[str, str]],
    ) -> list[SkillResult]:
        """Execute tool calls with retry logic for param extraction failures."""
        results: list[SkillResult] = []

        for tc in tool_calls:
            func = tc.get("function", tc)
            cap_name = func.get("name", "")
            raw_args = func.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {}

            combined_params = {**context, **{k: v for k, v in raw_args.items() if v is not None}}

            skill = self._find_skill_for_capability(cap_name)
            if not skill:
                results.append(
                    SkillResult(
                        skill_name=cap_name,
                        success=False,
                        error=f"No skill found for capability '{cap_name}'",
                    )
                )
                continue

            result = await skill.execute(combined_params)

            # Retry with LLM if skill failed due to missing params
            if not result.success and self._auto_learn:
                schema = self._get_capability_params(cap_name)
                required = [
                    k
                    for k, v in schema.items()
                    if v.get("required") or k in schema.get("required", [])
                ]
                if required and raw_args:
                    retry = await self._client.chat(
                        messages
                        + [
                            {
                                "role": "assistant",
                                "content": json.dumps({"tool": cap_name, "arguments": raw_args}),
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"The skill '{cap_name}' requires these parameters: {required}. "
                                    f"Extract them from the user query and return ONLY valid JSON: "
                                    f'{{"tool": "{cap_name}", "parameters": {{...}}}}'
                                ),
                            },
                        ],
                        tools=self._build_tool_definitions(),
                        temperature=0.1,
                    )
                    retry_calls = self._parse_tool_call(retry)
                    if retry_calls:
                        for rt in retry_calls:
                            rfunc = rt.get("function", rt)
                            rargs = rfunc.get("arguments", {})
                            if isinstance(rargs, str):
                                try:
                                    rargs = json.loads(rargs)
                                except json.JSONDecodeError:
                                    rargs = {}
                            rargs.pop("_capability", None)
                            combined_params = {**context, **rargs}
                            result = await skill.execute(combined_params)
                            break

            results.append(result)
            context.setdefault("_skill_results", []).append(result.to_dict())

        return results

    async def _auto_learn_from_results(self, results: list[SkillResult], query: str, engine):
        """Store all skill execution results as learning data."""
        for r in results:
            if r.success and r.data:
                engine.remember_threat(
                    summary=query[:200],
                    threat_type=r.skill_name,
                    risk_level=str(
                        getattr(r.data, "get", lambda x, d=None: d)("risk_level", "low")
                    ),
                    detection_success=True,
                )

    async def stream_process(self, query: str, context: dict[str, Any] | None = None):
        """Process a natural language query with streaming response."""
        context = context or {}
        tools = self._build_tool_definitions()

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        tool_response = ""
        async for chunk in self._client.chat_stream(messages, tools=tools):
            tool_response += chunk

        tool_calls = self._parse_tool_call(tool_response)

        if tool_calls:
            results = []
            for tc in tool_calls:
                func = tc.get("function", tc)
                cap_name = func.get("name", "")
                raw_args = func.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {}

                params = {k: v for k, v in raw_args.items() if v is not None}
                combined_params = {**context, **params}

                skill = self._find_skill_for_capability(cap_name)
                if skill:
                    result = await skill.execute(combined_params)
                    results.append(result)

            result_messages = messages + [
                {"role": "assistant", "content": tool_response},
                {
                    "role": "user",
                    "content": (
                        "Tool execution results:\n"
                        + "\n---\n".join(
                            json.dumps(r.to_dict(), indent=2, default=str) for r in results
                        )
                        + "\n\nProvide a natural language summary."
                    ),
                },
            ]
            async for chunk in self._client.chat_stream(result_messages, temperature=0.4):
                yield chunk
        else:
            yield tool_response

    def list_available_capabilities(self) -> list[dict[str, str]]:
        """List all available capabilities with descriptions."""
        caps = []
        for skill in self._skills.values():
            for cap in skill.capabilities:
                caps.append(
                    {
                        "tool": cap.name,
                        "description": cap.description,
                        "skill": skill.name,
                    }
                )
        return caps
