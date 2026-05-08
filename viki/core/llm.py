import os
import json
import re
import time
import yaml
import asyncio
import aiohttp
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Type, TypeVar
from pydantic import BaseModel
from viki.core.schema import VIKIResponse, VIKIResponseLite, ThoughtObject, ThoughtObjectLite
from viki.config.logger import viki_logger

T = TypeVar("T", bound=BaseModel)


def _resolve_ollama_thinking_from_settings(system_settings: Optional[Dict[str, Any]]) -> bool:
    """Env VIKI_OLLAMA_THINK overrides settings.system.ollama_enable_thinking."""
    env = (os.environ.get("VIKI_OLLAMA_THINK") or "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    sys = (system_settings or {}).get("system") or {}
    return bool(sys.get("ollama_enable_thinking", False))


def _resolve_ollama_options_from_settings(system_settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    sys = (system_settings or {}).get("system") or {}
    opts = sys.get("ollama_options")
    return dict(opts) if isinstance(opts, dict) else {}


def _effective_profile_for_factory(
    profile: Dict[str, Any],
    provider_conf: Dict[str, Any],
    system_settings: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
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
    def __init__(self, request: str, messages: List[Dict[str, str]] = None):
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
        
    def build(self) -> List[Dict[str, str]]:
        system_content = f"{self.identity}\n\nCOGNITIVE PROTOCOLS:{self.cognitive_instructions}\n\nCONTEXT:\n{self.context}"
        
        final_messages = [{"role": "system", "content": system_content}]
        final_messages.extend(self.messages)
        
        # Always add the current request as the last user message
        final_messages.append({"role": "user", "content": self.request})
             
        return final_messages

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, config: Dict[str, Any]):
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
        # Default conservative: cloud unless overridden by LocalLLM/MockLLM subclasses.
        return True

    def record_performance(self, latency: float, success: bool):
        self.call_count += 1
        n = self.call_count
        self.avg_latency = ((self.avg_latency * (n-1)) + latency) / n
        
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
        return (
            (prompt_tokens / 1000.0) * self.cost_per_1k_in
            + (completion_tokens / 1000.0) * self.cost_per_1k_out
        )

    def record_token_usage(self, input_tokens: int, output_tokens: int) -> float:
        """Update token counters and return the delta cost for this call."""
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        delta = (
            (input_tokens / 1000.0) * self.cost_per_1k_in
            + (output_tokens / 1000.0) * self.cost_per_1k_out
        )
        self.total_cost_usd += delta
        return delta

    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """Send a asynchronous chat request to the LLM."""
        pass

    @abstractmethod
    async def chat_structured(self, messages: List[Dict[str, str]], response_model: Type[T], temperature: float = 0.0, image_path: str = None) -> T:
        """Send a structured chat request returning a Pydantic model with optional visual context."""
        pass

    async def chat_stream(self, messages: List[Dict[str, str]], temperature: float = 0.7):
        """
        Default streaming implementation: yields the full response as a single chunk.
        Concrete providers should override with native streaming where supported.
        """
        result = await self.chat(messages, temperature=temperature)
        if result:
            yield result

class MockLLM(LLMProvider):
    """Mock LLM for testing and development."""

    def is_cloud(self) -> bool:
        return False

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        t0 = time.perf_counter()
        success = False
        try:
            await asyncio.sleep(0.1) # Simulate network
            all_text = "\n".join([m.get('content', '') for m in messages]).lower()
            # Security-scan prompt path (SafetyLayer.scan_request):
            # If asked to output EXACTLY 'SAFE' for a given user request, mock a refusal that includes 'violate'.
            if "output exactly the word 'safe'" in all_text:
                illegal_present = ("illegal" in all_text) or ("unsafe" in all_text)
                if illegal_present:
                    success = True
                    return "This request cannot be supported because it involves illegal or harmful activity and violates protocols."
                success = True
                return "SAFE"
            if "semantic extraction" in all_text or "extract permanent user facts" in all_text:
                success = True
                return json.dumps({
                    "fact": "Optimization sub-routine should be used for complex paths and heuristics applied.",
                    "rel": ["System", "applies", "heuristics"],
                    "confidence": 0.95
                })
            success = True
            return "Mock response for " + self.model_name
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat")
            except Exception:
                pass

    async def chat_structured(self, messages: List[Dict[str, str]], response_model: Type[T], temperature: float = 0.0, image_path: str = None) -> T:
        t0 = time.perf_counter()
        success = False
        try:
            await asyncio.sleep(0.1)
            if response_model == VIKIResponse:
                all_text = "\n".join([m["content"] for m in messages]).lower()
                if "plan" in all_text:
                    heur_present = "heuristics" in all_text
                    success = True
                    return VIKIResponse(
                        final_thought=ThoughtObject(
                            intent_summary="Planning", primary_strategy="Think", confidence=1.0
                        ),
                        final_response="I see the Heuristics Applied successfully."
                        if heur_present
                        else "Planning trip...",
                    )
                success = True
                return VIKIResponse(
                    final_thought=ThoughtObject(
                        intent_summary="Mock", primary_strategy="Mock response", confidence=1.0
                    ),
                    final_response="This is a mock response because I'm in testing mode.",
                )
            if response_model == VIKIResponseLite:
                success = True
                return VIKIResponseLite(final_response="This is a mock response.", confidence=1.0)

            # Support for Learning Analysis
            try:
                from viki.core.learning import VIKILessonBatch, VIKILesson

                if response_model == VIKILessonBatch:
                    success = True
                    return VIKILessonBatch(
                        lessons=[
                            VIKILesson(
                                topic="planning",
                                fact="Optimization sub-routine should be used for complex paths and heuristics applied.",
                                strategy="Use A*",
                                significance=0.8,
                            )
                        ]
                    )
            except ImportError:
                pass

            success = True
            return response_model()
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat_structured")
            except Exception:
                pass


def _looks_like_openai_secret(key: Optional[str]) -> bool:
    """True only for keys that can authenticate api.openai.com (not placeholders like 'ollama')."""
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    lowered = s.lower()
    if lowered in ("ollama", "none", "dummy", "placeholder", "test", "your-api-key-here", "changeme"):
        return False
    return s.startswith("sk-")  # includes sk-proj-


def _looks_like_anthropic_secret(key: Optional[str]) -> bool:
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    lowered = s.lower()
    if lowered in ("ollama", "none", "dummy", "placeholder", "test", "your-api-key-here", "changeme"):
        return False
    return s.startswith("sk-ant-")


class APILLM(LLMProvider):
    """OpenAI-compatible API provider with Instructor support."""
    
    def __init__(self, config: Dict[str, Any]):
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
                    AsyncAnthropic(api_key=api_key),
                    mode=instructor.Mode.ANTHROPIC_JSON
                )
            else:
                from openai import AsyncOpenAI
                base_url = self.config.get('base_url', 'https://api.openai.com/v1')
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
                    mode=instructor.Mode.JSON
                )
        except ImportError as e:
            viki_logger.warning(
                f"Model '{self.model_name}' (provider: {self.provider_type}) disabled: optional API dependency missing or broken: {e}"
            )
            self.client = None
            self.available = False
            self.unavailable_reason = f"optional dependency missing or broken: {e}"
        except Exception as e:
            viki_logger.warning(f"Model '{self.model_name}' (provider: {self.provider_type}) disabled: {e}")
            self.client = None
            self.available = False
            self.unavailable_reason = str(e)

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, image_path: str = None) -> str:
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
                        return base64.b64encode(image_file.read()).decode('utf-8')

                base64_image = await asyncio.to_thread(read_image)

                for i in range(len(messages) - 1, -1, -1):
                    if messages[i]['role'] == 'user':
                        original_text = messages[i]['content']
                        messages[i]['content'] = [
                            {"type": "text", "text": original_text},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
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
            return f"Error calling API Model: {str(e)}"
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat")
            except Exception:
                pass

    async def chat_structured(self, messages: List[Dict[str, str]], response_model: Type[T], temperature: float = 0.0, image_path: str = None) -> T:
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
                        return base64.b64encode(image_file.read()).decode('utf-8')

                base64_image = await asyncio.to_thread(read_image)

                for i in range(len(messages) - 1, -1, -1):
                    if messages[i]['role'] == 'user':
                        original_text = messages[i]['content'] or ""
                        messages[i]['content'] = [
                            {"type": "text", "text": str(original_text)},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                        ]
                        break

            out = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_model=response_model,
                temperature=temperature,
            )
            success = True
            return out
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat_structured")
            except Exception:
                pass

    async def chat_stream(self, messages: List[Dict[str, str]], temperature: float = 0.7):
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
            yield f"Error streaming API Model: {e}"


class LocalLLM(LLMProvider):
    """Ollama provider with Async support and JSON mode."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = self.config.get('base_url', 'http://127.0.0.1:11434').rstrip('/')
        if 'localhost' in self.base_url:
            self.base_url = self.base_url.replace('localhost', '127.0.0.1')
        self._ollama_enable_thinking = bool(config.get("ollama_enable_thinking", False))
        _oo = config.get("ollama_options")
        self._ollama_options: Dict[str, Any] = dict(_oo) if isinstance(_oo, dict) else {}

    def _ollama_options_merged(self, temperature: float) -> Dict[str, Any]:
        o: Dict[str, Any] = {"temperature": float(temperature)}
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

    async def chat_stream(self, messages: List[Dict[str, str]], temperature: float = 0.7):
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
                async with session.post(f"{self.base_url}/api/chat", json=data, timeout=300) as resp:
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

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, format: str = None, image_path: str = None, tools: List[Dict[str, Any]] = None) -> str:
        t0 = time.perf_counter()
        success = False
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

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(f"{self.base_url}/api/chat", json=data, timeout=120) as resp:
                        if resp.status == 404:
                            return f"Error: Model '{self.model_name}' not found."
                        resp_json = await resp.json()

                        # Handle Tool Calls
                        _msg = resp_json["message"]
                        _msg.pop("thinking", None)
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

    async def chat_with_tools(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]], temperature: float = 0.0) -> Dict[str, Any]:
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

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{self.base_url}/api/chat", json=data, timeout=120) as resp:
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

    def _compact_json_output_guide(self, response_model: Type[T]) -> str:
        """Short output instructions — full Pydantic JSON Schema makes Ollama echo the schema back."""
        if response_model == VIKIResponse:
            return (
                "### JSON OUTPUT (required) ###\n"
                "Return one JSON object only. Use keys: final_thought (object with intent_summary, "
                "primary_strategy, confidence) and final_response (string — your full answer to the user).\n"
                "Do NOT return a JSON Schema (no top-level properties, required, or definitions).\n"
                "Example: {\"final_thought\":{\"intent_summary\":\"User asked a question\","
                "\"primary_strategy\":\"Answer helpfully\",\"confidence\":0.82},"
                "\"final_response\":\"Here is my answer...\"}"
            )
        if response_model == VIKIResponseLite:
            return (
                "### JSON OUTPUT (required) ###\n"
                "Return one JSON object: {\"final_response\":\"your answer\",\"confidence\":0.85,\"action\":null}\n"
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
        msgs_without_guide: List[Dict[str, Any]],
        response_model: Type[T],
        temperature: float,
        image_path: Optional[str],
    ) -> str:
        """Second JSON attempt with stricter anti-schema instructions; then plain text if needed."""
        recovery = [dict(m) for m in msgs_without_guide]
        if response_model == VIKIResponse:
            recovery.append(
                {
                    "role": "system",
                    "content": (
                        "You returned a JSON Schema. That is wrong. Return ONLY a data object (one JSON value) "
                        "with fields final_thought and final_response as described in the prior instructions. "
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

    async def chat_structured(self, messages: List[Dict[str, str]], response_model: Type[T], temperature: float = 0.0, image_path: str = None) -> T:
        """Parse structured output from local Ollama models with heuristic patching."""
        msgs: List[Dict[str, Any]] = [dict(m) for m in messages]

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

        content = await self.chat(msgs, temperature=temperature, format="json", image_path=image_path)
        content = (content if isinstance(content, str) else str(content or "")).strip()
        viki_logger.debug("DEBUG: Raw response from %s", self.config.get("model_name"))

        try:
            data = self._parse_structured_json_heuristics(content)
            if response_model == VIKIResponse and self._data_is_json_schema_echo(data):
                viki_logger.info("Local model echoed JSON Schema; recovering with follow-up prompt.")
                content = await self._ollama_recover_after_schema_echo(
                    msgs[:-1], response_model, temperature, image_path
                )
                content = (content if isinstance(content, str) else str(content or "")).strip()
                if content.startswith("{") or content.startswith("["):
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
                    return self._structured_fallback(response_model, content, ValueError("schema echo persisted"))

            if response_model == VIKIResponse:
                data = self._patch_viki_response(data)
            return response_model.model_validate_json(json.dumps(data))
        except Exception as e:
            viki_logger.warning("Structured parse failed for %s: %s", response_model.__name__, e)
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
            # Last resort: Try replacing single quotes if double quotes are missing in keys
            if "'" in content and '"' not in content[:10]:
                fixed = content.replace("'", '"')
                return json.loads(fixed)
            raise

    def _structured_fallback(self, response_model: Type[T], content: str, err: Exception) -> T:
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
            extracted = self._first_non_empty_string(raw, ["final_response", "response", "message", "text", "content", "answer"])
            if extracted:
                return extracted

        if s.startswith("{") or s.startswith("["):
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

    def _first_non_empty_string(self, obj: Dict[str, Any], keys: List[str]) -> Optional[str]:
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

    def _patch_response_plan(self, data: dict) -> Optional[dict]:
        if "response" in data and "plan" in data and "final_thought" not in data:
            response_obj = data["response"]
            intent = response_obj.get("intent", "unknown") if isinstance(response_obj, dict) else str(response_obj)
            plan = str(data.get("plan", []))
            return {
                "final_thought": {"intent_summary": intent, "primary_strategy": plan, "confidence": 0.8},
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
            thought_obj: Dict[str, Any] = {}
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
            data["action"] = {"skill_name": data.pop("skill_name"), "parameters": data.pop("parameters")}

    def _patch_missing_final_thought(self, data: dict) -> None:
        if "final_thought" not in data:
            summary = data.get("final_response", "Request received, formulating response...")
            strategy = data.get("internal_metacognition", summary)
            data["final_thought"] = {
                "intent_summary": summary[:200] if isinstance(summary, str) else "User request",
                "primary_strategy": strategy[:200] if isinstance(strategy, str) else "Direct response",
                "confidence": 0.7,
            }

class ModelFactory:
    @staticmethod
    def create(profile_name: str, profile_config: Dict[str, Any], provider_config: Dict[str, Any]) -> LLMProvider:
        provider_type = provider_config.get("type", "mock")
        merged_config = {**provider_config, **profile_config}
        merged_config.setdefault("provider", provider_type)

        if provider_type == "mock":
            return MockLLM(merged_config)
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
            from viki.core.llm_providers import GeminiLLM
            return GeminiLLM(merged_config)
        if provider_type == "groq":
            from viki.core.llm_providers import GroqLLM
            return GroqLLM(merged_config)
        if provider_type == "mistral":
            from viki.core.llm_providers import MistralLLM
            return MistralLLM(merged_config)
        if provider_type in ("bedrock", "aws_bedrock"):
            from viki.core.llm_providers import BedrockLLM
            return BedrockLLM(merged_config)
        raise ValueError(f"Unknown provider type: {provider_type}")

class ModelRouter:
    def __init__(
        self,
        config_path: str,
        air_gap: bool = False,
        local_llm_only: bool = False,
        budget=None,
        system_settings: Optional[Dict[str, Any]] = None,
    ):
        self.models = {}
        self.default_model = None
        self.air_gap = air_gap
        self.local_llm_only = local_llm_only
        self.budget = budget
        self._budget_config: Dict[str, Any] = {}
        self._system_settings = system_settings
        self._load_config(config_path)

    def _model_allowed(self, model: LLMProvider) -> bool:
        if not model.available:
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

    def _first_allowed_model(self) -> Optional[LLMProvider]:
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
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
                
            providers = config.get('models', {}).get('providers', {})
            profiles = config.get('models', {}).get('profiles', {})
            default_profile = config.get('models', {}).get('default', 'mock-model')
            self._budget_config = dict(config.get('models', {}).get('budget', {}) or {})

            # Build a default LLMBudget if the controller didn't pass one in.
            if self.budget is None and self._budget_config:
                try:
                    from viki.core.llm_budget import LLMBudget

                    self.budget = LLMBudget(self._budget_config)
                except Exception as e:
                    viki_logger.debug("Failed to init LLMBudget: %s", e)

            for name, profile in profiles.items():
                provider_name = profile.get('provider')
                if provider_name in providers:
                    provider_conf = providers[provider_name]
                    # Merge `provider` name into config so providers know which one they are.
                    merged_provider_conf = {**provider_conf, "provider": provider_name}
                    eff_profile = _effective_profile_for_factory(
                        profile, merged_provider_conf, self._system_settings
                    )
                    self.models[name] = ModelFactory.create(name, eff_profile, merged_provider_conf)

            preferred: Optional[LLMProvider] = None
            if default_profile in self.models:
                preferred = self.models[default_profile]
            elif self.models:
                preferred = list(self.models.values())[0]

            if preferred and self._model_allowed(preferred):
                self.default_model = preferred
            else:
                self.default_model = self._first_allowed_model() or MockLLM({'model_name': 'fallback-mock'})
                if preferred and not preferred.available:
                    viki_logger.warning(
                        "Default model profile '%s' is unavailable (%s). Using '%s' instead.",
                        default_profile,
                        getattr(preferred, "unavailable_reason", "unknown"),
                        getattr(self.default_model, "model_name", "fallback"),
                    )
                 
        except (yaml.YAMLError, IOError, FileNotFoundError, KeyError) as e:
            viki_logger.error(f"Failed to load model config from {path}: {e}")
            self.default_model = MockLLM({'model_name': 'error-fallback'})

    def get_model(self, capabilities: List[str] = None) -> LLMProvider:
        if not capabilities:
            if self._model_allowed(self.default_model):
                return self.default_model
            fb = self._first_allowed_model()
            return fb or self.default_model
            
        best_candidate = None
        best_score = -1
        
        for model in self.models.values():
            if not self._model_allowed(model):
                continue

            model_caps = model.config.get('capabilities', [])
            
            # 1. Capability matching
            matched_caps = sum(1 for cap in capabilities if cap in model_caps)
            
            # 2. Priority from config (1-4, higher is better)
            priority = model.config.get('priority', 2)
            
            # 3. Calculate base score
            score = (matched_caps * priority) + (model.trust_score * 0.5)
            
            # 4. Penalize high latency for fast_response capability
            if 'fast_response' in capabilities and model.avg_latency > 0:
                latency_penalty = model.avg_latency / 10.0
                score -= latency_penalty
            
            # 5. Penalize high error rate
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

    def get_health_snapshot(self) -> Dict[str, Any]:
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

    def get_failover_chain(self, capabilities: Optional[List[str]] = None, max_models: int = 4) -> List[LLMProvider]:
        """
        Ranked list of allowed models for the given capabilities.
        Used by `chat_with_failover` and the cross-provider Ensemble.
        """
        scored: List[tuple] = []
        for model in self.models.values():
            if not self._model_allowed(model):
                continue
            model_caps = model.config.get('capabilities', [])
            matched = sum(1 for cap in (capabilities or []) if cap in model_caps)
            priority = model.config.get('priority', 2)
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
    def _redact_messages_for_cloud(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Apply secret redaction so credentials never leak across cloud boundaries."""
        try:
            from viki.core.safety import redact_secrets

            redacted: List[Dict[str, str]] = []
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
        messages: List[Dict[str, str]],
        capabilities: Optional[List[str]] = None,
        temperature: float = 0.7,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        """
        Try the highest-scoring allowed model; on transient error, retry with the next one.
        Returns a dict with `text`, `model_name`, `attempts`, `errors`.
        """
        chain = self.get_failover_chain(capabilities, max_models=max_attempts)
        if not chain:
            chain = [self.get_model(capabilities)]
        errors: List[Dict[str, Any]] = []
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
