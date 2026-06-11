import uuid
from dataclasses import dataclass, field
from enum import Enum


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass
class SubAgent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "SubAgent"
    specialty: str = "general"
    status: AgentStatus = AgentStatus.IDLE
    current_task: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SwarmTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    assigned_to: str | None = None
    status: str = "pending"
    result: str | None = None
