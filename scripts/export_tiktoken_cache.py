#!/usr/bin/env python3
"""Export cl100k_base ranks into the package for air-gapped first boot."""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    try:
        import tiktoken
    except ImportError:
        print("tiktoken required: pip install tiktoken", file=sys.stderr)
        return 1

    enc = tiktoken.get_encoding("cl100k_base")
    ranks = enc._mergeable_ranks
    out = {
        "pat_str": (
            r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}+|\p{N}{1,3}|"
            r" ?[^\s\p{L}\p{N}]++[\r\n]*|\s*[\r\n]|\s+(?!\S)|\s+"
        ),
        "special_tokens": {
            "<|endoftext|>": 100257,
            "<|fim_prefix|>": 100258,
            "<|fim_middle|>": 100259,
            "<|fim_suffix|>": 100260,
            "<|endofprompt|>": 100276,
        },
        "mergeable_ranks": {k.decode("latin-1"): int(v) for k, v in ranks.items()},
    }
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dest_dir = os.path.join(root, "src", "viki", "assets", "tokenizers")
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, "cl100k_base.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    # Also mirror under data/ for runtime default path.
    data_dir = os.path.join(root, "data", "tokenizers")
    os.makedirs(data_dir, exist_ok=True)
    data_path = os.path.join(data_dir, "cl100k_base.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {path} ({os.path.getsize(path)} bytes, {len(ranks)} ranks)")
    print(f"wrote {data_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
