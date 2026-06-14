"""Configuration system for the Public Safety Skills Framework."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SafetyConfig:
    """Configuration for the entire public safety framework."""

    # --- Core ---
    data_dir: str = field(
        default_factory=lambda: os.environ.get(
            "VIKI_SAFETY_DATA_DIR",
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "data", "safety"
            ),
        )
    )
    auto_learning: bool = True
    audit_logging: bool = True
    memory_enabled: bool = True

    # --- LLM ---
    model: str = field(default_factory=lambda: os.environ.get("VIKI_SAFETY_MODEL", "llama3.1:8b"))
    llm_host: str = field(
        default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    )
    temperature: float = 0.1
    max_tokens: int = 512

    # --- Safety ---
    enable_ai_threat_detection: bool = True
    enable_cyber_defense: bool = True
    enable_infrastructure_monitor: bool = True
    max_evidence_items: int = 100
    max_threat_memories: int = 10000

    # --- Agent coordination ---
    agent_timeout_seconds: float = 30.0
    max_concurrent_agents: int = 5

    # --- NL Bridge ---
    bridge_auto_retry: bool = True
    bridge_max_retries: int = 2
    bridge_fallback_to_json: bool = True

    # --- Audit ---
    audit_retention_days: int = 90
    audit_pii_redaction: bool = True

    # --- Memory ---
    short_term_ttl_seconds: float = 3600.0
    working_memory_limit: int = 50
    long_term_limit: int = 5000

    @classmethod
    def from_env(cls) -> SafetyConfig:
        """Load configuration from environment variables with sensible defaults."""
        return cls(
            auto_learning=os.environ.get("VIKI_SAFETY_AUTO_LEARN", "1").lower()
            in ("1", "true", "yes"),
            audit_logging=os.environ.get("VIKI_SAFETY_AUDIT", "1").lower() in ("1", "true", "yes"),
            model=os.environ.get("VIKI_SAFETY_MODEL", os.environ.get("VIKI_MODEL", "llama3.1:8b")),
            temperature=float(os.environ.get("VIKI_SAFETY_TEMPERATURE", "0.1")),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for f in self.__dataclass_fields__.values():
            result[f.name] = getattr(self, f.name)
        return result
