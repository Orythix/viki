from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class HealthIssue:
    id: str
    severity: str  # low, medium, high
    file_path: str
    description: str
    suggestion: str
    status: str = "detected"  # detected, ignore, fixed
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class HealthReport:
    issues: list[HealthIssue] = field(default_factory=list)
    last_scan: datetime | None = None
