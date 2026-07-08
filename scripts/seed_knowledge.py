#!/usr/bin/env python3
"""
Import curated lessons from viki/config/knowledge_seed.jsonl into viki_knowledge.db.

Use after clone or when refreshing operator + reference facts (profile, n8n, etc.).

  python scripts/seed_knowledge.py
  python scripts/seed_knowledge.py --reinforce   # access_count 2 for export thresholds
  python scripts/seed_knowledge.py --data-dir D:/VIKI/data
"""

from __future__ import annotations

import argparse
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from viki.core.knowledge_ingestion import LearningModule  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Seed VIKI lessons from knowledge_seed.jsonl")
    p.add_argument(
        "--file",
        default=os.path.join(_REPO_ROOT, "viki", "config", "knowledge_seed.jsonl"),
        help="Path to JSONL (default: viki/config/knowledge_seed.jsonl)",
    )
    p.add_argument(
        "--data-dir",
        default=None,
        help="SQLite data directory (default: ./data or VIKI_DATA_DIR)",
    )
    p.add_argument(
        "--reinforce",
        action="store_true",
        help="Import each line twice so new rows start export-eligible (access_count>=2)",
    )
    args = p.parse_args()

    data_dir = args.data_dir or os.environ.get("VIKI_DATA_DIR") or os.path.join(_REPO_ROOT, "data")
    data_dir = os.path.abspath(data_dir)
    seed_path = os.path.abspath(args.file)

    if not os.path.isfile(seed_path):
        print(f"seed_knowledge: missing file {seed_path}", file=sys.stderr)
        return 1

    lm = LearningModule(data_dir)
    msg = lm.import_lessons_from_jsonl(
        seed_path,
        reinforce=args.reinforce,
        source_task="knowledge_seed.jsonl",
    )
    print(msg)
    print(f"data_dir={data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
