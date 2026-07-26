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
        # Plain (non-instructor) client for unstructured chat()/chat_stream():
        # instructor's wrapped `create()` requires a `response_model` on every
        # call, so it can't be reused for the plain-text path.
        self._raw_client: Any = None
        self.base_url: str | None = None
        self._instructor_unsupported: bool = False
        self.provider_type = config.get("provider", "openai")
        api_key = os.getenv(self.config.get("api_key_env", "OPENAI_API_KEY"))

        try:
            import instructor

            if self.provider_type == "anthropic":
                from anthropic import AsyncAnthropic

                if not looks_like_anthropic_secret(api_key):
                    raise ValueError(
                        f"Anthropic API key missing or invalid ({self.config.get('api_key_env', 'ANTHROPIC_API_KEY')}). "
                        "Expected a key starting with sk-ant-. Remove placeholder values or use local LM Studio profiles."
                    )
                self._raw_client = AsyncAnthropic(api_key=api_key)
                self.client = instructor.from_anthropic(
                    AsyncAnthropic(api_key=api_key), mode=instructor.Mode.ANTHROPIC_JSON
                )
            else:
                from openai import AsyncOpenAI

                base_url = self.config.get("base_url", "https://api.openai.com/v1")
                self.base_url = base_url
                uses_official_openai = "api.openai.com" in (base_url or "")
                if uses_official_openai and not looks_like_openai_secret(api_key):
                    raise ValueError(
                        f"OpenAI API key missing or invalid ({self.config.get('api_key_env', 'OPENAI_API_KEY')}). "
                        "Official OpenAI expects a secret starting with sk-. "
                        "Unset OPENAI_API_KEY or set system.local_llm_only: true to use LM Studio only."
                    )
                if not api_key and not uses_official_openai:
                    api_key = "not-needed"

                self._raw_client = AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url)
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
            self._raw_client = None
            self.available = False
            self.unavailable_reason = f"optional dependency missing or broken: {e}"
        except Exception as e:
            viki_logger.warning(
                f"Model '{self.model_name}' (provider: {self.provider_type}) disabled: {e}"
            )
            self.client = None
            self._raw_client = None
            self.available = False
            self.unavailable_reason = str(e)

    def is_cloud(self) -> bool:
        """A profile pointed at a local OpenAI-compatible server (e.g. LM Studio,
        text-generation-webui, vLLM) is not a cloud call — budget tracking,
        air_gap, and local_llm_only exclusions shouldn't apply to it."""
        host = (self.base_url or "").lower()
        if not host:
            return True
        return not (
            "127.0.0.1" in host
            or "localhost" in host
            or "0.0.0.0" in host
            or host.startswith("http://host.docker.internal")
        )

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

            response = await self._raw_client.chat.completions.create(
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

            try:
                if self._instructor_unsupported:
                    raise ValueError("skip_instructor")
                out, completion = await self.client.chat.completions.create_with_completion(
                    model=self.model_name,
                    messages=messages,
                    response_model=response_model,
                    temperature=temperature,
                )
            except Exception as instructor_err:
                err_str = str(instructor_err).lower()
                if (
                    self._instructor_unsupported
                    or "response_format" in err_str
                    or "json_schema" in err_str
                    or "json_object" in err_str
                    or "skip_instructor" in err_str
                ):
                    if not self._instructor_unsupported:
                        self._instructor_unsupported = True
                        viki_logger.info(
                            "Instructor structured output not supported by %s; using prompt-based fallback",
                            self.model_name,
                        )
                    out = await self._prompt_based_structured(messages, response_model, temperature)
                else:
                    raise
            try:
                usage = getattr(completion, "usage", None) if "completion" in dir() else None
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

    async def _prompt_based_structured(
        self, messages: list[dict[str, Any]], response_model: type[T], temperature: float
    ) -> T:
        """Fallback: ask the model to return JSON via prompt, then parse heuristically."""
        import json as _json

        from pydantic import TypeAdapter

        schema = response_model.model_json_schema()
        guide = (
            f"### JSON OUTPUT (required) ###\n"
            f"Return one JSON object matching this schema: {_json.dumps(schema)}\n"
            "No markdown fences, no explanation — just the raw JSON object."
        )
        augmented = list(messages) + [{"role": "system", "content": guide}]
        raw = await self.chat(augmented, temperature=temperature)
        raw = (raw if isinstance(raw, str) else str(raw or "")).strip()
        raw = raw.removeprefix("```json").removesuffix("```").strip()
        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError:
            import ast

            try:
                data = ast.literal_eval(raw)
            except Exception:
                viki_logger.warning("Prompt-based structured parse failed for %s", response_model.__name__)
                return TypeAdapter(response_model).validate_python(
                    {"final_thought": {"intent_summary": "error", "primary_strategy": "parse failure", "confidence": 0.0},
                     "final_response": raw[:4000] if len(raw) > 4000 else raw}
                )
        return response_model.model_validate_json(_json.dumps(data))

    async def chat_stream(self, messages: list[dict[str, Any]], temperature: float = 0.7):
        if not self.available or self._raw_client is None:
            yield f"Error: Model '{self.model_name}' is unavailable."
            return
        try:
            stream = await self._raw_client.chat.completions.create(
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
