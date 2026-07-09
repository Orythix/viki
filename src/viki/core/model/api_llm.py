"""OpenAI-compatible API provider with Instructor support."""

from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any, cast

from viki.config.logger import viki_logger

from .llm_provider import LLMProvider
from .utils import looks_like_anthropic_secret, looks_like_openai_secret

T = Any


class APILLM(LLMProvider):
    """OpenAI-compatible API provider with Instructor support."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.client: Any = None
        self.provider_type = config.get("provider", "openai")
        api_key = os.getenv(self.config.get("api_key_env", "OPENAI_API_KEY"))

        try:
            import instructor

            if self.provider_type == "anthropic":
                from anthropic import AsyncAnthropic

                if not looks_like_anthropic_secret(api_key):
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
                if uses_official_openai and not looks_like_openai_secret(api_key):
                    raise ValueError(
                        f"OpenAI API key missing or invalid ({self.config.get('api_key_env', 'OPENAI_API_KEY')}). "
                        "Official OpenAI expects a secret starting with sk-. "
                        "Unset OPENAI_API_KEY or set system.local_llm_only: true to use Ollama only."
                    )
                if not api_key and not uses_official_openai:
                    api_key = "not-needed"

                self.client = instructor.from_openai(
                    AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url),
                    mode=instructor.Mode.JSON,
                )
        except ImportError as e:
            viki_logger.warning(
                f"Model '{self.model_name}' (provider: {self.provider_type}) disabled: "
                f"optional API dependency missing or broken: {e}"
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
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        image_path: str | None = None,
    ) -> str:
        t0 = time.perf_counter()
        success = False
        try:
            if not self.available:
                return f"Error: Model '{self.model_name}' is unavailable (likely due to missing API key)."
            if image_path:

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
                viki_logger.warning("failed to record token usage for %s", self.model_name)
            success = True
            return cast("str", response.choices[0].message.content)
        except Exception as e:
            viki_logger.error("APILLM.chat failed for '%s': %s", self.model_name, e)
            return f"Error calling API Model '{self.model_name}'. Check logs for details."
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat")
            except Exception:
                viki_logger.warning("failed to emit LLM inference usage for %s", self.model_name)

    async def chat_structured(
        self,
        messages: list[dict[str, Any]],
        response_model: type[T],
        temperature: float = 0.0,
        image_path: str | None = None,
    ) -> T:
        t0 = time.perf_counter()
        success = False
        try:
            if not self.available:
                raise ValueError(f"Model '{self.model_name}' is unavailable.")
            if image_path:

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
                viki_logger.warning("failed to record token usage for %s", self.model_name)
            success = True
            return out
        finally:
            try:
                from viki.core.usage_log import emit_llm_inference

                emit_llm_inference(self, time.perf_counter() - t0, success, "chat_structured")
            except Exception:
                viki_logger.warning("failed to emit LLM inference usage for %s", self.model_name)

    async def chat_stream(self, messages: list[dict[str, Any]], temperature: float = 0.7):
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
