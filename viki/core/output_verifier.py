import re
import time
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel
from viki.config.logger import viki_logger
from viki.core.schema import ThoughtObject, ActionCall

class JudgmentOutcome(Enum):
    REFLEX = "reflex"           # Fast, low-resource, no deep thought
    SHALLOW = "shallow"         # Brief reasoning, minimal tool use
    DEEP = "deep"               # Full consciousness stack, internal debate
    REFUSE = "refuse"           # Safety or clarity block

from dataclasses import dataclass, field

@dataclass
class JudgmentResult:
    outcome: JudgmentOutcome
    clarity: float
    risk: float
    novelty: float
    recommendation: str # "proceed", "deny", "confirm"
    reason: str
    recommended_capability: Optional[str] = None
    failure_similarity: float = 0.0
    elapsed_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "clarity": round(self.clarity, 3),
            "risk": round(self.risk, 3),
            "novelty": round(self.novelty, 3),
            "failure_similarity": round(self.failure_similarity, 3),
            "recommendation": self.recommendation,
            "reason": self.reason,
            "recommended_capability": self.recommended_capability,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }

class JudgmentEngine:
    """
    v11: The Cognitive Governor.
    Sits above all models to decide the 'Mode of Existence'.
    Enforces 'Judgment before Reasoning'.
    """
    def __init__(self, failure_memory, budget_allocator):
        # `failure_memory` is the LearningModule (lessons + failures + macros).
        self.failure_memory = failure_memory
        self.budgets = budget_allocator
        self.safety_threshold = 0.8
        self.reflex_threshold = 0.2 # Below this novelty/complexity, reflex only
        self._reflex_command_keywords = {
            "open", "launch", "click", "type", "scroll", "press",
            "pause", "play", "resume", "skip", "mute", "unmute", "volume",
            "search", "google", "stop",
        }

    async def evaluate(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> JudgmentResult:
        """
        Calculates the optimal cognitive mode for a task.
        Returns detailed JudgmentResult for downstream processing.
        """
        t0 = time.perf_counter()
        context = context or {}

        clarity = self._calculate_clarity(user_input)
        risk = self._assess_risk(user_input, context)
        past_failure = self._check_failure_similarity(user_input)
        novelty = self._estimate_novelty(user_input, context)

        recommended_cap = self._recommend_capability(user_input)

        viki_logger.info(
            "Judgment Engine: Clarity=%.2f, Risk=%.2f, Novelty=%.2f, FailSim=%.2f, RecCap=%s",
            clarity, risk, novelty, past_failure, recommended_cap,
        )

        def _make(outcome: JudgmentOutcome, recommendation: str, reason: str) -> JudgmentResult:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return JudgmentResult(
                outcome=outcome,
                clarity=clarity,
                risk=risk,
                novelty=novelty,
                recommendation=recommendation,
                reason=reason,
                recommended_capability=recommended_cap,
                failure_similarity=past_failure,
                elapsed_ms=elapsed,
            )

        # --- JUDGMENT LOGIC ---

        # Rule: Refuse if risk is extreme.
        if risk > self.safety_threshold:
            return _make(JudgmentOutcome.REFUSE, "deny", "Task exceeds risk threshold (Critical Zone).")
        if clarity < 0.3:
            return _make(JudgmentOutcome.REFUSE, "deny", "Intent too ambiguous.")

        # Rule: Repeat failures require Deep Thinking.
        if past_failure > 0.7:
            viki_logger.warning("Judgment: Detected high failure similarity. Escalating to DEEP reasoning.")
            return _make(JudgmentOutcome.DEEP, "proceed", "Escalating context: Previous similar attempts failed.")

        # Rule: REFLEX only for explicit, low-risk system commands.
        input_words = user_input.lower().split()
        if any(k in input_words for k in self._reflex_command_keywords) and risk < 0.2:
            return _make(JudgmentOutcome.REFLEX, "proceed", "Direct system command detected.")

        # Rule: Questions require DEEP reasoning for accuracy.
        if context.get("task_type") == "question" or recommended_cap == "internet_research":
            return _make(JudgmentOutcome.DEEP, "proceed", "Inquisitive or research intent detected. Routing to Deliberation Layer.")

        # Rule: Bias toward simplicity (Model Agnostic Thrift).
        if novelty < self.reflex_threshold and risk < 0.1 and clarity > 0.8:
            return _make(JudgmentOutcome.SHALLOW, "proceed", "Familiar pattern. Shallow reasoning applied.")

        if risk < 0.4 and novelty < 0.6:
            return _make(JudgmentOutcome.SHALLOW, "proceed", "Standard task. Shallow reasoning applied.")

        return _make(JudgmentOutcome.DEEP, "proceed", "Novel or complex task. Deliberative planning required.")

    def _recommend_capability(self, user_input: str) -> Optional[str]:
        input_lower = user_input.lower()
        if any(k in input_lower for k in ("search", "find", "research", "who is")):
            return "internet_research"
        if "what is" in input_lower:
            tail_m = re.search(r"\bwhat\s+is\s+(.+)$", input_lower.strip())
            trivial = False
            if tail_m:
                tail = tail_m.group(1).strip().rstrip("?")
                trivial = bool(
                    re.fullmatch(r"[\d\s\+\-\*\/\^\(\)\.\,]+", tail) and len(tail) <= 48
                )
            if not trivial:
                return "internet_research"
        if any(k in input_lower for k in ("write", "save", "delete")):
            return "filesystem_write"
        if any(k in input_lower for k in ("list", "read", "open file")):
            return "filesystem_read"
        return None

    def _calculate_clarity(self, text: str) -> float:
        words = text.split()
        if not words: return 0.0
        
        # Single word inputs still have meaning
        if len(words) == 1: return 0.5
        
        # Short phrases (2-3 words) are usually clear enough
        if len(words) <= 3: return 0.7
        
        # Longer inputs scale up
        return min(1.0, len(words) / 5.0)

    def _assess_risk(self, text: str, context: Dict[str, Any]) -> float:
        dangerous_keywords = ["delete", "remove", "kill", "format", "overwrite", "sudo", "rm -rf"]
        risk = 0.0
        for k in dangerous_keywords:
            if k in text.lower(): risk += 0.3
        
        # Zone check from world model
        if context.get('is_protected_zone'):
            risk += 0.5
            
        return min(1.0, risk)

    def _tokenize(self, text: str) -> set:
        return {w for w in re.findall(r"\w+", (text or "").lower()) if len(w) > 2}

    def _check_failure_similarity(self, text: str) -> float:
        """
        Compare against recent failures in the LearningModule.
        Returns 0.0..1.0 — peak Jaccard overlap between input tokens and any recent failure context/action.
        """
        if not self.failure_memory or not hasattr(self.failure_memory, "get_relevant_failures"):
            return 0.0
        try:
            failures = self.failure_memory.get_relevant_failures(text, limit=5) or []
        except Exception as e:
            viki_logger.debug("JudgmentEngine: failure lookup failed: %s", e)
            return 0.0

        if not failures:
            return 0.0

        query = self._tokenize(text)
        if not query:
            return 0.0

        peak = 0.0
        for f in failures:
            tokens = self._tokenize(str(f))
            if not tokens:
                continue
            inter = len(query & tokens)
            union = len(query | tokens) or 1
            peak = max(peak, inter / union)
        return min(1.0, peak)

    def _estimate_novelty(self, text: str, context: Dict[str, Any]) -> float:
        """
        Approximates novelty via lesson recall + recent-history overlap.
        - Strong overlap with prior lessons -> low novelty.
        - No overlap -> high novelty.
        """
        if not self.failure_memory or not hasattr(self.failure_memory, "get_relevant_lessons"):
            return 0.5

        try:
            lessons = self.failure_memory.get_relevant_lessons(text, limit=5) or []
        except Exception as e:
            viki_logger.debug("JudgmentEngine: lesson lookup failed: %s", e)
            return 0.5

        # No prior knowledge at all -> moderately novel.
        total_lessons = 0
        try:
            total_lessons = self.failure_memory.get_total_lesson_count()
        except Exception:
            total_lessons = 0
        if total_lessons == 0:
            return 0.7

        if not lessons:
            return 0.85

        query = self._tokenize(text)
        if not query:
            return 0.5

        peak = 0.0
        for lesson in lessons:
            tokens = self._tokenize(str(lesson))
            if not tokens:
                continue
            inter = len(query & tokens)
            denom = len(query) or 1
            peak = max(peak, inter / denom)

        # peak=1.0 -> no novelty (everything overlaps); peak=0.0 -> highly novel.
        novelty = 1.0 - min(1.0, peak)
        return max(0.0, min(1.0, novelty))
