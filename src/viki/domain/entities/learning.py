from dataclasses import dataclass


@dataclass
class Lesson:
    id: str
    content: str
    text_representation: str
    embedding: list[float] | None = None
    created_at: float = 0.0
    last_accessed: float = 0.0
    access_count: int = 1
    author: str = "System"
    source_task: str = "Unknown"
    reliability: float = 1.0


@dataclass
class FailureRecord:
    id: int | None
    action: str
    error: str
    context: str
    timestamp: float


@dataclass
class Relationship:
    lesson_id: str
    subj: str
    pred: str
    obj: str
