"""Base classes for Public Safety Skills Framework."""

from __future__ import annotations

import abc
import enum
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

UTC = timezone.utc
from typing import Any

PUBLIC_SAFETY_VERSION = "1.0.0"


class Severity(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceRating(enum.Enum):
    CONFIRMED = "confirmed"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SPECULATIVE = "speculative"


@dataclass
class ConfidenceScore:
    rating: ConfidenceRating
    score: float
    explanation: str = ""

    def __post_init__(self):
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"Confidence score must be between 0 and 1, got {self.score}")

    def to_dict(self) -> dict[str, Any]:
        return {"rating": self.rating.value, "score": self.score, "explanation": self.explanation}


@dataclass
class SafetyCheckResult:
    passed: bool
    refused: bool = False
    reason: str = ""
    triggered_rules: list[str] = field(default_factory=list)
    confidence: ConfidenceScore | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "refused": self.refused,
            "reason": self.reason,
            "triggered_rules": self.triggered_rules,
            "confidence": self.confidence.to_dict() if self.confidence else None,
        }


@dataclass
class SkillResult:
    skill_name: str
    success: bool
    data: Any = None
    error: str | None = None
    confidence: ConfidenceScore | None = None
    safety_check: SafetyCheckResult | None = None
    audit_id: str = ""
    execution_time_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "safety_check": self.safety_check.to_dict() if self.safety_check else None,
            "audit_id": self.audit_id,
            "execution_time_ms": self.execution_time_ms,
            "warnings": self.warnings,
            "timestamp": self.timestamp,
        }


@dataclass
class CapabilityDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    required_permissions: list[str] = field(default_factory=list)
    safety_tier: str = "safe"
    examples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "required_permissions": self.required_permissions,
            "safety_tier": self.safety_tier,
            "examples": self.examples,
        }


class ReasoningEngine:
    """Structured reasoning with fact-vs-assumption tracking."""

    def __init__(self):
        self._steps: list[dict[str, Any]] = []

    def add_step(self, description: str, evidence: str = "", is_assumption: bool = False):
        self._steps.append(
            {
                "step": len(self._steps) + 1,
                "description": description,
                "evidence": evidence,
                "is_assumption": is_assumption,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def get_steps(self) -> list[dict[str, Any]]:
        return list(self._steps)

    def clear(self):
        self._steps.clear()

    def to_dict(self) -> list[dict[str, Any]]:
        return self._steps


class InputValidator:
    """Validate and sanitize skill inputs."""

    BLOCKED_PATTERNS: list[str] = [
        "rm -rf",
        "format",
        "dd if=",
        "> /dev/sda",
        "DROP TABLE",
        "DROP DATABASE",
        "DELETE FROM",
        "shutdown -r",
    ]

    @staticmethod
    def validate_string(value: Any, field_name: str, max_length: int = 10000) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string, got {type(value).__name__}")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} cannot be empty")
        if len(stripped) > max_length:
            raise ValueError(f"{field_name} exceeds max length of {max_length}")
        return stripped

    @staticmethod
    def validate_enum(value: Any, field_name: str, allowed: list[str]) -> str:
        validated = InputValidator.validate_string(value, field_name)
        if validated.lower() not in [a.lower() for a in allowed]:
            raise ValueError(f"{field_name} must be one of {allowed}, got '{value}'")
        return validated.lower()

    @staticmethod
    def validate_location(lat: float, lon: float) -> tuple[float, float]:
        if not (-90 <= lat <= 90):
            raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Longitude must be between -180 and 180, got {lon}")
        return lat, lon

    @staticmethod
    def sanitize_for_logging(value: str) -> str:
        import re

        cleaned = re.sub(r"\b\d{16,19}\b", "[REDACTED_CARD]", value)
        cleaned = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", value)
        cleaned = re.sub(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", cleaned
        )
        return cleaned


class SafetyRules:
    """Enforce ethical and legal boundaries."""

    FORBIDDEN_CATEGORIES: dict[str, list[str]] = {
        "hacking": [
            "exploit",
            "payload",
            "backdoor",
            "rootkit",
            "crack",
            "keylogger",
            "ransomware",
        ],
        "surveillance_abuse": [
            "stalk",
            "track without consent",
            "hidden camera",
            "covert recording",
        ],
        "violence": [
            "weapon instructions",
            "explosive",
            "poison",
            "chemical weapon",
            "biological weapon",
        ],
        "identity_fraud": ["forgery", "identity theft", "fake id", "impersonate officer"],
        "privacy_violation": ["doxxing", "non-consensual", "private data without warrant"],
    }

    def __init__(self):
        self._custom_rules: list[Callable[[dict[str, Any]], SafetyCheckResult | None]] = []

    def add_rule(self, rule: Callable[[dict[str, Any]], SafetyCheckResult | None]):
        self._custom_rules.append(rule)

    def check(self, query: str, context: dict[str, Any] | None = None) -> SafetyCheckResult:
        query_lower = query.lower()
        triggered: list[str] = []

        for category, keywords in self.FORBIDDEN_CATEGORIES.items():
            for kw in keywords:
                if kw in query_lower:
                    triggered.append(f"{category}:{kw}")

        if triggered:
            return SafetyCheckResult(
                passed=False,
                refused=True,
                reason=f"Request matches forbidden categories: {', '.join(triggered)}",
                triggered_rules=triggered,
            )

        if context:
            for rule in self._custom_rules:
                result = rule(context)
                if result is not None and not result.passed:
                    return result

        return SafetyCheckResult(passed=True)

    @staticmethod
    def requires_legal_authority(jurisdiction: str = "") -> SafetyCheckResult:
        return SafetyCheckResult(
            passed=False,
            refused=True,
            reason=f"This operation requires proper legal authority in {jurisdiction or 'the relevant jurisdiction'}. "
            "Consult with legal counsel and obtain appropriate warrants or court orders before proceeding.",
            triggered_rules=["legal_authority_required"],
        )

    @staticmethod
    def requires_consent() -> SafetyCheckResult:
        return SafetyCheckResult(
            passed=False,
            refused=True,
            reason="This operation requires explicit informed consent from all parties involved.",
            triggered_rules=["consent_required"],
        )


class ConfidenceScorer:
    """Evaluate confidence in results with transparent scoring."""

    @staticmethod
    def from_sources(
        source_count: int, corroborating: int, recency_hours: float
    ) -> ConfidenceScore:
        if source_count == 0:
            return ConfidenceScore(ConfidenceRating.SPECULATIVE, 0.1, "No sources available")

        score = min(1.0, (corroborating / source_count) * 0.7 + min(source_count / 5, 1.0) * 0.2)
        recency_factor = max(0, 1.0 - (recency_hours / 8760))
        score = score * 0.8 + recency_factor * 0.2

        rating = (
            ConfidenceRating.HIGH
            if score >= 0.8
            else (
                ConfidenceRating.MEDIUM
                if score >= 0.5
                else (ConfidenceRating.LOW if score >= 0.3 else ConfidenceRating.SPECULATIVE)
            )
        )

        return ConfidenceScore(
            rating=rating,
            score=round(score, 3),
            explanation=f"Based on {corroborating}/{source_count} corroborating sources, {recency_hours:.1f}h old",
        )

    @staticmethod
    def from_llm_self_assessment(
        reasoning_quality: float,
        data_completeness: float,
        uncertainty_flags: int,
    ) -> ConfidenceScore:
        score = reasoning_quality * 0.4 + data_completeness * 0.4 - uncertainty_flags * 0.1
        score = max(0.0, min(1.0, score))

        rating = (
            ConfidenceRating.HIGH
            if score >= 0.8
            else (
                ConfidenceRating.MEDIUM
                if score >= 0.5
                else (ConfidenceRating.LOW if score >= 0.3 else ConfidenceRating.SPECULATIVE)
            )
        )

        flags_desc = (
            f"{uncertainty_flags} uncertainty flags"
            if uncertainty_flags
            else "no uncertainty flags"
        )
        return ConfidenceScore(
            rating=rating,
            score=round(score, 3),
            explanation=f"Reasoning quality: {reasoning_quality:.2f}, data completeness: {data_completeness:.2f}, {flags_desc}",
        )


class AuditLogger:
    """Structured audit logging for all skill operations."""

    def __init__(self, log_callback: Callable[[dict[str, Any]], None] | None = None):
        self._entries: list[dict[str, Any]] = []
        self._log_callback = log_callback

    def log(
        self,
        skill_name: str,
        action: str,
        actor: str = "system",
        status: str = "info",
        details: dict[str, Any] | None = None,
        result: SkillResult | None = None,
    ):
        entry = {
            "audit_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "skill_name": skill_name,
            "action": action,
            "actor": actor,
            "status": status,
            "details": details or {},
        }
        if result:
            entry["result"] = result.to_dict()
        self._entries.append(entry)
        if self._log_callback:
            self._log_callback(entry)

    def get_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._entries[-limit:]

    def get_by_skill(self, skill_name: str) -> list[dict[str, Any]]:
        return [e for e in self._entries if e["skill_name"] == skill_name]

    def clear(self):
        self._entries.clear()


class ReportingEngine:
    """Generate structured reports with standardized formatting."""

    @staticmethod
    def create_report(
        title: str,
        summary: str,
        sections: list[dict[str, Any]],
        confidence: ConfidenceScore | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "title": title,
            "summary": summary,
            "sections": sections,
            "confidence": confidence.to_dict() if confidence else None,
            "warnings": warnings or [],
            "generated_at": datetime.now(UTC).isoformat(),
            "report_id": str(uuid.uuid4()),
        }

    @staticmethod
    def section(title: str, content: Any, evidence: list[str] | None = None) -> dict[str, Any]:
        return {
            "title": title,
            "content": content,
            "evidence": evidence or [],
        }

    @staticmethod
    def format_markdown(report: dict[str, Any]) -> str:
        lines = [f"# {report['title']}", "", report["summary"], ""]
        if report.get("confidence"):
            c = report["confidence"]
            lines.append(f"**Confidence**: {c['rating']} ({c['score']:.0%})")
            lines.append(f"*{c['explanation']}*")
            lines.append("")
        for section in report.get("sections", []):
            lines.append(f"## {section['title']}")
            lines.append("")
            content = section["content"]
            if isinstance(content, str):
                lines.append(content)
            elif isinstance(content, list):
                for item in content:
                    lines.append(f"- {item}")
            else:
                lines.append(str(content))
            lines.append("")
            if section.get("evidence"):
                lines.append("**Evidence:**")
                for ev in section["evidence"]:
                    lines.append(f"- {ev}")
                lines.append("")
        if report.get("warnings"):
            lines.append("---")
            lines.append("**Warnings:**")
            for w in report["warnings"]:
                lines.append(f"- ⚠ {w}")
            lines.append("")
        lines.append(f"*Report ID: {report['report_id']}*")
        return "\n".join(lines)


class BasePublicSafetySkill(abc.ABC):
    """Abstract base class for all public safety skills."""

    def __init__(self):
        self.safety = SafetyRules()
        self.reasoning = ReasoningEngine()
        self.audit_logger = AuditLogger()
        self.reporter = ReportingEngine()
        self.confidence_scorer = ConfidenceScorer()
        self.input_validator = InputValidator()

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @property
    @abc.abstractmethod
    def description(self) -> str: ...

    @property
    @abc.abstractmethod
    def capabilities(self) -> list[CapabilityDefinition]: ...

    @property
    def version(self) -> str:
        return PUBLIC_SAFETY_VERSION

    def get_safety_tier(self) -> str:
        return "safe"

    def requires_authorization(self) -> bool:
        return False

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        start = time.time()
        audit_id = str(uuid.uuid4())
        try:
            self._validate_params(params)
            safety_result = self._safety_check(params)
            if not safety_result.passed:
                elapsed = (time.time() - start) * 1000
                result = SkillResult(
                    skill_name=self.name,
                    success=False,
                    error=safety_result.reason,
                    safety_check=safety_result,
                    audit_id=audit_id,
                    execution_time_ms=elapsed,
                )
                self.audit_logger.log(
                    self.name, "execute", status="refused", details=params, result=result
                )
                return result

            data = await self._execute_impl(params)
            confidence = self._assess_confidence(params, data)
            elapsed = (time.time() - start) * 1000
            result = SkillResult(
                skill_name=self.name,
                success=True,
                data=data,
                confidence=confidence,
                safety_check=safety_result,
                audit_id=audit_id,
                execution_time_ms=elapsed,
            )
            self.audit_logger.log(
                self.name, "execute", status="success", details=params, result=result
            )
            return result
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            result = SkillResult(
                skill_name=self.name,
                success=False,
                error=str(e),
                audit_id=audit_id,
                execution_time_ms=elapsed,
            )
            self.audit_logger.log(
                self.name, "execute", status="error", details=params, result=result
            )
            return result

    def _validate_params(self, params: dict[str, Any]):
        return

    def _safety_check(self, params: dict[str, Any]) -> SafetyCheckResult:
        query_str = " ".join(str(v) for v in params.values())
        return self.safety.check(query_str, params)

    @abc.abstractmethod
    async def _execute_impl(self, params: dict[str, Any]) -> Any: ...

    def _assess_confidence(self, params: dict[str, Any], data: Any) -> ConfidenceScore:
        return ConfidenceScore(ConfidenceRating.MEDIUM, 0.5, "Default confidence assessment")

    def create_report(
        self, title: str, summary: str, sections: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return self.reporter.create_report(title, summary, sections)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "name", None):
            cls.name = cls.__name__
