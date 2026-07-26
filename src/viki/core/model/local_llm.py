"""LM Studio provider — OpenAI-compatible local inference."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
from typing import Any, cast

import aiohttp

from viki.config.logger import viki_logger
from viki.core.schema import ThoughtObject, VIKIResponse, VIKIResponseLite

from .llm_provider import LLMProvider

T = Any


class LocalLLM(LLMProvider):
    """LM Studio provider using OpenAI-compatible /v1/chat/completions."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        env_url = (os.environ.get("VIKI_LMSTUDIO_URL") or "").strip().rstrip("/")
        self.base_url = env_url or self.config.get("base_url", "http://127.0.0.1:1234").rstrip("/")
        if "localhost" in self.base_url:
            self.base_url = self.base_url.replace("localhost", "127.0.0.1")
        # LM Studio doesn't use keep_alive or Ollama-specific options
        self._session: aiohttp.ClientSession | None = None
        if not _lmstudio_model_available(self.base_url, self.model_name):
            self.available = False
            self.unavailable_reason = (
                f"LM Studio model '{self.model_name}' not found at {self.base_url}. "
                "Load a model in LM Studio and ensure it is running."
            )
            viki_logger.warning(
                "Model '%s' (provider: lmstudio) disabled: %s",
                self.model_name,
                self.unavailable_reason,
            )

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300))
        return self._session

    def is_cloud(self) -> bool:
        try:
            host = (self.base_url or "").lower()
            return not (
                "127.0.0.1" in host
                or "localhost" in host
                or "0.0.0.0" in host
                or host.startswith("http://host.docker.internal")
            )
        except Exception:
            return False

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ):
        data: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        if tools:
            data["tools"] = tools
        try:
            async with self._get_session().post(
                f"{self.base_url}/v1/chat/completions", json=data
            ) as resp:
                if resp.status == 404:
                    yield f"Error: Model '{self.model_name}' not found."
                    return
                if resp.status != 200:
                    body = await resp.text()
                    yield f"Error: LM Studio returned {resp.status}: {body[:200]}"
                    return
                async for raw in resp.content:
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    payload_str = line[len("data: ") :]
                    if payload_str.strip() == "[DONE]":
                        return
                    try:
                        payload = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    delta = payload.get("choices", [{}])[0].get("delta", {})
                    chunk = delta.get("content") or ""
                    if chunk:
                        yield chunk
        except Exception as e:
            yield f"Error calling LM Studio: {e}"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        format: str | dict[str, Any] | None = None,
        image_path: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict | None = None,
    ) -> str:
        t0 = time.perf_counter()
        success = False
        try:
            data: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "stream": False,
                "temperature": temperature,
            }
            if format:
                if isinstance(format, str):
                    data["response_format"] = {"type": "text"}
                elif isinstance(format, dict):
                    data["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": "response", "schema": format},
                    }
            if response_format:
                data["response_format"] = response_format
            if tools:
                data["tools"] = tools
            if image_path:

                def read_image():
                    with open(image_path, "rb") as image_file:
                        return base64.b64encode(image_file.read()).decode("utf-8")

                base64_image = await asyncio.to_thread(read_image)
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i]["role"] == "user":
                        original_text = messages[i].get("content", "")
                        if isinstance(original_text, str):
                            messages[i]["content"] = [
                                {"type": "text", "text": original_text},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                                },
                            ]
                        break

            try:
                async with self._get_session().post(
                    f"{self.base_url}/v1/chat/completions", json=data
                ) as resp:
                    if resp.status == 404:
                        return f"Error: Model '{self.model_name}' not found."
                    if resp.status != 200:
                        body = await resp.text()
                        return f"LM Studio Error ({resp.status}): {body[:300]}"
                    resp_json = await resp.json()
                    if "error" in resp_json:
                        return f"LM Studio Error: {resp_json['error']}"
                    choices = resp_json.get("choices", [])
                    if not choices:
                        return "Error: No choices in LM Studio response."
                    message = choices[0].get("message", {})
                    usage = resp_json.get("usage", {})
                    if usage:
                        self.record_token_usage(
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                        )
                    if message.get("tool_calls"):
                        success = True
                        return json.dumps({"tool_calls": message["tool_calls"]})
                    success = True
                    return message.get("content") or ""
            except Exception as e:
                return f"Error calling LM Studio: {str(e)}"
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat")
            except Exception:
                viki_logger.warning("failed to emit LLM inference usage for %s", self.model_name)

    async def chat_with_tools(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], temperature: float = 0.0
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        success = False
        data: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "tools": tools,
        }
        try:
            async with self._get_session().post(
                f"{self.base_url}/v1/chat/completions", json=data
            ) as resp:
                if resp.status == 404:
                    raise ValueError(f"Model '{self.model_name}' not found.")
                if resp.status != 200:
                    body = await resp.text()
                    raise ValueError(f"LM Studio Error ({resp.status}): {body[:300]}")
                try:
                    resp_json = await resp.json()
                except (aiohttp.ContentTypeError, json.JSONDecodeError) as e:
                    viki_logger.error(f"Failed to parse LM Studio response: {e}")
                    raise ValueError(f"Invalid JSON from LM Studio: {resp.status}") from e
                if "error" in resp_json:
                    raise ValueError(f"LM Studio Error: {resp_json['error']}")
                choices = resp_json.get("choices", [])
                if not choices:
                    raise ValueError(f"No choices in response: {resp_json}")
                usage = resp_json.get("usage", {})
                if usage:
                    self.record_token_usage(
                        usage.get("prompt_tokens", 0),
                        usage.get("completion_tokens", 0),
                    )
                success = True
                message: dict[str, Any] = choices[0].get("message", {})
                return message
        except Exception as e:
            viki_logger.error(f"Tool call failed: {e}")
            return {"role": "assistant", "content": f"LM Studio Error: {str(e)}"}
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat_with_tools")
            except Exception:
                viki_logger.warning("failed to emit LLM inference usage for %s", self.model_name)

    def _compact_json_output_guide(self, response_model: type[T]) -> str:
        if response_model == VIKIResponse:
            return (
                "### JSON OUTPUT (required) ###\n"
                "Return one JSON object only. Use keys: final_thought (object), final_response (string), "
                "and action (optional object with skill_name and parameters).\n"
                'Do NOT return a JSON Schema. Example: {"final_thought":{"intent_summary":"...","primary_strategy":"...","confidence":0.8},'
                '"final_response":"...","action":{"skill_name":"...","parameters":{}}}'
            )
        if response_model == VIKIResponseLite:
            return (
                "### JSON OUTPUT (required) ###\n"
                'Return one JSON object: {"final_response":"your answer","confidence":0.85,"action":null}\n'
                "Include action only when a tool call is needed."
            )
        try:
            sch = response_model.model_json_schema()
            keys = list((sch.get("properties") or {}).keys())
            if keys:
                return (
                    "### JSON OUTPUT ###\n"
                    f"Return one JSON object with these keys only: {', '.join(keys)}. "
                    "Populate values; do not output JSON Schema metadata."
                )
        except Exception as e:
            viki_logger.debug("compact guide fallback: %s", e)
        return "### JSON OUTPUT ###\nReturn one valid JSON object for the task."

    @staticmethod
    def _data_is_json_schema_echo(data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        if data.get("type") != "object":
            return False
        return "properties" in data and "required" in data

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str | None = None,
    ) -> T:
        msgs: list[dict[str, Any]] = [dict(m) for m in messages]
        if image_path:

            def read_image():
                with open(image_path, "rb") as image_file:
                    return base64.b64encode(image_file.read()).decode("utf-8")

            base64_image = await asyncio.to_thread(read_image)
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i]["role"] == "user":
                    msgs[i]["content"] = [
                        {"type": "text", "text": msgs[i].get("content", "")},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ]
                    break

        guide = self._compact_json_output_guide(response_model)
        msgs.append({"role": "system", "content": guide})
        json_schema = response_model.model_json_schema()
        content = await self.chat(
            msgs,
            temperature=temperature,
            response_format={"type": "json_schema", "json_schema": json_schema},
            image_path=image_path,
        )
        content = (content if isinstance(content, str) else str(content or "")).strip()
        if content.startswith(("LM Studio Error", "Error")):
            content = await self.chat(
                msgs,
                temperature=temperature,
                response_format={"type": "text"},
                image_path=image_path,
            )
            content = (content if isinstance(content, str) else str(content or "")).strip()

        try:
            data = self._parse_structured_json_heuristics(content)
            if response_model == VIKIResponse and self._data_is_json_schema_echo(data):
                plain_msgs = [dict(m) for m in msgs[:-1]]
                plain_msgs.append(
                    {
                        "role": "system",
                        "content": "Reply in plain language only. Answer the user's last message helpfully. No JSON, no code fences, no preamble.",
                    }
                )
                content = await self.chat(
                    plain_msgs,
                    temperature=min(0.55, max(0.15, temperature)),
                    image_path=image_path,
                )
                content = (content if isinstance(content, str) else str(content or "")).strip()
                if content.startswith(("{", "[")):
                    data = self._parse_structured_json_heuristics(content)
                else:
                    return VIKIResponse(
                        final_thought=ThoughtObject(
                            intent_summary="Direct reply",
                            primary_strategy="Plain-language recovery after invalid JSON",
                            confidence=0.65,
                        ),
                        final_response=content[:8000] if len(content) > 8000 else content,
                    )
                if response_model == VIKIResponse and self._data_is_json_schema_echo(data):
                    return self._structured_fallback(
                        response_model, content, ValueError("schema echo persisted")
                    )

            if response_model == VIKIResponse:
                data = self._patch_viki_response(data)
            return response_model.model_validate_json(json.dumps(data))
        except Exception as e:
            viki_logger.warning("Structured parse failed for %s: %s", response_model.__name__, e)
            max_retries = 2
            retry_count = 0
            while retry_count < max_retries:
                retry_count += 1
                guide_text = self._compact_json_output_guide(response_model)
                retry_msgs = [dict(m) for m in msgs[:-1]]
                retry_msgs.append(
                    {
                        "role": "system",
                        "content": "Your previous response was not valid JSON. Return ONLY a single valid JSON object.\n"
                        + guide_text,
                    }
                )
                content2 = await self.chat(
                    retry_msgs,
                    temperature=min(0.5, temperature + 0.1 * retry_count),
                    response_format={"type": "json_schema", "json_schema": json_schema},
                    image_path=image_path,
                )
                content2 = (content2 if isinstance(content2, str) else str(content2 or "")).strip()
                try:
                    data2 = self._parse_structured_json_heuristics(content2)
                    if response_model == VIKIResponse and self._data_is_json_schema_echo(data2):
                        content = content2
                        continue
                    if response_model == VIKIResponse:
                        data2 = self._patch_viki_response(data2)
                    return response_model.model_validate_json(json.dumps(data2))
                except Exception:
                    content = content2
                    continue
            return self._structured_fallback(response_model, content, e)

    def _parse_structured_json_heuristics(self, content: str) -> dict:
        match = re.search(r"```(?:json)?\s*({.*})\s*```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()
        else:
            content = content.replace("```json", "").replace("```", "").strip()
        content = (
            content.replace(": None", ": null")
            .replace(": True", ": true")
            .replace(": False", ": false")
        )
        try:
            return cast("dict[Any, Any]", json.loads(content))
        except json.JSONDecodeError:
            try:
                import ast

                val = ast.literal_eval(content)
                if isinstance(val, dict):
                    return val
            except Exception:
                viki_logger.warning("ast fallback parse failed for local_llm")
            if "'" in content and '"' not in content[:10]:
                try:
                    return cast("dict[Any, Any]", json.loads(content.replace("'", '"')))
                except Exception:
                    viki_logger.warning("quote-replacement parse fallback failed for local_llm")
            raise

    def _structured_fallback(self, response_model: type[T], content: str, err: Exception) -> T:
        fallback_text = self._extract_text(content)
        if response_model == VIKIResponseLite:
            return VIKIResponseLite(final_response=fallback_text, confidence=0.4)
        if response_model == VIKIResponse:
            return VIKIResponse(
                final_thought=ThoughtObject(
                    intent_summary="Response recovery",
                    primary_strategy="Deliver available response despite format mismatch",
                    confidence=0.5,
                ),
                final_response=fallback_text,
            )
        raise ValueError(f"Failed to parse structured output: {err}\nContent: {content}")

    def _extract_text(self, content: str) -> str:
        fallback = "I encountered a parsing issue. Could you rephrase that?"
        if content is None:
            return fallback
        s = content.strip() if isinstance(content, str) else str(content or "").strip()
        if not s:
            return fallback
        raw = self._try_parse_json_object(content)
        if isinstance(raw, dict):
            extracted = self._first_non_empty_string(
                raw, ["final_response", "response", "message", "text", "content", "answer"]
            )
            if extracted:
                return extracted
        if s.startswith(("{", "[")):
            return fallback
        if self._looks_like_connection_error(s):
            return "I couldn't reach LM Studio. Make sure LM Studio is running and a model is loaded, then try again."
        return s[:2000] if len(s) > 2000 else s

    def _try_parse_json_object(self, content: Any) -> Any:
        if not isinstance(content, str):
            return None
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _first_non_empty_string(obj: dict[str, Any], keys: list[str]) -> str | None:
        for key in keys:
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return None

    @staticmethod
    def _looks_like_connection_error(text: str) -> bool:
        return (
            text.startswith("Error calling LM Studio")
            or "Cannot connect to host" in text
            or "127.0.0.1:1234" in text
        )

    def _patch_viki_response(self, data: dict) -> dict:
        patched = self._patch_response_plan(data)
        if patched is not None:
            return patched
        self._patch_thought_object_root(data)
        self._patch_flattened_thought_object(data)
        self._patch_action_fields(data)
        self._patch_flattened_action(data)
        self._patch_missing_final_thought(data)
        return data

    def _patch_response_plan(self, data: dict) -> dict | None:
        if "response" in data and "plan" in data and "final_thought" not in data:
            response_obj = data["response"]
            intent = (
                response_obj.get("intent", "unknown")
                if isinstance(response_obj, dict)
                else str(response_obj)
            )
            plan = str(data.get("plan", []))
            return {
                "final_thought": {
                    "intent_summary": intent,
                    "primary_strategy": plan,
                    "confidence": 0.8,
                },
                "action": data.get("action"),
                "final_response": data.get("final_response", f"Plan: {plan}"),
            }
        return None

    def _patch_thought_object_root(self, data: dict) -> None:
        if "ThoughtObject" in data and "final_thought" not in data:
            data["final_thought"] = data.pop("ThoughtObject")

    def _patch_flattened_thought_object(self, data: dict) -> None:
        if "intent_summary" in data and "primary_strategy" in data and "final_thought" not in data:
            thought_fields = [
                "intent_vector",
                "intent_summary",
                "assumptions",
                "constraints",
                "risk_score",
                "primary_strategy",
                "rejected_strategies",
                "symbolic_graph",
                "confidence",
                "provenance",
            ]
            thought_obj: dict[str, Any] = {}
            for f in thought_fields:
                if f in data:
                    thought_obj[f] = data.pop(f)
            data["final_thought"] = thought_obj

    def _patch_action_fields(self, data: dict) -> None:
        if "action" in data and isinstance(data["action"], str):
            data["action"] = {"skill_name": data["action"], "parameters": {}}
            return
        if "action" in data and isinstance(data["action"], dict):
            if "parameters" not in data["action"]:
                data["action"]["parameters"] = {}

    def _patch_flattened_action(self, data: dict) -> None:
        if "skill_name" in data and "parameters" in data and "action" not in data:
            data["action"] = {
                "skill_name": data.pop("skill_name"),
                "parameters": data.pop("parameters"),
            }

    def _patch_missing_final_thought(self, data: dict) -> None:
        if "final_thought" not in data:
            summary = data.get("final_response", "Request received, formulating response...")
            strategy = data.get("internal_metacognition", summary)
            data["final_thought"] = {
                "intent_summary": summary[:200] if isinstance(summary, str) else "User request",
                "primary_strategy": strategy[:200]
                if isinstance(strategy, str)
                else "Direct response",
                "confidence": 0.7,
            }


def _lmstudio_model_available(base_url: str, model_name: str) -> bool:
    """Check if a model is loaded in LM Studio via /v1/models."""
    try:
        import urllib.request

        req = urllib.request.Request(
            f"{base_url}/v1/models",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("data", []):
            if m.get("id") == model_name:
                return True
    except Exception:
        viki_logger.warning("lmstudio_model_exists check failed")
    return False
