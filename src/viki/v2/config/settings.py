"""v2 settings."""

from dataclasses import dataclass, field


@dataclass
class Settings:
    tool_timeout: int = 30
    admin_confirmation_timeout: int = 120
    max_tool_retries: int = 2
    session_ttl_minutes: int = 60
    enable_audit_log: bool = True
    providers: dict = field(
        default_factory=lambda: {
            "windows": {"enabled": True},
            "linux": {"enabled": True},
            "mac": {"enabled": False},
        }
    )
