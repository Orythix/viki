"""Layer 2: Entity Extraction & Intent Classification."""

from __future__ import annotations

import os
import re
from typing import Any

from viki.config.logger import viki_logger

from .cortex_layer import CortexLayer


class InterpretationLayer(CortexLayer):
    """Layer 2: Entity Extraction & Intent Classification."""

    COMMAND_KEYWORDS = {"open", "launch", "start", "run", "execute", "close", "kill", "stop"}
    MEDIA_KEYWORDS = {
        "play",
        "pause",
        "resume",
        "skip",
        "next",
        "previous",
        "mute",
        "unmute",
        "volume",
    }
    CLOUD_KEYWORDS = {
        "aws",
        "ec2",
        "s3",
        "lambda",
        "k8s",
        "kubernetes",
        "docker",
        "terraform",
        "cloud",
        "instance",
        "bucket",
        "cluster",
    }
    DEVOPS_KEYWORDS = {
        "git",
        "npm",
        "pip",
        "pytest",
        "test",
        "build",
        "deploy",
        "jenkins",
        "ci",
        "cd",
        "commit",
        "branch",
        "push",
        "pull",
        "merge",
    }
    SYSTEM_KEYWORDS = {
        "df",
        "ps",
        "top",
        "free",
        "mem",
        "cpu",
        "disk",
        "uptime",
        "whoami",
        "hostname",
        "ip",
        "netstat",
        "memory",
        "storage",
        "network",
        "wifi",
        "password",
        "wireless",
    }
    DATA_KEYWORDS = {
        "sqlite",
        "redis",
        "db",
        "sql",
        "table",
        "data",
        "database",
        "query",
        "select",
        "insert",
        "update",
        "delete",
    }
    AI_KEYWORDS = {
        "nvidia",
        "gpu",
        "cuda",
        "torch",
        "pytorch",
        "tensorflow",
        "ollama",
        "transformers",
        "huggingface",
        "model",
        "inference",
        "train",
    }
    PROD_KEYWORDS = {
        "calendar",
        "todo",
        "task",
        "note",
        "notes",
        "agenda",
        "weather",
        "price",
        "crypto",
        "bitcoin",
        "productivity",
    }
    QUESTION_KEYWORDS = {
        "what",
        "who",
        "where",
        "when",
        "why",
        "how",
        "which",
        "is",
        "are",
        "can",
        "do",
        "does",
    }
    CODE_KEYWORDS = {
        "code",
        "function",
        "class",
        "debug",
        "fix",
        "implement",
        "write",
        "create",
        "build",
        "compile",
    }
    RESEARCH_KEYWORDS = {"search", "find", "look up", "google", "research", "tell me about"}
    CORRECTION_KEYWORDS = {
        "wrong",
        "incorrect",
        "correction",
        "fix",
        "not",
        "actually",
        "mistake",
        "error",
    }

    async def _logic(self, data: str) -> dict[str, Any]:
        viki_logger.debug("Layer 2 (Interpretation) resolving human intent...")

        urls = re.findall(r'https?://[^\s<>"]+', data)
        file_paths = re.findall(r'(?:[A-Z]:\\|\.?/)[^\s<>"]+\.\w{1,5}', data)
        numbers = re.findall(r"\b\d+\.?\d*\b", data)
        quoted_strings = re.findall(r'"([^"]*)"', data) + re.findall(r"'([^']*)'", data)

        resolved_entities = {"paths": []}
        if hasattr(self, "world_model") and self.world_model:
            for path, purpose in self.world_model.state.semantic_paths.items():
                if (
                    purpose.lower() in data.lower()
                    or os.path.basename(path).lower() in data.lower()
                ):
                    resolved_entities["paths"].append({"path": path, "purpose": purpose})

        app_match = re.match(r"^(?:open|launch|start|run)\s+(.+)$", data.lower().strip())
        app_name = app_match.group(1).strip() if app_match else None

        words = set(data.lower().split())
        intent_type = self._classify_intent(words, data)

        if intent_type == "coding" and not file_paths:
            if any(ref in data.lower() for ref in ["this file", "the code", "the function"]):
                pass

        sentiment = self._detect_sentiment(data, words)

        context = {
            "raw_input": data,
            "entities": {
                "urls": urls,
                "file_paths": file_paths,
                "numbers": numbers,
                "quoted_strings": quoted_strings,
                "app_name": app_name,
                "resolved": resolved_entities,
            },
            "intent_type": intent_type,
            "sentiment": sentiment,
            "recommended_capabilities": self._get_capabilities(intent_type),
        }

        viki_logger.info(
            f"Layer 2 Discovery: intent={intent_type} | resolved={len(resolved_entities['paths'])} paths | sentiment={sentiment}"
        )
        return context

    def _classify_intent(self, words: set, raw: str) -> str:
        raw_lower = raw.lower().strip()
        if re.search(
            r"(who\s+are\s+you|what\s+are\s+you|tell\s+me\s+about\s+(yourself|you(\s+viki)?)|"
            r"about\s+yourself|introduce\s+yourself|describe\s+yourself)",
            raw_lower,
        ):
            return "conversation"
        if words & self.MEDIA_KEYWORDS:
            return "media_control"
        if words & self.CLOUD_KEYWORDS:
            return "cloud"
        if words & self.DEVOPS_KEYWORDS:
            return "devops"
        if words & self.SYSTEM_KEYWORDS:
            return "system"
        if words & self.DATA_KEYWORDS:
            return "data"
        if words & self.AI_KEYWORDS:
            return "ai"
        if words & self.PROD_KEYWORDS:
            return "productivity"
        if words & self.COMMAND_KEYWORDS:
            return "system_command"
        if words & self.CODE_KEYWORDS:
            return "coding"
        if words & self.CORRECTION_KEYWORDS and (
            "previous" in raw.lower() or "wrong" in raw.lower() or "not" in raw.lower()
        ):
            return "correction"
        if words & self.RESEARCH_KEYWORDS or re.search(r"https?://", raw):
            return "research"
        if raw.rstrip().endswith("?") or (words & self.QUESTION_KEYWORDS and len(words) < 20):
            return "question"
        return "conversation"

    def _detect_sentiment(self, raw: str, words: set) -> str:
        urgent_markers = {"urgent", "asap", "now", "immediately", "hurry", "quick", "fast"}
        frustration_markers = {"again", "still", "broken", "wrong", "failed"}

        if words & urgent_markers or raw.endswith(("!!!", "!!")):
            return "urgent"
        if words & frustration_markers:
            return "frustrated"
        if "not working" in raw.lower() or "doesn't work" in raw.lower():
            return "frustrated"
        if raw.rstrip().endswith("?"):
            return "curious"
        return "neutral"

    def _get_capabilities(self, intent_type: str) -> list[str]:
        mapping = {
            "media_control": ["fast_response"],
            "system_command": ["fast_response"],
            "coding": ["coding", "reasoning"],
            "research": ["researching", "reasoning"],
            "question": ["reasoning", "general"],
            "conversation": ["general", "chatter"],
            "cloud": ["cloud", "reasoning"],
            "devops": ["devops", "coding"],
            "system": ["system", "system_command", "fast_response"],
            "data": ["data", "reasoning"],
            "ai": ["ai", "reasoning"],
            "productivity": ["productivity", "fast_response"],
        }
        return mapping.get(intent_type, ["general"])
