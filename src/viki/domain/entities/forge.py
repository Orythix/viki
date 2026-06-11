from dataclasses import dataclass, field


@dataclass
class ForgeProfile:
    name: str
    base_model: str
    target_tag: str
    knowledge_topics: list[str] = field(default_factory=list)
    system_instruction_override: str | None = None
    parameters: dict = field(default_factory=lambda: {"temperature": 0.6})
    is_cloud: bool = False
    cloud_provider: str | None = None  # e.g., 'openai', 'anthropic'


@dataclass
class ForgeStatus:
    active_profile: str
    last_bake_time: float
    total_profiles: int
