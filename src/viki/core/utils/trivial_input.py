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
_TRIVIAL_MAX_LEN = 80

_GREETING_WORDS = (
    "hi",
    "hello",
    "hey",
    "yo",
    "hola",
    "hiya",
    "good morning",
    "good afternoon",
    "good evening",
    "good night",
    "thanks",
    "thank you",
    "thx",
    "cheers",
    "ty",
    "ok",
    "okay",
    "cool",
    "nice",
    "got it",
    "sounds good",
    "alright",
    "bye",
    "goodbye",
    "see ya",
    "cya",
    "later",
    "farewell",
    "how are you",
    "how are u",
    "how r u",
    "how's it going",
    "whats up",
    "what's up",
    "what up",
    "wassup",
    "sup",
    "howdy",
    "what's happening",
    "what's good",
)

_SMALL_TALK_FRAGMENTS = (
    "how are you",
    "how are u",
    "how r u",
    "how's it going",
    "whats up",
    "what's up",
    "what up",
    "wassup",
    "sup",
    "howdy",
    "what's happening",
    "what's good",
    "who am i",
    "who i am",
    "do you know who i am",
    "do you know me",
    "remember me",
)

_STRICT_PATTERNS = (
    re.compile(r"^(hi|hello|hey|yo|hola|hiya)(\s+(there|viki))?[\.\!\?]*$", re.IGNORECASE),
    re.compile(r"^good\s+(morning|afternoon|evening|night)(\s+viki)?[\.\!\?]*$", re.IGNORECASE),
    re.compile(r"^(thanks|thank\s+you|thx|cheers|ty)(\s+viki)?[\.\!\?]*$", re.IGNORECASE),
    re.compile(r"^(ok|okay|cool|nice|got\s+it|sounds\s+good|alright)[\.\!\?]*$", re.IGNORECASE),
    re.compile(r"^(bye|goodbye|see\s+ya|cya|later|farewell|good\s+night)[\.\!\?]*$", re.IGNORECASE),
    re.compile(r"^what'?s\s+up\??[\.\!]*$", re.IGNORECASE),
    re.compile(r"^how\s+(are\s+you|are\s+u|r\s+u|('s|s)\s+it\s+going)\??[\.\!\?]*$", re.IGNORECASE),
)


def is_trivial_input(text: str) -> bool:
    if not text:
        return True
    s = text.strip().lower()
    if not s:
        return True
    if len(s) > _TRIVIAL_MAX_LEN:
        return False
    s_stripped = s.rstrip(".!? ")
    for pat in _STRICT_PATTERNS:
        if pat.match(s_stripped):
            return True
    if s_stripped in _GREETING_WORDS:
        return True
    return False


def is_conversational_input(text: str) -> bool:
    """Return True for small-talk / chit-chat that shouldn't trigger tools.

    Catches compound phrases like 'hello viki. whats up bro??' that
    ``is_trivial_input`` misses because they contain extra words.  The
    bar is low: if the input is short and dominated by greeting / small-
    talk fragments, it's conversational.  Real task-shaped input like
    'search for X' or 'calculate Y' will not match.
    """
    if not text:
        return True
    s = text.strip().lower()
    if not s:
        return True
    if len(s) > _TRIVIAL_MAX_LEN:
        return False
    if is_trivial_input(text):
        return True
    tokens = re.split(r"[\s,.!?;]+", s)
    tokens = [t for t in tokens if t]
    if not tokens:
        return True
    fragment_hits = sum(1 for frag in _SMALL_TALK_FRAGMENTS if frag in s)
    if fragment_hits >= 1 and len(tokens) <= 8:
        non_filler = [
            t
            for t in tokens
            if t
            not in (
                "bro",
                "dude",
                "man",
                "mate",
                "lol",
                "haha",
                "viki",
                "hey",
                "oh",
                "so",
                "like",
                "um",
                "uh",
            )
        ]
        if len(non_filler) <= 5:
            return True
    return False
