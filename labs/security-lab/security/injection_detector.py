"""
Educational prompt-injection heuristic classifier (defensive).

Purpose: score user/system-adjacent text for patterns often associated with
instruction override attempts — without claiming completeness (LLMs are not
solvable by regex alone).

Risks:
- False positives block legitimate power users.
- False negatives: determined adversaries evade keyword checks.

Mitigations:
- Combine with LLM-as-judge (optional, local model) for high-risk paths.
- Log all blocks with reason for tuning.
- Never use as sole control; enforce RBAC and tool sandbox regardless.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class InjectionReport:
    score: float  # 0..1 higher = riskier
    reasons: list[str]
    blocked: bool


# Benign educational patterns — high-level categories only (no weaponized payloads).
_SUSPICIOUS_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (
        re.compile(
            r"\b(ignore|disregard)\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|directives?)\b",
            re.I,
        ),
        "instruction_override_phrase",
        0.35,
    ),
    (
        re.compile(r"\b(system|developer)\s*:\s*", re.I),
        "fake_system_role_marker",
        0.25,
    ),
    (
        re.compile(r"<\s*/?\s*(system|instruction)\s*>", re.I),
        "pseudo_xml_instruction_tags",
        0.3,
    ),
    (
        re.compile(r"\b(you\s+are\s+now|new\s+instructions?)\b", re.I),
        "role_swap_cue",
        0.2,
    ),
    (
        re.compile(
            r"\b(print|reveal|leak|dump|expose)\b.+\b(secret|api[_-]?key|password|token)\b", re.I
        ),
        "exfiltration_language",
        0.4,
    ),
]


def analyze_prompt(text: str, block_threshold: float = 0.55) -> InjectionReport:
    if not text:
        return InjectionReport(0.0, [], False)
    reasons: list[str] = []
    score = 0.0
    for pat, label, w in _SUSPICIOUS_PATTERNS:
        if pat.search(text):
            reasons.append(label)
            score = min(1.0, score + w)
    blocked = score >= block_threshold
    return InjectionReport(score=score, reasons=reasons, blocked=blocked)
