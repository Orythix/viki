from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class Lesson:
    id: str
    content: str
    text_representation: str
    embedding: Optional[List[float]] = None
    created_at: float = 0.0
    last_accessed: float = 0.0
    access_count: int = 1
    author: str = "System"
    source_task: str = "Unknown"
    reliability: float = 1.0

@dataclass
class FailureRecord:
    id: Optional[int]
    action: str
    error: str
    context: str
    timestamp: float
