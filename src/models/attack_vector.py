from enum import Enum
from typing import TypedDict

class AttackVector(str, Enum):
    """Defines the structured taxonomy of adversarial attacks."""
    PROMPT_INJECTION = "Prompt Injection"
    CONTEXT_OVERLOAD = "Context Overload"
    ROLE_PLAYING_JAILBREAK = "Role-Playing Jailbreak"
    DATA_EXFILTRATION = "Data Exfiltration"
    BIAS_TOXICITY_PROBING = "Bias/Toxicity Probing"

class AttackPayload(TypedDict):
    """Structured representation of a test case payload."""
    vector: AttackVector
    description: str
    payload: str
    metadata: dict # e.g., {"source": "manual", "severity": "high"}