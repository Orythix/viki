import os
import json
import re
import yaml
import asyncio
import aiohttp
import instructor
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Type, TypeVar
from pydantic import BaseModel
from openai import AsyncOpenAI
from viki.core.schema import VIKIResponse, VIKIResponseLite, ThoughtObject, ThoughtObjectLite
from viki.config.logger import viki_logger

T = TypeVar("T", bound=BaseModel)

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

    def record_performance(self, latency: float, success: bool):
        self.call_count += 1
        n = self.call_count
        self.avg_latency = ((self.avg_latency * (n-1)) + latency) / n
        
        if not success:
            self.error_count += 1
            self.trust_score = max(0.0, self.trust_score - 0.1)
        else:
            self.trust_score = min(1.0, self.trust_score + 0.01)

    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """Send a asynchronous chat request to the LLM."""
        pass

    @abstractmethod
    async def chat_structured(self, messages: List[Dict[str, str]], response_model: Type[T], temperature: float = 0.0) -> T:
        """Send a structured chat request returning a Pydantic model."""
        pass

class MockLLM(LLMProvider):
    """Mock LLM for testing and development."""
    
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        await asyncio.sleep(0.1) # Simulate network
        return "Mock response for " + self.model_name

    async def chat_structured(self, messages: List[Dict[str, str]], response_model: Type[T], temperature: float = 0.0) -> T:
        await asyncio.sleep(0.1)
        if response_model == VIKIResponse:
            return VIKIResponse(
                final_thought=ThoughtObject(intent_summary="Mock", primary_strategy="Mock response", confidence=1.0),
                final_response="This is a mock response because I'm in testing mode."
            )
        if response_model == VIKIResponseLite:
            return VIKIResponseLite(final_response="This is a mock response.", confidence=1.0)
        return response_model()

class APILLM(LLMProvider):
    """OpenAI-compatible API provider with Instructor support."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        self.provider_type = config.get("provider", "openai")
        api_key = os.getenv(self.config.get("api_key_env", "OPENAI_API_KEY"))
        
        try:
            if self.provider_type == "anthropic":
                from anthropic import AsyncAnthropic
                if not api_key:
                    raise ValueError(f"API key for Anthropic is missing ({self.config.get('api_key_env')})")
                self.client = instructor.from_anthropic(
                    AsyncAnthropic(api_key=api_key),
                    mode=instructor.Mode.ANTHROPIC_JSON
                )
            else:
                base_url = self.config.get('base_url', 'https://api.openai.com/v1')
                if not api_key and "openai.com" in base_url:
                     raise ValueError(f"API key for OpenAI is missing ({self.config.get('api_key_env')})")
                
                self.client = instructor.from_openai(
                    AsyncOpenAI(api_key=api_key, base_url=base_url),
                    mode=instructor.Mode.JSON
                )
        except Exception as e:
            viki_logger.warning(f"Model '{self.model_name}' (provider: {self.provider_type}) disabled: {e}")
            self.client = None
            self.available = False

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, image_path: str = None) -> str:
        if not self.available:
            return f"Error: Model '{self.model_name}' is unavailable (likely due to missing API key)."
        try:
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
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                        break

            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error calling API Model: {str(e)}"

    async def chat_structured(self, messages: List[Dict[str, str]], response_model: Type[T], temperature: float = 0.0, image_path: str = None) -> T:
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
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                    break

        return await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            response_model=response_model,
            temperature=temperature
        )

class LocalLLM(LLMProvider):
    """Ollama provider with Async support and JSON mode."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = self.config.get('base_url', 'http://127.0.0.1:11434').rstrip('/')
        if 'localhost' in self.base_url:
            self.base_url = self.base_url.replace('localhost', '127.0.0.1')

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, format: str = None, image_path: str = None, tools: List[Dict[str, Any]] = None) -> str:
        data = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature}
        }
        if format:
            data["format"] = format
        
        if tools:
            data["tools"] = tools
            data["stream"] = False # Tools require non-streaming for now
        
        if image_path:
            import base64
            # Use asyncio.to_thread for file I/O
            def read_image():
                with open(image_path, "rb") as image_file:
                    return base64.b64encode(image_file.read()).decode('utf-8')
            
            base64_image = await asyncio.to_thread(read_image)
            for i in range(len(messages) - 1, -1, -1):
                if messages[i]['role'] == 'user':
                    messages[i]["images"] = [base64_image]
                    break

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{self.base_url}/api/chat", json=data, timeout=120) as resp:
                    if resp.status == 404:
                        return f"Error: Model '{self.model_name}' not found."
                    resp_json = await resp.json()
                    
                    # Handle Tool Calls
                    if resp_json['message'].get('tool_calls'):
                        # Return the first tool call as a special string or handle it
                        # For now, let's just serialize it so the caller can parse it
                        return json.dumps({"tool_calls": resp_json['message']['tool_calls']})
                        
                    return resp_json['message']['content']
            except Exception as e:
                return f"Error calling Local Model: {str(e)}"

    async def chat_with_tools(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]], temperature: float = 0.0) -> Dict[str, Any]:
        """Specific method for tool use that returns the full message object (content + tool_calls)."""
        data = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
            "tools": tools
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

                    if 'error' in resp_json:
                        raise ValueError(f"Ollama Error: {resp_json['error']}")
                        
                    if 'message' not in resp_json:
                         raise ValueError(f"Missing 'message' in response: {resp_json}")

                    return resp_json['message'] 
            except Exception as e:
                viki_logger.error(f"Tool call failed: {e}")
                return {"role": "assistant", "content": f"Ollama Error: {str(e)}"}

    async def chat_structured(self, messages: List[Dict[str, str]], response_model: Type[T], temperature: float = 0.0, image_path: str = None) -> T:
        """Parse structured output from local Ollama models with heuristic patching."""
        
        # 0. Inject Schema for guidance
        try:
            schema = response_model.model_json_schema()
            # More forceful instruction for local models
            instruction = (
                f"### JSON OUTPUT RULE ###\n"
                f"Return ONLY a single, valid JSON object matching this structure. "
                f"No explanations, no markdown code blocks, and no extra text.\n"
                f"SCHEMA: {json.dumps(schema)}"
            )
            
            messages.append({"role": "system", "content": instruction})
        except Exception as e:
            viki_logger.debug(f"Failed to inject schema: {e}")

        # 1. Get raw JSON from model
        content = await self.chat(messages, temperature=temperature, format="json", image_path=image_path)
        viki_logger.debug(f"DEBUG: Raw response from {self.config.get('model_name')}: {content}")
        
        # 2. Parse and patch
        try:
            # Strip markdown code blocks
            import re
            match = re.search(r"```(?:json)?\s*({.*})\s*```", content, re.DOTALL)
            if match:
                content = match.group(1).strip()
            else:
                content = content.replace("```json", "").replace("```", "").strip()

            # Fix Python/JSON mismatch (common with local models)
            content = content.replace(": None", ": null").replace(": True", ": true").replace(": False", ": false")
            
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Last resort: Try replacing single quotes if double quotes are missing in keys
                if "'" in content and '"' not in content[:10]: # Heuristic check
                     content = content.replace("'", '"')
                     data = json.loads(content)
                else:
                     raise
            
            # --- HEURISTIC PATCHES (only for VIKIResponse, not for Lite) ---
            if response_model == VIKIResponse:
                data = self._patch_viki_response(data)
            
            content = json.dumps(data)
            return response_model.model_validate_json(content)
            
        except Exception as e:
            viki_logger.warning(f"Structured parse failed for {response_model.__name__}: {e}")
            
            # Graceful fallback
            if response_model == VIKIResponseLite:
                fallback_text = self._extract_text(content)
                return VIKIResponseLite(final_response=fallback_text, confidence=0.4)
            
            if response_model == VIKIResponse:
                fallback_text = self._extract_text(content)
                return VIKIResponse(
                    final_thought=ThoughtObject(
                        intent_summary="Response recovery",
                        primary_strategy="Deliver available response despite format mismatch",
                        confidence=0.5
                    ),
                    final_response=fallback_text
                )
            raise ValueError(f"Failed to parse structured output: {e}\nContent: {content}")

    def _extract_text(self, content: str) -> str:
        """Try to extract useful text from a failed parse."""
        fallback = "I encountered a parsing issue. Could you rephrase that?"
        try:
            raw = json.loads(content) if isinstance(content, str) else {}
            if isinstance(raw, dict):
                # Try common keys
                for key in ["final_response", "response", "message", "text", "content", "answer"]:
                    if key in raw and isinstance(raw[key], str):
                        return raw[key]
        except (json.JSONDecodeError, TypeError) as e:
            viki_logger.debug(f"Failed to extract text from content: {e}")
        return fallback

    def _patch_viki_response(self, data: dict) -> dict:
        """Apply heuristic patches for common local LLM schema errors.
        These handle the various ways models mangle the VIKIResponse schema."""
        
        # PATCH: Schema Echo — model returned the schema definition instead of data
        # Check for multiple schema indicators to avoid false positives
        if all(k in data for k in ["properties", "type", "required"]) and data.get("type") == "object":
            return {
                "final_thought": {
                    "intent_summary": "Model Error (Schema Echo)",
                    "primary_strategy": "Retry with simpler constraints",
                    "confidence": 0.0,
                },
                "final_response": "Internal Error: The local model echoed the schema instead of answering. Try again or switch models."
            }

        # PATCH: "response/plan" format
        if "response" in data and "plan" in data and "final_thought" not in data:
            intent = data["response"].get("intent", "unknown") if isinstance(data["response"], dict) else str(data["response"])
            plan = str(data.get("plan", []))
            return {
                "final_thought": {"intent_summary": intent, "primary_strategy": plan, "confidence": 0.8},
                "action": data.get("action"),
                "final_response": data.get("final_response", f"Plan: {plan}")
            }

        # PATCH: ThoughtObject at root level
        if "ThoughtObject" in data and "final_thought" not in data:
            data["final_thought"] = data.pop("ThoughtObject")

        # PATCH: Flattened ThoughtObject (all fields at root)
        if "intent_summary" in data and "primary_strategy" in data and "final_thought" not in data:
            thought_fields = ["intent_vector", "intent_summary", "assumptions", "constraints", 
                            "risk_score", "primary_strategy", "rejected_strategies", 
                            "symbolic_graph", "confidence", "provenance"]
            thought_obj = {}
            for f in thought_fields:
                if f in data:
                    thought_obj[f] = data.pop(f)
            data["final_thought"] = thought_obj

        # PATCH: Action as string instead of object
        if "action" in data and isinstance(data["action"], str):
            data["action"] = {"skill_name": data["action"], "parameters": {}}
        elif "action" in data and isinstance(data["action"], dict):
            if "parameters" not in data["action"]:
                data["action"]["parameters"] = {}

        # PATCH: Flattened action (skill_name + parameters at root)
        if "skill_name" in data and "parameters" in data and "action" not in data:
            data["action"] = {"skill_name": data.pop("skill_name"), "parameters": data.pop("parameters")}

        # PATCH: Missing final_thought — synthesize from available data
        if "final_thought" not in data:
            summary = data.get("final_response", "Request received, formulating response...")
            strategy = data.get("internal_metacognition", summary)
            data["final_thought"] = {
                "intent_summary": summary[:200] if isinstance(summary, str) else "User request",
                "primary_strategy": strategy[:200] if isinstance(strategy, str) else "Direct response",
                "confidence": 0.7,
            }

        return data

class ModelFactory:
    @staticmethod
    def create(profile_name: str, profile_config: Dict[str, Any], provider_config: Dict[str, Any]) -> LLMProvider:
        provider_type = provider_config.get("type", "mock")
        merged_config = {**provider_config, **profile_config}
        
        if provider_type == "mock":
            return MockLLM(merged_config)
        elif provider_type == "api":
            return APILLM(merged_config)
        elif provider_type == "anthropic":
            # Instructor handles Anthropic via the same interface if configured
            merged_config['type'] = 'api' 
            return APILLM(merged_config)
        elif provider_type == "local":
            return LocalLLM(merged_config)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

class ModelRouter:
    def __init__(self, config_path: str, air_gap: bool = False):
        self.models = {}
        self.default_model = None
        self.air_gap = air_gap
        self._load_config(config_path)

        
    def _load_config(self, path: str):
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
                
            providers = config.get('models', {}).get('providers', {})
            profiles = config.get('models', {}).get('profiles', {})
            default_profile = config.get('models', {}).get('default', 'mock-model')

            for name, profile in profiles.items():
                provider_name = profile.get('provider')
                if provider_name in providers:
                    provider_conf = providers[provider_name]
                    self.models[name] = ModelFactory.create(name, profile, provider_conf)
            
            if default_profile in self.models:
                self.default_model = self.models[default_profile]
            elif self.models:
                self.default_model = list(self.models.values())[0]
            else:
                 self.default_model = MockLLM({'model_name': 'fallback-mock'})
                 
        except (yaml.YAMLError, IOError, FileNotFoundError, KeyError) as e:
            viki_logger.error(f"Failed to load model config from {path}: {e}")
            self.default_model = MockLLM({'model_name': 'error-fallback'})

    def get_model(self, capabilities: List[str] = None) -> LLMProvider:
        if not capabilities:
            return self.default_model
            
        best_candidate = None
        best_score = -1
        
        for model in self.models.values():
            if not model.available:
                continue
            if self.air_gap and not isinstance(model, LocalLLM):
                continue # Skip non-local if in air-gap mode

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
        
        return best_candidate or self.default_model
