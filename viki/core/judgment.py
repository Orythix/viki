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

from dataclasses import dataclass

@dataclass
class JudgmentResult:
    outcome: JudgmentOutcome
    clarity: float
    risk: float
    novelty: float
    recommendation: str # "proceed", "deny", "confirm"
    reason: str
    recommended_capability: Optional[str] = None

class JudgmentEngine:
    """
    v11: The Cognitive Governor.
    Sits above all models to decide the 'Mode of Existence'.
    Enforces 'Judgment before Reasoning'.
    """
    def __init__(self, failure_memory, budget_allocator):
        self.failure_memory = failure_memory
        self.budgets = budget_allocator
        self.safety_threshold = 0.8
        self.reflex_threshold = 0.2 # Below this novelty/complexity, reflex only

    async def evaluate(self, user_input: str, context: Dict[str, Any]) -> JudgmentResult:
        """
        Calculates the optimal cognitive mode for a task.
        Returns detailed JudgmentResult for downstream processing.
        """
        # 1. Intent Clarity (Heuristic for now, could use a small local model)
        clarity = self._calculate_clarity(user_input)
        
        # 2. Risk Assessment
        risk = self._assess_risk(user_input, context)
        
        # 3. Novelty & Failure check
        past_failure = self._check_failure_similarity(user_input)
        novelty = self._estimate_novelty(user_input, context)
        
        # 4. Capability Recommendation (Heuristic)
        recommended_cap = None
        input_lower = user_input.lower()
        if "search" in input_lower or "find" in input_lower or "research" in input_lower or "who is" in input_lower or "what is" in input_lower:
            recommended_cap = "internet_research"
        elif "write" in input_lower or "save" in input_lower or "delete" in input_lower:
            recommended_cap = "filesystem_write"
        elif "list" in input_lower or "read" in input_lower or "open file" in input_lower:
            recommended_cap = "filesystem_read"
        
        viki_logger.info(f"Judgment Engine: Clarity={clarity:.2f}, Risk={risk:.2f}, Novelty={novelty:.2f}, RecCap={recommended_cap}")

        # --- JUDGMENT LOGIC ---
        
        # Rule: Refuse if risk is extreme or clarity is zero
        if risk > self.safety_threshold:
            return JudgmentResult(
                outcome=JudgmentOutcome.REFUSE, clarity=clarity, risk=risk, novelty=novelty, 
                recommendation="deny", reason="Task exceeds risk threshold (Critical Zone).",
                recommended_capability=recommended_cap
            )
        if clarity < 0.3:
            return JudgmentResult(
                outcome=JudgmentOutcome.REFUSE, clarity=clarity, risk=risk, novelty=novelty, 
                recommendation="deny", reason="Intent too ambiguous.",
                recommended_capability=recommended_cap
            )

        # Rule: Repeat failures require Deep Thinking
        if past_failure > 0.7:
             viki_logger.warning("Judgment: Detected high failure similarity. Escalating to DEEP reasoning.")
             return JudgmentResult(
                 outcome=JudgmentOutcome.DEEP, clarity=clarity, risk=risk, novelty=novelty,
                 recommendation="proceed", reason="Escalating context: Previous similar attempts failed.",
                 recommended_capability=recommended_cap
             )

        # Rule: REFLEX only for explicit system commands
        command_keywords = ["open", "launch", "click", "type", "scroll", "press",
                            "pause", "play", "resume", "skip", "mute", "unmute", "volume",
                            "search", "google"]
        input_words = input_lower.split()
        if any(k in input_words for k in command_keywords) and risk < 0.2:
             return JudgmentResult(
                 outcome=JudgmentOutcome.REFLEX, clarity=clarity, risk=risk, novelty=novelty,
                 recommendation="proceed", reason="Direct system command detected.",
                 recommended_capability=recommended_cap
             )

        # Rule: Bias toward simplicity (Model Agnostic Thrift)
        if novelty < self.reflex_threshold and risk < 0.1 and clarity > 0.8:
            return JudgmentResult(
                outcome=JudgmentOutcome.SHALLOW, clarity=clarity, risk=risk, novelty=novelty,
                recommendation="proceed", reason="Familiar pattern. Shallow reasoning applied.",
                recommended_capability=recommended_cap
            )

        if risk < 0.4 and novelty < 0.6:
            return JudgmentResult(
                outcome=JudgmentOutcome.SHALLOW, clarity=clarity, risk=risk, novelty=novelty,
                recommendation="proceed", reason="Standard task. Shallow reasoning applied.",
                recommended_capability=recommended_cap
            )

        # Default to Deep for everything else
        return JudgmentResult(
            outcome=JudgmentOutcome.DEEP, clarity=clarity, risk=risk, novelty=novelty,
            recommendation="proceed", reason="Novel or complex task. Deliberative planning required.",
            recommended_capability=recommended_cap
        )

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

    def _check_failure_similarity(self, text: str) -> float:
        # Interface with LearningModule failure memory
        # For now, a mock score
        return 0.1 

    def _estimate_novelty(self, text: str, context: Dict[str, Any]) -> float:
        # Check against macro memory and world habits
        return 0.5 # Default
