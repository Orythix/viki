from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import uuid

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
    current_task: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

@dataclass
class SwarmTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    assigned_to: Optional[str] = None
    status: str = "pending"
    result: Optional[str] = None
