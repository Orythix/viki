"""
Token-aware text condensation for local LLM context windows.

Uses a real tokenizer when available (tiktoken / transformers), otherwise a
deterministic heuristic. Never prefer raw ``len//4`` at call sites that go
through ``count_tokens`` / ``BudgetedContextAssembler``.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any

_TOKENIZER: Any | None = None
_TOKENIZER_KIND: str = "unset"

# Air-gap local cache paths (no network required for first boot).
_DEFAULT_ENCODING_CACHE = os.path.join("data", "tokenizers", "cl100k_base.json")
_CL100K_PAT = (
    r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}+|\p{N}{1,3}|"
    r" ?[^\s\p{L}\p{N}]++[\r\n]*|\s*[\r\n]|\s+(?!\S)|\s+"
)
_CL100K_SPECIAL = {
    "<|endoftext|>": 100257,
    "<|fim_prefix|>": 100258,
    "<|fim_middle|>": 100259,
    "<|fim_suffix|>": 100260,
    "<|endofprompt|>": 100276,
}


def _package_tokenizer_path() -> str | None:
    """Shipped ranks inside the wheel/sdist (air-gap first boot)."""
    try:
        from importlib import resources

        ref = resources.files("viki.assets.tokenizers").joinpath("cl100k_base.json")
        with resources.as_file(ref) as path:
            if path.is_file():
                return str(path)
    except Exception:
        pass
    # Source-tree fallback when not installed as a package.
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(
        os.path.join(here, "..", "..", "assets", "tokenizers", "cl100k_base.json")
    )
    return candidate if os.path.isfile(candidate) else None


def _encoding_cache_paths() -> list[str]:
    paths: list[str] = []
    for env_key in ("VIKI_TIKTOKEN_CACHE", "VIKI_TOKENIZER_CACHE"):
        val = os.environ.get(env_key, "").strip()
        if val:
            paths.append(val)
    pkg = _package_tokenizer_path()
    if pkg:
        paths.append(pkg)
    paths.append(_DEFAULT_ENCODING_CACHE)
    paths.append(os.path.join("data", "tokenizers", "cl100k_base.tiktoken"))
    # Dedupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _encoding_from_json(path: str) -> Any | None:
    import json

    import tiktoken

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "mergeable_ranks" not in data:
        return None
    ranks_raw = data["mergeable_ranks"]
    ranks: dict[bytes, int] = {}
    for k, v in ranks_raw.items():
        if isinstance(k, str):
            ranks[k.encode("latin-1")] = int(v)
        elif isinstance(k, (bytes, bytearray)):
            ranks[bytes(k)] = int(v)
    return tiktoken.Encoding(
        name="cl100k_base_local",
        pat_str=data.get("pat_str") or _CL100K_PAT,
        mergeable_ranks=ranks,
        special_tokens=data.get("special_tokens") or _CL100K_SPECIAL,
    )


def _try_load_tiktoken_from_cache() -> Any | None:
    """Load cl100k_base from shipped package asset or local cache (air-gapped)."""
    for path in _encoding_cache_paths():
        if not path or not os.path.isfile(path):
            continue
        try:
            if path.endswith(".json"):
                enc = _encoding_from_json(path)
                if enc is not None:
                    return enc
            else:
                import tiktoken
                from tiktoken.load import load_tiktoken_bpe

                mergeable_ranks = load_tiktoken_bpe(path)
                return tiktoken.Encoding(
                    name="cl100k_base_local",
                    pat_str=_CL100K_PAT,
                    mergeable_ranks=mergeable_ranks,
                    special_tokens=_CL100K_SPECIAL,
                )
        except Exception:
            continue
    return None


def _try_cache_tiktoken_encoding(enc: Any) -> None:
    """Persist encoding ranks for offline reuse when possible."""
    path = _encoding_cache_path()
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if os.path.isfile(path):
            return
        # Prefer copying tiktoken's on-disk cache if the package already fetched it.
        cache_dir = os.environ.get("TIKTOKEN_CACHE_DIR") or os.path.join(
            os.path.expanduser("~"), ".cache", "tiktoken"
        )
        if os.path.isdir(cache_dir):
            for name in os.listdir(cache_dir):
                src = os.path.join(cache_dir, name)
                if os.path.isfile(src) and "cl100k" in name.lower():
                    import shutil

                    shutil.copy2(src, path)
                    return
        # Minimal JSON dump of ranks when Encoding exposes them.
        ranks = getattr(enc, "_mergeable_ranks", None) or getattr(enc, "mergeable_ranks", None)
        if isinstance(ranks, dict):
            import json

            serializable = {
                "mergeable_ranks": {
                    (k.decode("latin-1") if isinstance(k, (bytes, bytearray)) else str(k)): int(v)
                    for k, v in ranks.items()
                },
                "special_tokens": getattr(enc, "_special_tokens", {}) or {},
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(serializable, f)
    except Exception:
        pass


def _load_tokenizer() -> tuple[Any | None, str]:
    global _TOKENIZER, _TOKENIZER_KIND
    if _TOKENIZER_KIND != "unset":
        return _TOKENIZER, _TOKENIZER_KIND

    # 1) Air-gap local encoding file (no network).
    cached = _try_load_tiktoken_from_cache()
    if cached is not None:
        _TOKENIZER = cached
        _TOKENIZER_KIND = "tiktoken_local"
        return _TOKENIZER, _TOKENIZER_KIND

    # 2) Prefer live tiktoken, then cache for next air-gapped run.
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        _TOKENIZER = enc
        _TOKENIZER_KIND = "tiktoken"
        _try_cache_tiktoken_encoding(enc)
        return _TOKENIZER, _TOKENIZER_KIND
    except Exception:
        pass

    # 3) Optional HuggingFace tokenizer (local dir or name).
    try:
        name = os.environ.get("VIKI_TOKENIZER_NAME", "").strip()
        local_dir = os.environ.get("VIKI_TOKENIZER_DIR", "").strip()
        from_path = local_dir if local_dir and os.path.isdir(local_dir) else name
        if from_path:
            from transformers import AutoTokenizer

            tok = AutoTokenizer.from_pretrained(
                from_path, use_fast=True, local_files_only=bool(local_dir)
            )
            _TOKENIZER = tok
            _TOKENIZER_KIND = "transformers"
            return _TOKENIZER, _TOKENIZER_KIND
    except Exception:
        pass

    _TOKENIZER = None
    _TOKENIZER_KIND = "heuristic"
    return _TOKENIZER, _TOKENIZER_KIND


def reset_tokenizer_cache() -> None:
    """Test helper to force re-detection."""
    global _TOKENIZER, _TOKENIZER_KIND
    _TOKENIZER = None
    _TOKENIZER_KIND = "unset"
    count_tokens.cache_clear()


@lru_cache(maxsize=2048)
def count_tokens(text: str) -> int:
    """Return token count for ``text`` using the best available tokenizer."""
    if not text:
        return 0
    tok, kind = _load_tokenizer()
    if kind in ("tiktoken", "tiktoken_local") and tok is not None:
        try:
            return len(tok.encode(text))
        except Exception:
            pass
    if kind == "transformers" and tok is not None:
        try:
            return len(tok.encode(text, add_special_tokens=False))
        except Exception:
            pass
    # Heuristic: ~4 chars/token for English-ish text; floor of 1 for non-empty.
    return max(1, (len(text) + 3) // 4)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate ``text`` to approximately ``max_tokens`` tokens."""
    if max_tokens <= 0 or not text:
        return ""
    if count_tokens(text) <= max_tokens:
        return text
    tok, kind = _load_tokenizer()
    if kind in ("tiktoken", "tiktoken_local") and tok is not None:
        try:
            ids = tok.encode(text)[:max_tokens]
            return tok.decode(ids)
        except Exception:
            pass
    if kind == "transformers" and tok is not None:
        try:
            ids = tok.encode(text, add_special_tokens=False)[:max_tokens]
            return tok.decode(ids, skip_special_tokens=True)
        except Exception:
            pass
    # Char heuristic fallback
    return text[: max_tokens * 4]


def condense_text(text: str, max_chars: int = 3000, query: str | None = None) -> str:
    """
    Condenses text for local LLM consumption.
    1. Removes boilerplate lines.
    2. Collapses whitespace.
    3. If query is provided, prioritizes blocks containing query terms.
    4. Truncates by token budget derived from max_chars (~4 chars/token).
    """
    if not text:
        return ""

    text = re.sub(r"[ \t]+", " ", text)
    lines = text.splitlines()
    cleaned_lines = []

    boilerplate_keywords = [
        "cookie",
        "privacy policy",
        "terms of use",
        "subscribe",
        "sign in",
        "log in",
        "all rights reserved",
        "copyright",
        "skip to content",
        "menu",
        "navigation",
    ]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if len(line) < 10:
            continue
        lower_line = line.lower()
        if any(kw in lower_line for kw in boilerplate_keywords):
            continue
        cleaned_lines.append(line)

    if query and len(cleaned_lines) > 20:
        query_terms = set(re.findall(r"\w+", query.lower()))
        scored_lines = []
        for line in cleaned_lines:
            line_terms = set(re.findall(r"\w+", line.lower()))
            score = len(query_terms & line_terms)
            scored_lines.append((score, line))

        final_lines = []
        for i, (score, line) in enumerate(scored_lines):
            if score > 0:
                final_lines.append(line)
            elif i < 5 or i > len(scored_lines) - 5:
                final_lines.append(line)
        cleaned_lines = final_lines

    result = "\n".join(cleaned_lines)
    max_tokens = max(32, max_chars // 4)
    if count_tokens(result) > max_tokens:
        result = truncate_to_tokens(result, max_tokens)
        if not result.endswith("\n... (further content truncated for token efficiency)"):
            result = result.rstrip() + "\n... (further content truncated for token efficiency)"
    return result


def summarize_heuristic(text: str) -> str:
    """
    Extreme condensation: Keep only headers (lines ending in :) and first sentences.
    """
    lines = text.splitlines()
    summary = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.endswith(":") or len(line) < 80:
            summary.append(line)
        else:
            match = re.match(r"[^.!?]+[.!?]", line)
            if match:
                summary.append(match.group(0))
    return "\n".join(summary)


def extractive_keep(text: str, query: str, max_tokens: int, preserve_citations: bool = True) -> str:
    """
    Query-conditioned extractive compression that prefers citation-like lines.
    """
    if not text or max_tokens <= 0:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    terms = set(re.findall(r"\w+", (query or "").lower()))
    scored: list[tuple[float, int, str]] = []
    for i, line in enumerate(lines):
        score = 0.0
        lower = line.lower()
        if terms:
            score += len(terms & set(re.findall(r"\w+", lower)))
        if preserve_citations and (
            "http://" in lower
            or "https://" in lower
            or re.search(r"\[\d+\]", line)
            or line.startswith(">")
            or "source:" in lower
            or "cite:" in lower
        ):
            score += 2.0
        # Prefer edges slightly (lost-in-the-middle mitigation for keep set).
        if i < 3 or i >= len(lines) - 3:
            score += 0.25
        scored.append((score, i, line))
    scored.sort(key=lambda t: (-t[0], t[1]))

    kept: list[tuple[int, str]] = []
    used = 0
    for _score, idx, line in scored:
        cost = count_tokens(line) + 1
        if used + cost > max_tokens:
            continue
        kept.append((idx, line))
        used += cost
        if used >= max_tokens:
            break
    kept.sort(key=lambda t: t[0])
    return "\n".join(ln for _, ln in kept)
