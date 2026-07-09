"""
Contradiction detection for lesson storage.

When a new lesson content overlaps semantically with an existing lesson but
asserts the opposite (or a conflicting fact), this module surfaces the conflict
so the system can reconcile rather than storing both blindly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from viki.config.logger import viki_logger

# Simple antonym / negation markers for heuristic detection.
_NEGATION_WORDS = {
    "not",
    "never",
    "cannot",
    "can't",
    "don't",
    "doesn't",
    "isn't",
    "wasn't",
    "won't",
    "wouldn't",
    "shouldn't",
    "no",
    "without",
    "dislike",
    "hates",
    "avoids",
    "refuses",
}

_CONTRADICTORY_PAIRS: set[tuple[str, str]] = {
    ("like", "dislike"),
    ("like", "hate"),
    ("love", "hate"),
    ("prefer", "avoid"),
    ("enable", "disable"),
    ("allow", "block"),
    ("support", "reject"),
    ("include", "exclude"),
    ("start", "stop"),
    ("begin", "end"),
    ("create", "delete"),
    ("add", "remove"),
    ("increase", "decrease"),
    ("raise", "lower"),
    ("enable", "prevent"),
    ("always", "never"),
    ("yes", "no"),
    ("true", "false"),
    ("positive", "negative"),
    ("good", "bad"),
    ("excellent", "terrible"),
    ("works", "broken"),
    ("succeed", "fail"),
    ("pass", "fail"),
}


@dataclass
class ContradictionResult:
    """Describes a detected contradiction between lessons."""

    existing_id: str
    existing_text: str
    new_text: str
    confidence: float  # 0.0 – 1.0
    reason: str = ""
    # If an LLM was used, the raw judgment text
    judgment: str | None = None


def extract_key_claims(text: str) -> set[str]:
    """Normalize a lesson string into a set of claim tokens for comparison."""
    text = text.lower().strip()
    # Remove punctuation
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    # Keep meaningful n-grams (1-3 words) that aren't pure stopwords
    claims: set[str] = set()
    for i in range(len(tokens)):
        for j in range(i + 1, min(i + 4, len(tokens) + 1)):
            phrase = " ".join(tokens[i:j])
            if len(phrase) > 2:
                claims.add(phrase)
    return claims


def has_negation(text: str) -> bool:
    """Check if a text contains negation markers."""
    text_lower = text.lower()
    return any(neg in text_lower.split() for neg in _NEGATION_WORDS)


def heuristic_contradiction_score(existing: str, new_text: str) -> float:
    """
    Return a confidence score (0-1) that *new_text* contradicts *existing*.

    Uses lexical overlap + negation detection.  0 = no conflict,
    1 = near-certain contradiction.
    """
    e_claims = extract_key_claims(existing)
    n_claims = extract_key_claims(new_text)

    if not e_claims or not n_claims:
        return 0.0

    common = e_claims & n_claims
    if not common:
        return 0.0

    # Check for negation asymmetry
    e_neg = has_negation(existing)
    n_neg = has_negation(new_text)

    # They share claims but differ on negation → likely contradiction
    if e_neg != n_neg:
        overlap_ratio = len(common) / max(len(e_claims), len(n_claims))
        return min(1.0, overlap_ratio * 1.2)

    # Check for contradictory word pairs in overlapping contexts
    e_words = set(existing.lower().split())
    n_words = set(new_text.lower().split())
    for a, b in _CONTRADICTORY_PAIRS:
        if (a in e_words and b in n_words) or (b in e_words and a in n_words):
            return 0.8

    return 0.0


async def detect_contradiction(
    existing_text: str,
    new_text: str,
    model_router: Any | None = None,
) -> ContradictionResult | None:
    """
    High-level contradiction check.

    1. Fast heuristic pass.
    2. If heuristic is ambiguous (0.3–0.7) and a model_router is available,
       ask an LLM to judge.
    """
    heuristic = heuristic_contradiction_score(existing_text, new_text)

    if heuristic >= 0.7:
        return ContradictionResult(
            existing_id="",
            existing_text=existing_text,
            new_text=new_text,
            confidence=heuristic,
            reason="High lexical overlap with opposing negation or contradictory keywords",
        )

    if 0.3 <= heuristic < 0.7 and model_router is not None:
        try:
            prompt = [
                {
                    "role": "system",
                    "content": (
                        "You are a contradiction detector.  Two statements are given. "
                        'Reply with ONLY a JSON object: {"contradiction": bool, "confidence": 0.0-1.0, "reason": "..."}. '
                        "A contradiction means they cannot both be true."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Statement A: {existing_text}\nStatement B: {new_text}",
                },
            ]
            response = await model_router.chat(prompt)
            result = _parse_llm_judgment(response)
            if result is not None:
                return result
        except Exception as e:
            viki_logger.debug("LLM contradiction check failed: %s", e)

    return None


def _parse_llm_judgment(response: str) -> ContradictionResult | None:
    """Extract a ContradictionResult from an LLM JSON response."""
    try:
        start = response.index("{")
        end = response.rindex("}")
        data = json.loads(response[start : end + 1])
        if data.get("contradiction"):
            return ContradictionResult(
                existing_id="",
                existing_text="",
                new_text="",
                confidence=float(data.get("confidence", 0.8)),
                reason=data.get("reason", "LLM judged contradictory"),
                judgment=response,
            )
    except (ValueError, json.JSONDecodeError, KeyError):
        pass
    return None
