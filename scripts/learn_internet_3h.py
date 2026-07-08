"""
Continuous 3-Hour Internet Knowledge Ingestion Script for VIKI.

This script searches the web for a series of software engineering, system design,
and general AI topics, automatically extracting and saving lessons to VIKI's SQLite
knowledge database. It includes a dynamic discovery loop that harvests new keywords
from search summaries to expand its topic queue on the fly.

To avoid IP rate limiting/banning by search engines, it uses randomized delays.

Usage:
  # Run for 3 hours (default) using built-in seed topics:
  python scripts/learn_internet_3h.py --duration-hours 3

  # Run for a short trial (e.g. 5 minutes) to test:
  python scripts/learn_internet_3h.py --duration-hours 0.08
"""

from __future__ import annotations

import argparse
import asyncio
import random
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from viki.core.knowledge_ingestion import LearningModule  # noqa: E402
from viki.skills.builtins.research_skill import HAS_DDG, ResearchSkill  # noqa: E402

# Seed topics to kick off the learning process if no custom topics are provided
DEFAULT_SEEDS = [
    # System Design & Architecture
    "microservices design patterns and trade-offs",
    "eventual consistency vs strong consistency in distributed databases",
    "how raft consensus algorithm works",
    "horizontal scaling vs vertical scaling systems",
    "caching strategies write-through write-back cache-aside",
    "rate limiting algorithms token bucket leaky bucket",
    "rest vs graphql vs grpc API comparison",
    "message queues rabbitmq activemq vs kafka",
    # Advanced Python
    "python 3.12 new feature highlights",
    "python asyncio event loop internals design",
    "python memory management reference counting garbage collection",
    "metaprogramming in python decorators and metaclasses",
    "optimizing python code performance with cython and cffi",
    # Web & Frontend
    "angular 18 standalone components best practices",
    "how angular zone.js handles change detection",
    "optimizing web vital metrics lcp fid cls",
    "server side rendering ssr vs static site generation ssg",
    "react server components rsc architecture guide",
    # Databases & Storage
    "postgres indexing types btree hash gin gist",
    "database transaction isolation levels read committed serializable",
    "nosql vs sql database choosing guide",
    "redis data structures hashes sets sorted sets",
    # AI & Machine Learning
    "retrieval augmented generation rag best practices",
    "direct preference optimization dpo vs rlhf",
    "large language model quantization methods gptq awq gguf",
    "how vector embeddings search indexing works",
    "transformer architecture self attention mechanism explained",
    # Devops & Infrastructure
    "docker multi stage builds best practices",
    "kubernetes architecture control plane worker nodes",
    "ci cd pipeline security hardening techniques",
    "monitoring and logging stack prometheus grafana loki",
]


class LearningBridge:
    """Bridges ResearchSkill callbacks to the LearningModule."""

    def __init__(self, learning: LearningModule):
        self.learning = learning
        self.air_gap = False


def extract_new_keywords(text: str) -> list[str]:
    """
    Scans search snippets for capitalized terms or technology names
    to dynamically discover new subtopics.
    """
    # Look for capitalized word sequences (2-3 words) that might represent techs/concepts
    candidates = re.findall(r"\b[A-Z][a-zA-Z0-9]{2,15}(?:\s+[A-Z][a-zA-Z0-9]{2,15}){1,2}\b", text)
    valid_keywords = []

    # Filter out common false positives and lowercase them to normalize
    for kw in candidates:
        kw_clean = kw.strip()
        lower_kw = kw_clean.lower()
        if any(w in lower_kw for w in ["source:", "http", "result", "the", "this", "url"]):
            continue
        if len(kw_clean) > 8 and kw_clean not in valid_keywords:
            valid_keywords.append(kw_clean)

    return valid_keywords


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Continuous Web Knowledge Ingestion for VIKI.")
    parser.add_argument(
        "--duration-hours",
        type=float,
        default=3.0,
        help="Duration to run the learning process (default: 3.0 hours)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Custom VIKI data directory path",
    )
    parser.add_argument(
        "--custom-seed-file",
        type=str,
        default=None,
        help="Path to a text file containing one seed query per line",
    )
    args = parser.parse_args()

    if not HAS_DDG:
        print("ERROR: DDG search package not available. Run: pip install ddgs", file=sys.stderr)
        return 1

    # Resolve Data Directory
    if args.data_dir:
        data_path = Path(args.data_dir).resolve()
    else:
        # Try importing from settings
        try:
            import yaml

            settings_path = REPO_ROOT / "config" / "settings.yaml"
            with settings_path.open("r", encoding="utf-8") as f:
                settings = yaml.safe_load(f) or {}
            rel_dir = (settings.get("system") or {}).get("data_dir") or "./data"
            data_path = Path(rel_dir)
            if not data_path.is_absolute():
                data_path = (REPO_ROOT / data_path).resolve()
        except Exception:
            data_path = (REPO_ROOT / "data").resolve()

    print("=== VIKI Continuous Knowledge Ingestion ===")
    print(f"Data Directory : {data_path}")
    print(f"Target Duration: {args.duration_hours} hours ({args.duration_hours * 60:.1f} minutes)")

    learning = LearningModule(str(data_path))
    bridge = LearningBridge(learning)
    research = ResearchSkill(controller=bridge)

    # Initialize topic queue
    queue: list[str] = []
    if args.custom_seed_file:
        seed_file = Path(args.custom_seed_file)
        if seed_file.is_file():
            queue.extend(
                ln.strip()
                for ln in seed_file.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            )
            print(f"Loaded {len(queue)} seeds from {seed_file.name}")
        else:
            print(f"ERROR: custom seed file not found: {args.custom_seed_file}", file=sys.stderr)
            return 1
    else:
        queue.extend(DEFAULT_SEEDS)
        print(f"Using {len(queue)} built-in seed topics.")

    # Shuffle seeds for random distribution
    random.shuffle(queue)
    visited_topics: set[str] = set()

    # Time tracking
    start_time = time.time()
    duration_seconds = args.duration_hours * 3600
    queries_run = 0
    lessons_added_before = learning.get_total_lesson_count()

    print("Starting ingestion loop. Press Ctrl+C to terminate early.\n")

    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed >= duration_seconds:
                print("\nTarget duration reached. Stopping ingestion loop.")
                break

            if not queue:
                print("\nTopic queue empty! Refilling with seeds.")
                queue.extend(DEFAULT_SEEDS)
                random.shuffle(queue)

            # Dequeue next topic
            topic = queue.pop(0).strip()
            if not topic or topic.lower() in visited_topics:
                continue

            visited_topics.add(topic.lower())
            queries_run += 1

            # Format time status
            rem_sec = max(0.0, duration_seconds - elapsed)
            time_str = f"[{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m elapsed | {int(rem_sec // 3600)}h {int((rem_sec % 3600) // 60)}m remaining]"

            print(f"\n{time_str} ({queries_run}) Searching: '{topic}'")

            try:
                # Execute web research
                results_text = await asyncio.wait_for(
                    research.execute({"query": topic}), timeout=45.0
                )

                # Check for rate-limiting blocks or errors
                if (
                    "No results found" in results_text
                    or "Error" in results_text
                    or "Safety Block" in results_text
                ):
                    print(f"  Result: {results_text[:120]}...")
                else:
                    # Dynamically discover new subtopics from search summaries
                    new_kws = extract_new_keywords(results_text)
                    added_count = 0
                    for kw in new_kws:
                        # Build a subtopic query using discovered keyword
                        sub_topic = f"{kw} explained in software engineering"
                        if sub_topic.lower() not in visited_topics and sub_topic not in queue:
                            queue.append(sub_topic)
                            added_count += 1
                    if added_count > 0:
                        print(
                            f"  Discovered & queued {added_count} subtopics (Queue size: {len(queue)})"
                        )
                    else:
                        print("  Successfully ingested search snippets.")

            except asyncio.TimeoutError:
                print("  Timeout searching topic.")
            except Exception as e:
                print(f"  Error: {e}")

            # Safe delay to respect search engines (5 - 15 seconds)
            delay = random.uniform(8.0, 15.0)
            await asyncio.sleep(delay)

    except KeyboardInterrupt:
        print("\n\nIngestion loop interrupted by user.")

    # Final Summary Report
    lessons_added_after = learning.get_total_lesson_count()
    delta = lessons_added_after - lessons_added_before
    elapsed_total = time.time() - start_time

    print("\n" + "=" * 50)
    print("INGESTION RUN COMPLETE")
    print("=" * 50)
    print(
        f"Total Run Time     : {int(elapsed_total // 3600)}h {int((elapsed_total % 3600) // 60)}m {int(elapsed_total % 60)}s"
    )
    print(f"Queries Run        : {queries_run}")
    print(f"Lessons Before Run : {lessons_added_before}")
    print(f"Lessons After Run  : {lessons_added_after}")
    print(f"New Lessons Added  : {delta}")
    print("=" * 50)
    print("You can now build/fine-tune the model with these lessons:")
    print("  python scripts/build_viki_model.py")
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
