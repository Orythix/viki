"""
Application configuration.

Security notes:
- LAB_API_KEY must be set in any shared or long-lived deployment (use secrets manager in real env).
- OLLAMA_URL must point to localhost or lab-internal Docker network only.
- TOOL_ALLOWLIST limits shell tool to explicit binaries (defense in depth; real isolation = Docker).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECURITY_LAB_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Security Learning Lab"
    debug: bool = Field(default=False, description="Never enable in a shared network")

    lab_api_key: str = Field(default="dev-lab-change-me", alias="LAB_API_KEY")
    database_url: str = Field(default="sqlite:///./data/lab_audit.db", alias="DATABASE_URL")

    ollama_url: str = Field(default="http://host.docker.internal:11434", alias="OLLAMA_URL")
    ollama_model: str = Field(default="llama3.2:latest", alias="OLLAMA_MODEL")

    rate_limit_per_minute: int = Field(default=60, ge=1, alias="RATE_LIMIT_PER_MINUTE")
    max_prompt_chars: int = Field(default=16_384, ge=256)
    max_output_chars: int = Field(default=32_768, ge=1024)

    # Comma-separated allowlist for subprocess tool (basename only)
    tool_allowlist: str = Field(default="python,echo,whoami", alias="TOOL_ALLOWLIST")

    rbac_policy_path: str = Field(
        default_factory=lambda: str(_SECURITY_LAB_ROOT / "security" / "policies" / "rbac.json"),
        alias="RBAC_POLICY_PATH",
    )

    @property
    def tool_allowlist_set(self) -> set[str]:
        return {x.strip().lower() for x in self.tool_allowlist.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
