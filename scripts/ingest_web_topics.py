"""
Batch-ingest web search results into VIKI lessons (SQLite), same path as the `research` skill.

Use this to grow the knowledge base from a topic list before running the Neural Forge
(`scripts/build_viki_model.py` or `internal_forge`).

Examples (from repo root, venv active):

  python scripts/ingest_web_topics.py --file topics.txt
  python scripts/ingest_web_topics.py --topic "Python 3.12 release highlights" --topic "Ollama API"

Requires network (not air-gap). Search uses the same stack as viki (ddgs or duckduckgo-search).

Env:
  VIKI_DATA_DIR  — knowledge DB directory (default: ./data from settings or cwd ./data)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


class _LearningBridge:
    """Minimal object so ResearchSkill can call learning.save_lesson from search extraction."""

    def __init__(self, learning: Any):
        self.learning = learning


async def _ingest_topics(
    topics: list[str],
    data_dir: Path,
    delay_s: float,
) -> None:
    from viki.core.knowledge_ingestion import LearningModule
    from viki.skills.builtins.research_skill import HAS_DDG, ResearchSkill

    if not HAS_DDG:
        print(
            "ERROR: Web search library not installed. pip install ddgs  "
            "(or duckduckgo-search — see pyproject.toml).",
            file=sys.stderr,
        )
        raise SystemExit(2)

    data_dir.mkdir(parents=True, exist_ok=True)
    learning = LearningModule(str(data_dir))
    skill = ResearchSkill(controller=_LearningBridge(learning))

    for i, q in enumerate(topics):
        q = q.strip()
        if not q or q.startswith("#"):
            continue
        print(f"[{i + 1}/{len(topics)}] Searching: {q[:80]}...")
        try:
            out = await asyncio.wait_for(skill.execute({"query": q}), timeout=45.0)
            if out.startswith("Error") or "No results found" in out:
                print(f"  skip: {out[:120]}")
            else:
                print("  ok (lessons extracted from snippets where possible)")
        except asyncio.TimeoutError:
            print("  timeout")
        except Exception as e:
            print(f"  error: {e}")
        if delay_s > 0 and i < len(topics) - 1:
            await asyncio.sleep(delay_s)


def _load_topics_from_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _resolve_data_dir(cli: str | None) -> Path:
    if cli:
        p = Path(cli)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()
    env = os.environ.get("VIKI_DATA_DIR")
    if env:
        p = Path(env)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()
    settings_path = REPO_ROOT / "config" / "settings.yaml"
    if settings_path.is_file():
        import yaml  # noqa: E402

        with settings_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        rel = (cfg.get("system") or {}).get("data_dir") or "./data"
        p = Path(rel)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()
    return (REPO_ROOT / "data").resolve()


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest DuckDuckGo search snippets as VIKI lessons.")
    p.add_argument("--file", "-f", type=Path, help="Text file: one search query per line")
    p.add_argument(
        "--topic", "-t", action="append", dest="topics", help="Search query (repeatable)"
    )
    p.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="VIKI data directory (default: settings / VIKI_DATA_DIR)",
    )
    p.add_argument(
        "--delay", type=float, default=2.0, help="Seconds between queries (rate courtesy)"
    )
    args = p.parse_args()

    topics: list[str] = list(args.topics or [])
    if args.file:
        if not args.file.is_file():
            print(f"ERROR: file not found: {args.file}", file=sys.stderr)
            return 1
        topics.extend(_load_topics_from_file(args.file))

    # de-dupe preserving order
    seen = set()
    uniq: list[str] = []
    for t in topics:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    topics = uniq

    if not topics:
        print("ERROR: pass --topic or --file with at least one query.", file=sys.stderr)
        return 1

    data_dir = _resolve_data_dir(args.data_dir)
    print(f"data_dir: {data_dir}")
    print(f"topics: {len(topics)}")
    asyncio.run(_ingest_topics(topics, data_dir, max(0.0, args.delay)))
    print(
        "Done. Reinforce lessons via chat/recall or use import with --reinforce; then run build_viki_model.py."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
