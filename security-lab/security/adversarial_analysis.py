"""
Defensive adversarial prompt analysis (educational).

Purpose
-------
Combine sanitization, injection heuristics, and memory-store hygiene signals into
one structured report for instructors and dashboards — without executing tools
or calling an LLM.

Security risks
--------------
- Heuristic scores are not ground truth; over-trust causes false confidence.
- Logging raw user text can leak PII; callers should redact before persistence.

Mitigations
-----------
- Treat reports as triage hints; pair with RBAC, sandboxing, and human review.
- Redact via ``secrets_redact`` before writing to audit storage.
"""
from __future__ import annotations

from typing import Any, Dict

from security.injection_detector import analyze_prompt
from security.sanitizer import sanitize_prompt
from security.testing_harness import run_memory_poisoning_check


def adversarial_prompt_report(text: str, max_chars: int = 16_384) -> Dict[str, Any]:
    raw = text or ""
    raw_len = len(raw)
    strip_raw = raw.strip()[:max_chars]
    sanitized = sanitize_prompt(raw, max_chars)
    inj = analyze_prompt(sanitized)
    _, mem_changed = run_memory_poisoning_check(raw, max_chars)
    return {
        "input_length": raw_len,
        "sanitized_length": len(sanitized),
        "sanitizer_changed": sanitized != strip_raw,
        "injection": {
            "score": inj.score,
            "reasons": inj.reasons,
            "blocked": inj.blocked,
        },
        "memory_poisoning_mitigation": {
            "sanitized_differs_from_raw": mem_changed,
        },
    }
