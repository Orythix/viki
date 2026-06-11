import asyncio
import json
import os
import re
import time
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import aiohttp
import yaml
from pydantic import BaseModel

from viki.config.logger import viki_logger
from viki.core.schema import ThoughtObject, VIKIResponse, VIKIResponseLite


def _debug_enabled() -> bool:
    return os.environ.get("VIKI_DEBUG", "").lower() in ("true", "1", "yes")


T = TypeVar("T", bound=BaseModel)


def _resolve_ollama_thinking_from_settings(system_settings: dict[str, Any] | None) -> bool:
    """Env VIKI_OLLAMA_THINK overrides settings.system.ollama_enable_thinking."""
    env = (os.environ.get("VIKI_OLLAMA_THINK") or "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    sys = (system_settings or {}).get("system") or {}
    return bool(sys.get("ollama_enable_thinking", False))


def _resolve_ollama_options_from_settings(system_settings: dict[str, Any] | None) -> dict[str, Any]:
    sys = (system_settings or {}).get("system") or {}
    opts = sys.get("ollama_options")
    return dict(opts) if isinstance(opts, dict) else {}


def _effective_profile_for_factory(
    profile: dict[str, Any],
    provider_conf: dict[str, Any],
    system_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge Ollama tuning from settings (and optional per-profile overrides) into the profile dict."""
    if provider_conf.get("type") != "local":
        return profile
    merged = dict(profile)
    thinking = _resolve_ollama_thinking_from_settings(system_settings)
    if profile.get("ollama_enable_thinking") is not None:
        thinking = bool(profile["ollama_enable_thinking"])
    merged["ollama_enable_thinking"] = thinking
    base_opts = _resolve_ollama_options_from_settings(system_settings)
    po = profile.get("ollama_options")
    if isinstance(po, dict):
        merged["ollama_options"] = {**base_opts, **po}
    elif base_opts:
        merged["ollama_options"] = dict(base_opts)
    return merged


class StructuredPrompt:
    def __init__(self, request: str, messages: list[dict[str, str]] = None):
        self.request = request
        self.messages = messages or []
        self.identity = ""
        self.cognitive_instructions = ""
        self.context = ""

    def set_identity(self, identity: str):
        self.identity = identity

    def add_cognitive(self, instruction: str):
        self.cognitive_instructions += f"\n- {instruction}"

    def add_context(self, context: str):
        self.context = context

    def build(self) -> list[dict[str, str]]:
        system_content = f"{self.identity}\n\nCOGNITIVE PROTOCOLS:{self.cognitive_instructions}\n\nCONTEXT:\n{self.context}"

        final_messages = [{"role": "system", "content": system_content}]
        final_messages.extend(self.messages)

        # Always add the current request as the last user message
        final_messages.append({"role": "user", "content": self.request})

        return final_messages


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.model_name = config.get("model_name", "unknown")
        # v11 Model Governance (HR)
        self.trust_score = 1.0  # 0.0 to 1.0
        self.strengths = config.get("strengths", [])
        self.weaknesses = config.get("weaknesses", [])
        self.error_count = 0
        self.avg_latency = 0.0
        self.call_count = 0
        self.available = True
        self.unavailable_reason = None
        # Phase 1: cost & token accounting.
        self.cost_per_1k_in: float = float(config.get("cost_per_1k_in", 0.0))
        self.cost_per_1k_out: float = float(config.get("cost_per_1k_out", 0.0))
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.provider_name: str = config.get("provider", config.get("provider_type", "unknown"))

    def is_cloud(self) -> bool:
        """True for any provider that egresses outside the local machine."""
        # Default conservative: cloud unless overridden by LocalLLM/FallbackLLM subclasses.
        return True

    def record_performance(self, latency: float, success: bool):
        self.call_count += 1
        n = self.call_count
        self.avg_latency = ((self.avg_latency * (n - 1)) + latency) / n

        if not success:
            self.error_count += 1
            self.trust_score = max(0.0, self.trust_score - 0.1)
        else:
            self.trust_score = min(1.0, self.trust_score + 0.01)

        try:
            from viki.core.usage_log import emit_model_feedback

            emit_model_feedback(self, latency, success)
        except Exception:
            pass

    def estimate_cost_usd(self, prompt_tokens: int, completion_tokens: int = 256) -> float:
        """
        Rough cost estimator using the provider's per-1k pricing config.
        Returns 0.0 for local models (no `cost_per_1k_*` set).
        """
        return (prompt_tokens / 1000.0) * self.cost_per_1k_in + (
            completion_tokens / 1000.0
        ) * self.cost_per_1k_out

    def record_token_usage(self, input_tokens: int, output_tokens: int) -> float:
        """Update token counters and return the delta cost for this call."""
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        delta = (input_tokens / 1000.0) * self.cost_per_1k_in + (
            output_tokens / 1000.0
        ) * self.cost_per_1k_out
        self.total_cost_usd += delta

        try:
            from api.events import get_event_bus

            get_event_bus().publish(
                "usage",
                {"input": input_tokens, "output": output_tokens, "model": self.model_name},
                channel="system",
            )
        except Exception:
            pass

        return delta

    @abstractmethod
    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        """Send a asynchronous chat request to the LLM."""

    @abstractmethod
    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str = None,
    ) -> T:
        """Send a structured chat request returning a Pydantic model with optional visual context."""

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        """
        Default streaming implementation: yields the full response as a single chunk.
        Concrete providers should override with native streaming where supported.
        """
        result = await self.chat(messages, temperature=temperature)
        if result:
            yield result


class FallbackLLM(LLMProvider):
    """Fallback LLM used when no configured model is available (dev/edge case)."""

    def is_cloud(self) -> bool:
        return False

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        t0 = time.perf_counter()
        success = False
        try:
            await asyncio.sleep(0.1)
            success = True
            return f"Fallback response for {self.model_name}"
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat")
            except Exception:
                pass

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str = None,
    ) -> T:
        t0 = time.perf_counter()
        success = False
        try:
            await asyncio.sleep(0.1)
            success = True
            return response_model()
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat_structured")
            except Exception:
                pass


def _looks_like_openai_secret(key: str | None) -> bool:
    """True only for keys that can authenticate api.openai.com (not placeholders like 'ollama')."""
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    lowered = s.lower()
    if lowered in (
        "ollama",
        "none",
        "dummy",
        "placeholder",
        "test",
        "your-api-key-here",
        "changeme",
    ):
        return False
    return s.startswith("sk-")  # includes sk-proj-


def _looks_like_anthropic_secret(key: str | None) -> bool:
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    lowered = s.lower()
    if lowered in (
        "ollama",
        "none",
        "dummy",
        "placeholder",
        "test",
        "your-api-key-here",
        "changeme",
    ):
        return False
    return s.startswith("sk-ant-")


class APILLM(LLMProvider):
    """OpenAI-compatible API provider with Instructor support."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

        self.provider_type = config.get("provider", "openai")
        api_key = os.getenv(self.config.get("api_key_env", "OPENAI_API_KEY"))

        try:
            import instructor

            if self.provider_type == "anthropic":
                from anthropic import AsyncAnthropic

                if not _looks_like_anthropic_secret(api_key):
                    raise ValueError(
                        f"Anthropic API key missing or invalid ({self.config.get('api_key_env', 'ANTHROPIC_API_KEY')}). "
                        "Expected a key starting with sk-ant-. Remove placeholder values or use local Ollama profiles."
                    )
                self.client = instructor.from_anthropic(
                    AsyncAnthropic(api_key=api_key), mode=instructor.Mode.ANTHROPIC_JSON
                )
            else:
                from openai import AsyncOpenAI

                base_url = self.config.get("base_url", "https://api.openai.com/v1")
                uses_official_openai = "api.openai.com" in (base_url or "")
                if uses_official_openai and not _looks_like_openai_secret(api_key):
                    raise ValueError(
                        f"OpenAI API key missing or invalid ({self.config.get('api_key_env', 'OPENAI_API_KEY')}). "
                        "Official OpenAI expects a secret starting with sk-. "
                        "Unset OPENAI_API_KEY or set system.local_llm_only: true to use Ollama only."
                    )
                if not api_key and not uses_official_openai:
                    api_key = "not-needed"  # OpenAI-compatible local servers (LM Studio, vLLM) often accept any string

                self.client = instructor.from_openai(
                    AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url),
                    mode=instructor.Mode.JSON,
                )
        except ImportError as e:
            viki_logger.warning(
                f"Model '{self.model_name}' (provider: {self.provider_type}) disabled: optional API dependency missing or broken: {e}"
            )
            self.client = None
            self.available = False
            self.unavailable_reason = f"optional dependency missing or broken: {e}"
        except Exception as e:
            viki_logger.warning(
                f"Model '{self.model_name}' (provider: {self.provider_type}) disabled: {e}"
            )
            self.client = None
            self.available = False
            self.unavailable_reason = str(e)

    async def chat(
        self, messages: list[dict[str, str]], temperature: float = 0.7, image_path: str = None
    ) -> str:
        t0 = time.perf_counter()
        success = False
        try:
            if not self.available:
                return f"Error: Model '{self.model_name}' is unavailable (likely due to missing API key)."
            if image_path:
                import base64

                # Use asyncio.to_thread for file I/O
                def read_image():
                    with open(image_path, "rb") as image_file:
                        return base64.b64encode(image_file.read()).decode("utf-8")

                base64_image = await asyncio.to_thread(read_image)

                for i in range(len(messages) - 1, -1, -1):
                    if messages[i]["role"] == "user":
                        original_text = messages[i]["content"]
                        messages[i]["content"] = [
                            {"type": "text", "text": original_text},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ]
                        break

            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
            )
            try:
                usage = getattr(response, "usage", None)
                if usage is not None:
                    self.record_token_usage(
                        getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                    )
            except Exception:
                pass
            success = True
            return response.choices[0].message.content
        except Exception as e:
            viki_logger.error("APILLM.chat failed for '%s': %s", self.model_name, e)
            return f"Error calling API Model '{self.model_name}'. Check logs for details."
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat")
            except Exception:
                pass

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str = None,
    ) -> T:
        t0 = time.perf_counter()
        success = False
        try:
            if not self.available:
                raise ValueError(f"Model '{self.model_name}' is unavailable.")
            if image_path:
                import base64

                # Use asyncio.to_thread for file I/O
                def read_image():
                    with open(image_path, "rb") as image_file:
                        return base64.b64encode(image_file.read()).decode("utf-8")

                base64_image = await asyncio.to_thread(read_image)

                for i in range(len(messages) - 1, -1, -1):
                    if messages[i]["role"] == "user":
                        original_text = messages[i]["content"] or ""
                        messages[i]["content"] = [
                            {"type": "text", "text": str(original_text)},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ]
                        break

            out, completion = await self.client.chat.completions.create_with_completion(
                model=self.model_name,
                messages=messages,
                response_model=response_model,
                temperature=temperature,
            )
            try:
                usage = getattr(completion, "usage", None)
                if usage is not None:
                    self.record_token_usage(
                        getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                    )
            except Exception:
                pass
            success = True
            return out
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat_structured")
            except Exception:
                pass

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        """Native streaming for OpenAI-compatible / Anthropic via instructor's underlying client."""
        if not self.available or self.client is None:
            yield f"Error: Model '{self.model_name}' is unavailable."
            return
        try:
            stream = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                try:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                except Exception:
                    delta = None
                if delta:
                    yield delta
        except Exception as e:
            viki_logger.error("APILLM.chat_stream failed for '%s': %s", self.model_name, e)
            yield f"Error streaming from '{self.model_name}'. Check logs for details."


def _ollama_model_exists(base_url: str, model_name: str) -> bool:
    """Check whether a model tag exists in the local Ollama instance."""
    try:
        req = urllib.request.Request(
            f"{base_url}/api/tags",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models", []):
            if m.get("name") == model_name or m.get("model") == model_name:
                return True
    except Exception:
        pass
    return False


class LocalLLM(LLMProvider):
    """Ollama provider with Async support and JSON mode."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        env_url = (os.environ.get("OLLAMA_HOST") or "").strip().rstrip("/")
        self.base_url = env_url or self.config.get("base_url", "http://127.0.0.1:11434").rstrip("/")
        if "localhost" in self.base_url:
            self.base_url = self.base_url.replace("localhost", "127.0.0.1")
        self._ollama_enable_thinking = bool(config.get("ollama_enable_thinking", False))
        _oo = config.get("ollama_options")
        self._ollama_options: dict[str, Any] = dict(_oo) if isinstance(_oo, dict) else {}
        # Verify the model actually exists in Ollama so the router can fall back.
        if not _ollama_model_exists(self.base_url, self.model_name):
            self.available = False
            self.unavailable_reason = (
                f"Ollama model '{self.model_name}' not found. "
                f"Run: ollama pull {self.model_name.split(':')[0]}"
            )
            viki_logger.warning(
                "Model '%s' (provider: ollama) disabled: %s",
                self.model_name,
                self.unavailable_reason,
            )

    def _ollama_options_merged(self, temperature: float) -> dict[str, Any]:
        o: dict[str, Any] = {"temperature": float(temperature)}
        o.update(self._ollama_options)
        return o

    def is_cloud(self) -> bool:
        # Local Ollama / OpenAI-compatible local servers (LM Studio, vLLM) running on this host.
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

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        """Native Ollama token streaming."""
        data = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "think": self._ollama_enable_thinking,
            "options": self._ollama_options_merged(temperature),
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat", json=data, timeout=300
                ) as resp:
                    if resp.status == 404:
                        yield f"Error: Model '{self.model_name}' not found."
                        return
                    async for raw in resp.content:
                        if not raw:
                            continue
                        line = raw.decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg = payload.get("message") or {}
                        if msg.get("thinking"):
                            continue
                        chunk = msg.get("content") or ""
                        if chunk:
                            yield chunk
                        if payload.get("done"):
                            return
        except Exception as e:
            yield f"Error streaming Local Model: {e}"

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        format: str = None,
        image_path: str = None,
        tools: list[dict[str, Any]] = None,
        response_format: dict = None,
    ) -> str:
        t0 = time.perf_counter()
        success = False
        if _debug_enabled():
            print(
                f"VIKI_DEBUG: LocalLLM.chat CALLED model={self.model_name} format={format}",
                flush=True,
            )
        try:
            data = {
                "model": self.model_name,
                "messages": messages,
                "stream": False,
                "think": self._ollama_enable_thinking,
                "options": self._ollama_options_merged(temperature),
            }
            if format:
                data["format"] = format
            if response_format:
                data["response_format"] = response_format

            if tools:
                data["tools"] = tools
                data["stream"] = False  # Tools require non-streaming for now

            if image_path:
                import base64

                # Use asyncio.to_thread for file I/O
                def read_image():
                    with open(image_path, "rb") as image_file:
                        return base64.b64encode(image_file.read()).decode("utf-8")

                base64_image = await asyncio.to_thread(read_image)
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i]["role"] == "user":
                        messages[i]["images"] = [base64_image]
                        break

            timeout = aiohttp.ClientTimeout(total=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.post(f"{self.base_url}/api/chat", json=data) as resp:
                        if resp.status == 404:
                            return f"Error: Model '{self.model_name}' not found."
                        resp_json = await resp.json()
                        if "error" in resp_json:
                            return f"Ollama Error: {resp_json['error']}"
                        if "message" not in resp_json:
                            return f"Error: Missing 'message' in Ollama response: {resp_json}"

                        # Handle Tool Calls
                        _msg = resp_json["message"]
                        _msg.pop("thinking", None)

                        # Record token usage
                        self.record_token_usage(
                            resp_json.get("prompt_eval_count", 0), resp_json.get("eval_count", 0)
                        )

                        if _msg.get("tool_calls"):
                            success = True
                            return json.dumps({"tool_calls": _msg["tool_calls"]})

                        success = True
                        return _msg.get("content") or ""
                except Exception as e:
                    return f"Error calling Local Model: {str(e)}"
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat")
            except Exception:
                pass

    async def chat_with_tools(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], temperature: float = 0.0
    ) -> dict[str, Any]:
        """Specific method for tool use that returns the full message object (content + tool_calls)."""
        t0 = time.perf_counter()
        success = False
        data = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "think": self._ollama_enable_thinking,
            "options": self._ollama_options_merged(temperature),
            "tools": tools,
        }

        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(f"{self.base_url}/api/chat", json=data) as resp:
                    if resp.status == 404:
                        raise ValueError(f"Model '{self.model_name}' not found.")

                    try:
                        resp_json = await resp.json()
                    except (aiohttp.ContentTypeError, json.JSONDecodeError) as e:
                        viki_logger.error(f"Failed to parse Ollama response: {e}")
                        raise ValueError(f"Invalid JSON response from Ollama: {resp.status}")

                    if "error" in resp_json:
                        raise ValueError(f"Ollama Error: {resp_json['error']}")

                    if "message" not in resp_json:
                        raise ValueError(f"Missing 'message' in response: {resp_json}")

                    # Record token usage
                    self.record_token_usage(
                        resp_json.get("prompt_eval_count", 0), resp_json.get("eval_count", 0)
                    )

                    success = True
                    msg = dict(resp_json["message"])
                    msg.pop("thinking", None)
                    return msg
            except Exception as e:
                viki_logger.error(f"Tool call failed: {e}")
                return {"role": "assistant", "content": f"Ollama Error: {str(e)}"}
            finally:
                try:
                    from viki.core.usage_log import emit_llm_inference

                    emit_llm_inference(self, time.perf_counter() - t0, success, "chat_with_tools")
                except Exception:
                    pass

    def _compact_json_output_guide(self, response_model: type[T]) -> str:
        """Short output instructions — full Pydantic JSON Schema makes Ollama echo the schema back."""
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

    async def _ollama_recover_after_schema_echo(
        self,
        msgs_without_guide: list[dict[str, Any]],
        response_model: type[T],
        temperature: float,
        image_path: str | None,
    ) -> str:
        """Second JSON attempt with stricter anti-schema instructions; then plain text if needed."""
        recovery = [dict(m) for m in msgs_without_guide]
        if response_model == VIKIResponse:
            recovery.append(
                {
                    "role": "system",
                    "content": (
                        "You returned a JSON Schema. That is wrong. Return ONLY a data object (one JSON value) "
                        "with fields final_thought, final_response, and action as described in the prior instructions. "
                        "final_response must contain your actual reply to the user."
                    ),
                }
            )
        else:
            recovery.append(
                {
                    "role": "system",
                    "content": "Return only the answer JSON object, not a schema describing it.",
                }
            )
        text = await self.chat(
            recovery,
            temperature=min(0.4, max(0.1, temperature)),
            format="json",
            image_path=image_path,
            response_format={
                "type": "json_schema",
                "json_schema": response_model.model_json_schema(),
            },
        )
        text = (text if isinstance(text, str) else str(text or "")).strip()
        try:
            data2 = self._parse_structured_json_heuristics(text)
            if not self._data_is_json_schema_echo(data2):
                return text
        except Exception:
            return text

        plain_msgs = [dict(m) for m in msgs_without_guide]
        plain_msgs.append(
            {
                "role": "system",
                "content": (
                    "Reply in plain language only. Answer the user's last message helpfully. "
                    "No JSON, no code fences, no preamble."
                ),
            }
        )
        return await self.chat(
            plain_msgs,
            temperature=min(0.55, max(0.15, temperature)),
            format=None,
            image_path=image_path,
        )

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str = None,
    ) -> T:
        """Parse structured output from local Ollama models with heuristic patching."""
        if _debug_enabled():
            print(
                f"VIKI_DEBUG: chat_structured ENTERED for {self.__class__.__name__} model={self.model_name} response_model={response_model.__name__}",
                flush=True,
            )
        msgs: list[dict[str, Any]] = [dict(m) for m in messages]

        if image_path:
            import base64

            def read_image():
                with open(image_path, "rb") as image_file:
                    return base64.b64encode(image_file.read()).decode("utf-8")

            base64_image = await asyncio.to_thread(read_image)
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i]["role"] == "user":
                    msgs[i]["images"] = [base64_image]
                    break

        guide = self._compact_json_output_guide(response_model)
        msgs.append({"role": "system", "content": guide})

        # Generate JSON schema for constrained decoding (Ollama 0.1.34+)
        json_schema = response_model.model_json_schema()
        content = await self.chat(
            msgs,
            temperature=temperature,
            format="json",
            image_path=image_path,
            response_format={"type": "json_schema", "json_schema": json_schema},
        )
        content = (content if isinstance(content, str) else str(content or "")).strip()
        if _debug_enabled():
            print(
                f"VIKI_DEBUG: Raw response ({len(content)} bytes) from {self.config.get('model_name')}: {repr(content[:500])}",
                flush=True,
            )
        viki_logger.debug("DEBUG: Raw response from %s", self.config.get("model_name"))

        try:
            data = self._parse_structured_json_heuristics(content)
            if response_model == VIKIResponse and self._data_is_json_schema_echo(data):
                viki_logger.info(
                    "Local model echoed JSON Schema; recovering with follow-up prompt."
                )
                content = await self._ollama_recover_after_schema_echo(
                    msgs[:-1], response_model, temperature, image_path
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
                        "content": (
                            "Your previous response was not valid JSON. "
                            "Return ONLY a single valid JSON object with no other text.\n"
                            + guide_text
                        ),
                    }
                )
                content2 = await self.chat(
                    retry_msgs,
                    temperature=min(0.5, temperature + 0.1 * retry_count),
                    format="json",
                    image_path=image_path,
                    response_format={
                        "type": "json_schema",
                        "json_schema": response_model.model_json_schema(),
                    },
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
        """Best-effort parsing for local model structured output."""
        match = re.search(r"```(?:json)?\s*({.*})\s*```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()
        else:
            content = content.replace("```json", "").replace("```", "").strip()

        # Fix Python/JSON mismatch (common with local models)
        content = (
            content.replace(": None", ": null")
            .replace(": True", ": true")
            .replace(": False", ": false")
        )

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try ast.literal_eval for single-quoted Python-dict-style output
            try:
                import ast

                val = ast.literal_eval(content)
                if isinstance(val, dict):
                    return val
            except Exception:
                pass

            # Last resort: Try replacing single quotes if double quotes are missing in keys
            if "'" in content and '"' not in content[:10]:
                try:
                    fixed = content.replace("'", '"')
                    return json.loads(fixed)
                except Exception:
                    pass
            raise

    def _structured_fallback(self, response_model: type[T], content: str, err: Exception) -> T:
        """Construct the response when structured parsing fails."""
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
        """Try to extract useful text from a failed parse. Use plain-text response when content is not JSON."""
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
        if self._looks_like_ollama_connection_error(s):
            viki_logger.debug("Detected Ollama connection error in fallback")
            return "I couldn't reach my local model. Make sure Ollama is running (e.g. run `ollama serve` or start the Ollama app), then try again."

        viki_logger.debug("Using plain-text fallback for model response")
        return s[:2000] if len(s) > 2000 else s

    def _try_parse_json_object(self, content: Any) -> Any:
        if not isinstance(content, str):
            return None
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None

    def _first_non_empty_string(self, obj: dict[str, Any], keys: list[str]) -> str | None:
        for key in keys:
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return None

    def _looks_like_ollama_connection_error(self, text: str) -> bool:
        return (
            text.startswith("Error calling Local Model")
            or "Cannot connect to host" in text
            or "127.0.0.1:11434" in text
        )

    def _patch_viki_response(self, data: dict) -> dict:
        """Apply heuristic patches for common local LLM schema errors.
        These handle the various ways models mangle the VIKIResponse schema."""
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


class ModelFactory:
    @staticmethod
    def create(
        profile_name: str, profile_config: dict[str, Any], provider_config: dict[str, Any]
    ) -> LLMProvider:
        provider_type = provider_config.get("type", "mock")
        merged_config = {**provider_config, **profile_config}
        merged_config.setdefault("provider", provider_type)

        if provider_type == "mock":
            return FallbackLLM(merged_config)
        if provider_type == "api":
            return APILLM(merged_config)
        if provider_type == "anthropic":
            # Instructor handles Anthropic via the same interface if configured.
            merged_config["type"] = "api"
            return APILLM(merged_config)
        if provider_type == "local":
            # Native Ollama tool calling is opt-in per profile (YAML); default off.
            merged_config.setdefault("supports_native_tools", False)
            return LocalLLM(merged_config)
        if provider_type in ("gemini", "google", "vertex"):
            from viki.core.inference_providers import GeminiLLM

            return GeminiLLM(merged_config)
        if provider_type == "groq":
            from viki.core.inference_providers import GroqLLM

            return GroqLLM(merged_config)
        if provider_type == "mistral":
            from viki.core.inference_providers import MistralLLM

            return MistralLLM(merged_config)
        if provider_type in ("bedrock", "aws_bedrock"):
            from viki.core.inference_providers import BedrockLLM

            return BedrockLLM(merged_config)
        raise ValueError(f"Unknown provider type: {provider_type}")


class ModelRouter:
    CONSECUTIVE_FAIL_THRESHOLD = 3
    COOLDOWN_SECONDS = 60

    def __init__(
        self,
        config_path: str,
        air_gap: bool = False,
        local_llm_only: bool = False,
        budget=None,
        system_settings: dict[str, Any] | None = None,
    ):
        self.models = {}
        self.default_model = None
        self.air_gap = air_gap
        self.local_llm_only = local_llm_only
        self.budget = budget
        self._budget_config: dict[str, Any] = {}
        self._system_settings = system_settings
        self._model_cooldowns: dict[str, dict[str, Any]] = {}
        self._load_config(config_path)

    def _model_allowed(self, model: LLMProvider) -> bool:
        if not model.available:
            return False
        if model.config.get("training_only"):
            return False
        if self._model_on_cooldown(model.model_name):
            return False
        try:
            cloud = model.is_cloud()
        except Exception:
            cloud = isinstance(model, APILLM)
        if self.air_gap and cloud:
            return False
        if self.local_llm_only and cloud:
            return False
        if self.budget is not None and cloud:
            try:
                breaker = self.budget.get_breaker(getattr(model, "provider_name", "unknown"))
                if breaker.is_open():
                    return False
            except Exception:
                pass
        return True

    def _model_on_cooldown(self, model_name: str) -> bool:
        entry = self._model_cooldowns.get(model_name)
        if not entry:
            return False
        if time.time() >= entry["cooldown_until"]:
            del self._model_cooldowns[model_name]
            return False
        return True

    def record_model_failure(self, model_name: str):
        now = time.time()
        entry = self._model_cooldowns.setdefault(
            model_name, {"consecutive_failures": 0, "cooldown_until": 0}
        )
        entry["consecutive_failures"] += 1
        if entry["consecutive_failures"] >= self.CONSECUTIVE_FAIL_THRESHOLD:
            entry["cooldown_until"] = now + self.COOLDOWN_SECONDS
            viki_logger.warning(
                "Model '%s' failed %d times; cooling down for %ds",
                model_name,
                self.CONSECUTIVE_FAIL_THRESHOLD,
                self.COOLDOWN_SECONDS,
            )

    def record_model_success(self, model_name: str):
        self._model_cooldowns.pop(model_name, None)

    def _first_allowed_model(self) -> LLMProvider | None:
        for m in self.models.values():
            if self._model_allowed(m):
                return m
        for m in self.models.values():
            if m.available and isinstance(m, LocalLLM):
                return m
        for m in self.models.values():
            if m.available:
                return m
        return None

    def _load_config(self, path: str):
        try:
            with open(path) as f:
                config = yaml.safe_load(f)

            providers = config.get("models", {}).get("providers", {})
            profiles = config.get("models", {}).get("profiles", {})
            default_profile = config.get("models", {}).get("default", "mock-model")
            self._budget_config = dict(config.get("models", {}).get("budget", {}) or {})

            # Build a default LLMBudget if the controller didn't pass one in.
            if self.budget is None and self._budget_config:
                try:
                    from viki.core.resource_budget import LLMBudget

                    self.budget = LLMBudget(self._budget_config)
                except Exception as e:
                    viki_logger.debug("Failed to init LLMBudget: %s", e)

            for name, profile in profiles.items():
                provider_name = profile.get("provider")
                if provider_name in providers:
                    provider_conf = providers[provider_name]
                    # Merge `provider` name into config so providers know which one they are.
                    merged_provider_conf = {**provider_conf, "provider": provider_name}
                    eff_profile = _effective_profile_for_factory(
                        profile, merged_provider_conf, self._system_settings
                    )
                    self.models[name] = ModelFactory.create(name, eff_profile, merged_provider_conf)

            preferred: LLMProvider | None = None
            if default_profile in self.models:
                preferred = self.models[default_profile]
            elif self.models:
                preferred = list(self.models.values())[0]

            if preferred and self._model_allowed(preferred):
                self.default_model = preferred
            else:
                self.default_model = self._first_allowed_model() or FallbackLLM(
                    {"model_name": "fallback-mock"}
                )
                if preferred and not preferred.available:
                    viki_logger.warning(
                        "Default model profile '%s' is unavailable (%s). Using '%s' instead.",
                        default_profile,
                        getattr(preferred, "unavailable_reason", "unknown"),
                        getattr(self.default_model, "model_name", "fallback"),
                    )

        except (OSError, yaml.YAMLError, FileNotFoundError, KeyError) as e:
            viki_logger.error(f"Failed to load model config from {path}: {e}")
            self.default_model = FallbackLLM({"model_name": "error-fallback"})

    def get_model(self, capabilities: list[str] = None, tier: str = "standard") -> LLMProvider:
        if not capabilities and tier == "standard":
            if self._model_allowed(self.default_model):
                return self.default_model
            fb = self._first_allowed_model()
            return fb or self.default_model

        best_candidate = None
        best_score = -1

        for model in self.models.values():
            if not self._model_allowed(model):
                continue

            model_caps = model.config.get("capabilities", [])
            model_tier = model.config.get("tier", "standard").lower()

            # 1. Capability matching
            matched_caps = sum(1 for cap in (capabilities or []) if cap in model_caps)

            # 2. Priority from config (1-4, higher is better)
            priority = model.config.get("priority", 2)

            # 3. Calculate base score
            score = (matched_caps * priority) + (model.trust_score * 0.5)

            # 4. Tier matching bonus (Strong bias)
            if model_tier == tier.lower():
                score += 10.0

            # 5. Penalize high latency for fast_response capability or fast tier
            is_fast = "fast_response" in (capabilities or []) or tier == "fast"
            if is_fast and model.avg_latency > 0:
                latency_penalty = model.avg_latency / 10.0
                score -= latency_penalty

            # 6. Penalize high error rate
            if model.call_count > 10:
                error_rate = model.error_count / model.call_count
                error_penalty = error_rate * 5.0
                score -= error_penalty

            if score > best_score:
                best_score = score
                best_candidate = model

        if best_candidate:
            return best_candidate
        if self._model_allowed(self.default_model):
            return self.default_model
        return self._first_allowed_model() or self.default_model

    def get_health_snapshot(self) -> dict[str, Any]:
        available = []
        unavailable = {}
        for name, model in self.models.items():
            if model.available:
                available.append(name)
            else:
                unavailable[name] = model.unavailable_reason or "unavailable"
        default_name = None
        for name, model in self.models.items():
            if model is self.default_model:
                default_name = name
                break
        return {
            "default_model": default_name,
            "available_models": available,
            "unavailable_models": unavailable,
            "budget": self.budget.snapshot() if self.budget is not None else {},
        }

    def apply_eval_signal(self, model_name: str, pass_rate: float) -> None:
        """
        Phase 2: feed eval-suite pass rates into the trust score so good evals
        increase a model's priority on subsequent routing decisions.
        """
        model = self.models.get(model_name)
        if model is None:
            return
        # Smooth update: blend current trust with eval pass rate.
        prev = float(getattr(model, "trust_score", 1.0))
        # Pull trust toward pass_rate by 30%.
        updated = max(0.0, min(1.0, 0.7 * prev + 0.3 * float(pass_rate)))
        model.trust_score = updated

    def get_failover_chain(
        self, capabilities: list[str] | None = None, max_models: int = 4
    ) -> list[LLMProvider]:
        """
        Ranked list of allowed models for the given capabilities.
        Used by `chat_with_failover` and the cross-provider Ensemble.
        """
        scored: list[tuple] = []
        for model in self.models.values():
            if not self._model_allowed(model):
                continue
            model_caps = model.config.get("capabilities", [])
            matched = sum(1 for cap in (capabilities or []) if cap in model_caps)
            priority = model.config.get("priority", 2)
            score = (matched * priority) + (model.trust_score * 0.5)
            if model.call_count > 10:
                error_rate = model.error_count / model.call_count
                score -= error_rate * 5.0
            scored.append((score, model))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:max_models]]

    @staticmethod
    def _looks_like_error(text: Any) -> bool:
        if not isinstance(text, str):
            return False
        prefixes = (
            "Error calling API Model:",
            "Error calling Local Model:",
            "Error calling Gemini Model:",
            "Error calling Groq Model:",
            "Error calling Mistral Model:",
            "Error calling Bedrock Model:",
            "Error: Model ",
        )
        return any(text.startswith(p) for p in prefixes)

    @staticmethod
    def _redact_messages_for_cloud(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Apply secret redaction so credentials never leak across cloud boundaries."""
        try:
            from viki.core.security_guard import redact_secrets

            redacted: list[dict[str, str]] = []
            for m in messages:
                content = m.get("content")
                if isinstance(content, str):
                    redacted.append({**m, "content": redact_secrets(content)})
                elif isinstance(content, list):
                    parts = []
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append({**part, "text": redact_secrets(part["text"])})
                        else:
                            parts.append(part)
                    redacted.append({**m, "content": parts})
                else:
                    redacted.append(m)
            return redacted
        except Exception:
            return messages

    async def chat_with_failover(
        self,
        messages: list[dict[str, str]],
        capabilities: list[str] | None = None,
        temperature: float = 0.7,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        """
        Try the highest-scoring allowed model; on transient error, retry with the next one.
        Returns a dict with `text`, `model_name`, `attempts`, `errors`.
        """
        chain = self.get_failover_chain(capabilities, max_models=max_attempts)
        if not chain:
            chain = [self.get_model(capabilities)]
        errors: list[dict[str, Any]] = []
        for attempt, model in enumerate(chain):
            try:
                outbound = (
                    self._redact_messages_for_cloud(messages) if model.is_cloud() else messages
                )
                if self.budget is not None and model.is_cloud():
                    estimate = model.estimate_cost_usd(prompt_tokens=512, completion_tokens=256)
                    allowed, reason = self.budget.can_spend(
                        getattr(model, "provider_name", "unknown"),
                        estimate,
                        is_cloud=True,
                    )
                    if not allowed:
                        errors.append({"model": model.model_name, "reason": reason})
                        continue
                t0 = time.perf_counter()
                text = await model.chat(outbound, temperature=temperature)
                latency = time.perf_counter() - t0

                if self._looks_like_error(text):
                    model.record_performance(latency, False)
                    if self.budget is not None and model.is_cloud():
                        self.budget.record_failure(getattr(model, "provider_name", "unknown"))
                    errors.append({"model": model.model_name, "reason": text})
                    continue

                model.record_performance(latency, True)
                if self.budget is not None and model.is_cloud():
                    self.budget.record_success(getattr(model, "provider_name", "unknown"))
                    self.budget.record_cost(
                        getattr(model, "provider_name", "unknown"),
                        getattr(model, "total_cost_usd", 0.0),
                    )
                return {
                    "text": text,
                    "model_name": model.model_name,
                    "attempts": attempt + 1,
                    "errors": errors,
                }
            except Exception as e:
                if self.budget is not None and model.is_cloud():
                    self.budget.record_failure(getattr(model, "provider_name", "unknown"))
                errors.append({"model": model.model_name, "reason": str(e)})
                model.record_performance(0.0, False)
        return {
            "text": "",
            "model_name": None,
            "attempts": len(chain),
            "errors": errors,
        }
