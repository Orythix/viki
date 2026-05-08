"""
Central configuration from environment variables.

Why env vars: CI injects secrets; local dev uses .env (never committed).
Security: never log raw API keys; rotate keys used in shared environments.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    role: str = "lab_admin"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            base_url=os.environ.get("QA_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            api_key=os.environ.get("QA_API_KEY", "dev-lab-change-me"),
            role=os.environ.get("QA_LAB_ROLE", "lab_admin"),
        )
