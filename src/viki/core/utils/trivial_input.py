"""
Shared "is this a trivial conversational turn?" predicate.

A turn is trivial only when it clearly matches a greeting / ack / farewell
shape (e.g. "hi", "hello viki", "thanks", "bye", "ok"). Intentionally
narrow: false negatives (a real greeting that isn't matched) just pay the
normal latency budget; false positives (a real task mis-classified as
trivial) silently strip semantic context from the prompt. We bias for the
safer error.

Used to keep behavior consistent across the hot path:
- `viki.core.reflex` has its own canned-response regex set,
- `viki.core.memory` and `viki.core.learning` skip embedding-based retrieval here,
- `viki.core.cortex` Deliberation streams tokens and skips the ensemble here.
"""

from __future__ import annotations

import re

# Inputs longer than this are unconditionally non-trivial.
_TRIVIAL_MAX_LEN = 60

# Greetings / acks / farewells. If the input matches one of these, treat it
# as trivial. Patterns mirror the reflex set in `viki.core.reflex`.
_GREETING_PATTERNS = (
    re.compile(r"^(hi|hello|hey|yo|hola|hiya)(\s+(there|viki))?[\.\!]*$", re.IGNORECASE),
    re.compile(r"^good\s+(morning|afternoon|evening|night)(\s+viki)?[\.\!]*$", re.IGNORECASE),
    re.compile(r"^(thanks|thank\s+you|thx|cheers|ty)(\s+viki)?[\.\!]*$", re.IGNORECASE),
    re.compile(r"^(ok|okay|cool|nice|got\s+it|sounds\s+good|alright)[\.\!]*$", re.IGNORECASE),
    re.compile(r"^(bye|goodbye|see\s+ya|cya|later|farewell|good\s+night)[\.\!]*$", re.IGNORECASE),
    re.compile(r"^how\s+(are\s+you|are\s+u|r\s+u|('s|s)\s+it\s+going)\??[\.\!]*$", re.IGNORECASE),
    re.compile(r"^what'?s\s+up\??[\.\!]*$", re.IGNORECASE),
)


def is_trivial_input(text: str) -> bool:
    """
    Return True for clear greetings / acks / farewells. Empty / whitespace
    inputs are also trivial. Everything else returns False.
    """
    if not text:
        return True
    s = text.strip()
    if not s:
        return True
    if len(s) > _TRIVIAL_MAX_LEN:
        return False
    for pat in _GREETING_PATTERNS:
        if pat.match(s):
            return True
    return False
