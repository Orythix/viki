"""
Phase 1: additional cloud LLM provider implementations.

These are loaded lazily so missing optional dependencies do not block the rest
of VIKI from booting. Each provider:
- inherits from `LLMProvider`,
- exposes async `chat`, `chat_structured`, and `chat_stream`,
- reports `is_cloud() -> True`,
- records token usage / cost when the upstream client returns usage info.

Currently shipped:
- GeminiLLM  : Google `google-genai` SDK.
- GroqLLM    : Groq's OpenAI-compatible API (very low latency Llama / Mixtral).
- MistralLLM : Mistral's official SDK or OpenAI-compatible endpoint.
- BedrockLLM : AWS Bedrock (Claude / Llama / Mistral).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from viki.config.logger import viki_logger
from viki.core.model import LLMProvider

T = TypeVar("T", bound=BaseModel)


def _looks_like_gemini_secret(key: str | None) -> bool:
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    if s.lower() in (
        "ollama",
        "none",
        "dummy",
        "placeholder",
        "test",
        "your-api-key-here",
        "changeme",
    ):
        return False
    # Google AI Studio keys typically begin with "AI" and are ~39 chars.
    return len(s) >= 20


def _looks_like_groq_secret(key: str | None) -> bool:
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    if s.lower() in (
        "ollama",
        "none",
        "dummy",
        "placeholder",
        "test",
        "your-api-key-here",
        "changeme",
    ):
        return False
    return s.startswith("gsk_")


def _looks_like_mistral_secret(key: str | None) -> bool:
    if not key or not str(key).strip():
        return False
    s = str(key).strip()
    if s.lower() in (
        "ollama",
        "none",
        "dummy",
        "placeholder",
        "test",
        "your-api-key-here",
        "changeme",
    ):
        return False
    return len(s) >= 16


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
class GeminiLLM(LLMProvider):
    """Google Gemini (gemini-2.5-pro / flash) via `google-genai`."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.provider_name = "gemini"
        self._client: Any = None
        api_key = os.getenv(self.config.get("api_key_env", "GOOGLE_API_KEY"))
        if not _looks_like_gemini_secret(api_key):
            self.available = False
            self.unavailable_reason = "Gemini API key missing or invalid; expected GOOGLE_API_KEY."
            return
        try:
            from google import genai  # type: ignore

            self._client = genai.Client(api_key=api_key)
            self._genai = genai
        except ImportError as e:
            self.available = False
            self.unavailable_reason = f"google-genai missing: {e}"
        except Exception as e:
            self.available = False
            self.unavailable_reason = str(e)

    def is_cloud(self) -> bool:
        return True

    @staticmethod
    def _to_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents = []
        for m in messages:
            role = m.get("role", "user")
            text = m.get("content")
            if not isinstance(text, str):
                text = str(text)
            mapped_role = "user"
            if role == "assistant" or role == "model":
                mapped_role = "model"
            elif role == "system":
                # Gemini handles system via a separate system_instruction; we prepend.
                mapped_role = "user"
            contents.append({"role": mapped_role, "parts": [{"text": text}]})
        return contents

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        if not self.available or self._client is None:
            return f"Error: Model '{self.model_name}' is unavailable."
        t0 = time.perf_counter()
        success = False
        try:
            system_msg = next((m for m in messages if m.get("role") == "system"), None)
            user_messages = [m for m in messages if m.get("role") != "system"]
            contents = self._to_contents(user_messages)

            def _call():
                return self._client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config={
                        "temperature": temperature,
                        "system_instruction": (system_msg or {}).get("content")
                        if system_msg
                        else None,
                    },
                )

            response = await asyncio.to_thread(_call)
            success = True
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                self.record_token_usage(
                    getattr(usage, "prompt_token_count", 0) or 0,
                    getattr(usage, "candidates_token_count", 0) or 0,
                )
            return response.text or ""
        except Exception as e:
            return f"Error calling Gemini Model: {e}"
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
        image_path: str | None = None,
    ) -> T:
        # Use instructor's Gemini integration when available; otherwise fall back to
        # a JSON-mode prompt and tolerant parsing.
        try:
            import instructor  # type: ignore

            if hasattr(instructor, "from_genai"):
                client = instructor.from_genai(self._client)

                def _call():
                    return client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        response_model=response_model,
                        temperature=temperature,
                    )

                return await asyncio.to_thread(_call)
        except Exception as e:
            viki_logger.debug("Gemini structured via instructor failed: %s", e)

        text = await self.chat(
            messages
            + [
                {"role": "system", "content": "Return only a single JSON object."},
            ],
            temperature=temperature,
        )
        try:
            return response_model.model_validate_json(text)
        except Exception:
            # Last-ditch: extract first JSON object.
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                return response_model.model_validate_json(text[start : end + 1])
            raise

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        if not self.available or self._client is None:
            yield f"Error: Model '{self.model_name}' is unavailable."
            return
        try:
            system_msg = next((m for m in messages if m.get("role") == "system"), None)
            user_messages = [m for m in messages if m.get("role") != "system"]
            contents = self._to_contents(user_messages)

            def _stream():
                return self._client.models.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
                    config={
                        "temperature": temperature,
                        "system_instruction": (system_msg or {}).get("content")
                        if system_msg
                        else None,
                    },
                )

            stream = await asyncio.to_thread(_stream)
            for chunk in stream:
                txt = getattr(chunk, "text", None) or ""
                if txt:
                    yield txt
        except Exception as e:
            yield f"Error streaming Gemini Model: {e}"


# ---------------------------------------------------------------------------
# Groq (OpenAI-compatible API, AsyncOpenAI client with custom base_url)
# ---------------------------------------------------------------------------
class GroqLLM(LLMProvider):
    """Groq Cloud — OpenAI-compatible API, low-latency Llama/Mixtral inference."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.provider_name = "groq"
        api_key = os.getenv(self.config.get("api_key_env", "GROQ_API_KEY"))
        if not _looks_like_groq_secret(api_key):
            self.available = False
            self.unavailable_reason = (
                "Groq API key missing or invalid; expected GROQ_API_KEY starting with gsk_."
            )
            self._client = None
            return
        try:
            from openai import AsyncOpenAI  # type: ignore

            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=self.config.get("base_url", "https://api.groq.com/openai/v1"),
            )
        except ImportError as e:
            self.available = False
            self.unavailable_reason = f"openai client missing: {e}"
            self._client = None

    def is_cloud(self) -> bool:
        return True

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        if not self.available or self._client is None:
            return f"Error: Model '{self.model_name}' is unavailable."
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name, messages=messages, temperature=temperature
            )
            try:
                usage = getattr(response, "usage", None)
                if usage:
                    self.record_token_usage(
                        getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                    )
            except Exception:
                pass
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"Error calling Groq Model: {e}"

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str | None = None,
    ) -> T:
        try:
            import instructor  # type: ignore

            client = instructor.from_openai(self._client, mode=instructor.Mode.JSON)
            result: T = await client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_model=response_model,
                temperature=temperature,
            )
            return result
        except Exception as e:
            viki_logger.debug("Groq structured via instructor failed: %s", e)
            text = await self.chat(messages, temperature=temperature)
            return response_model.model_validate_json(text)

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        if not self.available or self._client is None:
            yield f"Error: Model '{self.model_name}' is unavailable."
            return
        try:
            stream = await self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                delta: str | None = None
                try:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                except Exception:
                    delta = None
                if delta:
                    yield delta
        except Exception as e:
            yield f"Error streaming Groq Model: {e}"


# ---------------------------------------------------------------------------
# Mistral (official mistralai SDK or OpenAI-compatible)
# ---------------------------------------------------------------------------
class MistralLLM(LLMProvider):
    """Mistral AI cloud (mistral-large, mistral-small)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.provider_name = "mistral"
        api_key = os.getenv(self.config.get("api_key_env", "MISTRAL_API_KEY"))
        if not _looks_like_mistral_secret(api_key):
            self.available = False
            self.unavailable_reason = "Mistral API key missing or invalid."
            self._client = None
            return
        try:
            from openai import AsyncOpenAI  # type: ignore

            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=self.config.get("base_url", "https://api.mistral.ai/v1"),
            )
        except ImportError as e:
            self.available = False
            self.unavailable_reason = f"openai client missing: {e}"
            self._client = None

    def is_cloud(self) -> bool:
        return True

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        if not self.available or self._client is None:
            return f"Error: Model '{self.model_name}' is unavailable."
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name, messages=messages, temperature=temperature
            )
            try:
                usage = getattr(response, "usage", None)
                if usage:
                    self.record_token_usage(
                        getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                    )
            except Exception:
                pass
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"Error calling Mistral Model: {e}"

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str | None = None,
    ) -> T:
        try:
            import instructor  # type: ignore

            client = instructor.from_openai(self._client, mode=instructor.Mode.JSON)
            result: T = await client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_model=response_model,
                temperature=temperature,
            )
            return result
        except Exception as e:
            viki_logger.debug("Mistral structured via instructor failed: %s", e)
            text = await self.chat(messages, temperature=temperature)
            return response_model.model_validate_json(text)

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        if not self.available or self._client is None:
            yield f"Error: Model '{self.model_name}' is unavailable."
            return
        try:
            stream = await self._client.chat.completions.create(
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
            yield f"Error streaming Mistral Model: {e}"


# ---------------------------------------------------------------------------
# NVIDIA NIM (OpenAI-compatible cloud inference)
# ---------------------------------------------------------------------------
class NvidiaLLM(LLMProvider):
    """NVIDIA NIM — OpenAI-compatible API for hosted frontier models.

    Supports chat, streaming, structured output, and (optionally) text
    embeddings when `embedding_model: true` is set in the profile config.

    API keys start with ``nvapi-`` and are obtained for free from
    https://build.nvidia.com.  The hosted base URL is
    ``https://integrate.api.nvidia.com/v1``.
    """

    _NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.provider_name = "nvidia_nim"
        self._client: Any = None
        self._is_embedding_model = bool(config.get("embedding_model", False))

        api_key = os.getenv(self.config.get("api_key_env", "NVIDIA_API_KEY"))
        if not self._looks_like_nvidia_secret(api_key):
            self.available = False
            self.unavailable_reason = (
                "NVIDIA NIM API key missing or invalid; expected NVIDIA_API_KEY "
                "starting with 'nvapi-'. Get a free key at https://build.nvidia.com."
            )
            return

        try:
            from openai import AsyncOpenAI  # type: ignore

            base_url = self.config.get("base_url", self._NIM_BASE_URL)
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            self._api_key = api_key
            viki_logger.debug(
                "NvidiaLLM initialised: model=%s base_url=%s", self.model_name, base_url
            )
        except ImportError as e:
            self.available = False
            self.unavailable_reason = f"openai client missing: {e}"
            self._client = None
        except Exception as e:
            self.available = False
            self.unavailable_reason = str(e)
            self._client = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_nvidia_secret(key: str | None) -> bool:
        if not key or not str(key).strip():
            return False
        s = str(key).strip()
        if s.lower() in ("none", "dummy", "placeholder", "test", "your-api-key-here", "changeme"):
            return False
        return s.startswith("nvapi-") and len(s) >= 20

    def _extra_body(self) -> dict[str, Any]:
        """Return any NIM-specific extra_body parameters from the profile config."""
        extra: dict[str, Any] = {}
        if "top_p" in self.config:
            extra["top_p"] = float(self.config["top_p"])
        if "max_tokens" in self.config:
            extra["max_tokens"] = int(self.config["max_tokens"])
        return extra

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def is_cloud(self) -> bool:
        return True

    # --- Embedding (only for embedding-model profiles) -----------------

    async def embed(self, texts: list[str], input_type: str = "query") -> list[list[float]]:
        """Return embeddings for *texts* using an NVIDIA NIM embedding model.

        Only works when the profile has ``embedding_model: true``.

        Args:
            texts: List of strings to embed.
            input_type: ``"query"`` for search queries (default), ``"passage"``
                for documents being indexed. Required by asymmetric NIM models.
        """
        if not self.available or self._client is None:
            raise RuntimeError(f"NvidiaLLM embedding model '{self.model_name}' is unavailable.")
        if not self._is_embedding_model:
            raise RuntimeError(
                f"Model '{self.model_name}' is not configured as an embedding model. "
                "Set 'embedding_model: true' in the model profile."
            )
        # Allow profile-level override of default input_type
        effective_input_type = self.config.get("embed_input_type", input_type)
        try:
            response = await self._client.embeddings.create(
                model=self.model_name,
                input=texts,
                encoding_format="float",
                extra_body={"input_type": effective_input_type, "truncate": "END"},
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            raise RuntimeError(f"NVIDIA NIM embedding failed: {e}") from e

    # --- Chat ----------------------------------------------------------

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        if not self.available or self._client is None:
            return f"Error: NVIDIA NIM model '{self.model_name}' is unavailable."
        t0 = time.perf_counter()
        success = False
        try:
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature,
            }
            extra = self._extra_body()
            if extra:
                kwargs["extra_body"] = extra

            response = await self._client.chat.completions.create(**kwargs)
            usage = getattr(response, "usage", None)
            if usage:
                self.record_token_usage(
                    getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                )
            success = True
            return response.choices[0].message.content or ""
        except Exception as e:
            viki_logger.error("NvidiaLLM.chat failed for '%s': %s", self.model_name, e)
            return f"Error calling NVIDIA NIM model '{self.model_name}': {e}"
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat")
            except Exception:
                pass

    # --- Structured output --------------------------------------------

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str | None = None,
    ) -> T:
        t0 = time.perf_counter()
        success = False
        try:
            import instructor  # type: ignore

            client = instructor.from_openai(self._client, mode=instructor.Mode.JSON)
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "response_model": response_model,
                "temperature": temperature,
            }
            extra = self._extra_body()
            if extra:
                kwargs["extra_body"] = extra

            result = await client.chat.completions.create(**kwargs)
            success = True
            return cast("T", result)
        except Exception as e:
            viki_logger.debug("NvidiaLLM structured via instructor failed: %s — falling back", e)
            # Fallback: plain chat + JSON parse
            text = await self.chat(
                messages + [{"role": "user", "content": "Return only a single JSON object."}],
                temperature=temperature,
            )
            try:
                result = response_model.model_validate_json(text)
                success = True
                return result
            except Exception:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1:
                    return response_model.model_validate_json(text[start : end + 1])
                raise
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat_structured")
            except Exception:
                pass

    # --- Streaming ----------------------------------------------------

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        if not self.available or self._client is None:
            yield f"Error: NVIDIA NIM model '{self.model_name}' is unavailable."
            return
        try:
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            }
            extra = self._extra_body()
            if extra:
                kwargs["extra_body"] = extra

            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                try:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                except Exception:
                    delta = None
                if delta:
                    yield delta
        except Exception as e:
            viki_logger.error("NvidiaLLM.chat_stream failed for '%s': %s", self.model_name, e)
            yield f"Error streaming NVIDIA NIM model '{self.model_name}': {e}"


# ---------------------------------------------------------------------------
# OpenCode — gateway to Zen and Go coding/reasoning models (GPT-5.5, Qwen, etc.)
# ---------------------------------------------------------------------------
class OpenCodeLLM(LLMProvider):
    """OpenCode API — access to Zen and Go optimized coding/reasoning models.

    OpenCode exposes OpenAI-compatible endpoints at:
    - OpenCode Zen: ``https://opencode.ai/zen/v1``
    - OpenCode Go: ``https://opencode.ai/zen/go/v1``

    API keys are obtained at https://opencode.ai and start with ``sk-``.
    Set ``OPENCODE_API_KEY`` in your environment.
    """

    _OC_BASE_URL = "https://opencode.ai/zen/v1"
    _OC_SITE_URL = "https://github.com/Orythix/viki"
    _OC_SITE_NAME = "VIKI"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.provider_name = "opencode"
        self._client: Any = None

        api_key = os.getenv(self.config.get("api_key_env", "OPENCODE_API_KEY"))
        if not self._looks_like_opencode_secret(api_key):
            self.available = False
            self.unavailable_reason = (
                "OpenCode API key missing or invalid; expected OPENCODE_API_KEY "
                "starting with 'sk-'. Get a key at https://opencode.ai."
            )
            return

        try:
            from openai import AsyncOpenAI  # type: ignore

            base_url = self.config.get("base_url", self._OC_BASE_URL)
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                default_headers={
                    "HTTP-Referer": self._OC_SITE_URL,
                    "X-Title": self._OC_SITE_NAME,
                },
            )
            viki_logger.debug(
                "OpenCodeLLM initialised: model=%s base_url=%s", self.model_name, base_url
            )
        except ImportError as e:
            self.available = False
            self.unavailable_reason = f"openai client missing: {e}"
            self._client = None
        except Exception as e:
            self.available = False
            self.unavailable_reason = str(e)
            self._client = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_opencode_secret(key: str | None) -> bool:
        if not key or not str(key).strip():
            return False
        s = str(key).strip()
        if s.lower() in ("none", "dummy", "placeholder", "test", "your-api-key-here", "changeme"):
            return False
        return s.startswith("sk-") and len(s) >= 20

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def is_cloud(self) -> bool:
        return True

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        if not self.available or self._client is None:
            return f"Error: OpenCode model '{self.model_name}' is unavailable."
        t0 = time.perf_counter()
        success = False
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
            )
            usage = getattr(response, "usage", None)
            if usage:
                self.record_token_usage(
                    getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                )
            success = True
            return response.choices[0].message.content or ""
        except Exception as e:
            viki_logger.error("OpenCodeLLM.chat failed for '%s': %s", self.model_name, e)
            return f"Error calling OpenCode model '{self.model_name}': {e}"
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
        image_path: str | None = None,
    ) -> T:
        t0 = time.perf_counter()
        success = False
        try:
            import instructor  # type: ignore

            client = instructor.from_openai(self._client, mode=instructor.Mode.JSON)
            result = await client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_model=response_model,
                temperature=temperature,
            )
            success = True
            return cast("T", result)
        except Exception as e:
            viki_logger.debug("OpenCodeLLM structured via instructor failed: %s — falling back", e)
            text = await self.chat(
                messages + [{"role": "user", "content": "Return only a single JSON object."}],
                temperature=temperature,
            )
            try:
                result = response_model.model_validate_json(text)
                success = True
                return result
            except Exception:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1:
                    return response_model.model_validate_json(text[start : end + 1])
                raise
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat_structured")
            except Exception:
                pass

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        if not self.available or self._client is None:
            yield f"Error: OpenCode model '{self.model_name}' is unavailable."
            return
        try:
            stream = await self._client.chat.completions.create(
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
            viki_logger.error("OpenCodeLLM.chat_stream failed for '%s': %s", self.model_name, e)
            yield f"Error streaming OpenCode model '{self.model_name}': {e}"


# ---------------------------------------------------------------------------
# Bedrock (AWS) — Claude / Llama / Mistral
# ---------------------------------------------------------------------------
class BedrockLLM(LLMProvider):
    """AWS Bedrock invocation via `boto3`."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.provider_name = "bedrock"
        self.region = config.get("region", os.getenv("AWS_REGION", "us-east-1"))
        try:
            import boto3  # type: ignore

            self._boto3 = boto3
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        except ImportError as e:
            self.available = False
            self.unavailable_reason = f"boto3 missing: {e}"
            self._client = None
        except Exception as e:
            self.available = False
            self.unavailable_reason = str(e)
            self._client = None

    def is_cloud(self) -> bool:
        return True

    @staticmethod
    def _to_anthropic_payload(messages: list[dict[str, Any]], temperature: float) -> dict[str, Any]:
        system = None
        msgs = []
        for m in messages:
            role = m.get("role")
            content = m.get("content")
            if role == "system":
                system = content
                continue
            msgs.append(
                {
                    "role": role if role in ("user", "assistant") else "user",
                    "content": [{"type": "text", "text": str(content)}],
                }
            )
        payload: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": msgs,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        return payload

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        if not self.available or self._client is None:
            return f"Error: Model '{self.model_name}' is unavailable."
        try:
            body = json.dumps(self._to_anthropic_payload(messages, temperature))

            def _invoke():
                return self._client.invoke_model(
                    modelId=self.model_name,
                    body=body,
                    contentType="application/json",
                    accept="application/json",
                )

            response = await asyncio.to_thread(_invoke)
            payload = json.loads(response["body"].read())
            try:
                usage = payload.get("usage") or {}
                self.record_token_usage(
                    int(usage.get("input_tokens", 0) or 0),
                    int(usage.get("output_tokens", 0) or 0),
                )
            except Exception:
                pass
            content = payload.get("content") or []
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    return first.get("text") or ""
            return payload.get("output_text") or ""
        except Exception as e:
            return f"Error calling Bedrock Model: {e}"

    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str | None = None,
    ) -> T:
        text = await self.chat(messages, temperature=temperature)
        return response_model.model_validate_json(text)

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.7):
        # Bedrock streaming via invoke_model_with_response_stream — defer to chat for now.
        result = await self.chat(messages, temperature=temperature)
        if result:
            yield result
