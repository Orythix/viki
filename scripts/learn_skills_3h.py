"""
Continuous 3-Hour Skill Knowledge Ingestion Script for VIKI.

This script loops over all builtin skill definition files in `src/viki/skills/builtins/`,
performs static AST analysis to extract local usage definitions (name, docstring, parameters),
and queries the internet (via DuckDuckGo) for best practices and tutorials on the
underlying technology behind each skill.

It saves these as lessons in VIKI's SQLite knowledge database, preparing the Neural Forge
to build a model that is highly proficient in using its own skill suite.

Usage:
  # Run for 3 hours (default) across all skills:
  python scripts/learn_skills_3h.py --duration-hours 3

  # Run a quick trial (e.g. 2 minutes) for a subset:
  python scripts/learn_skills_3h.py --duration-hours 0.03
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from viki.core.knowledge_ingestion import LearningModule  # noqa: E402
from viki.skills.builtins.research_skill import HAS_DDG, ResearchSkill  # noqa: E402

# Mapping of specific skills to high-quality technical search queries
SKILL_QUERY_MAPPING: dict[str, list[str]] = {
    "autonomous_auditor_skill": [
        "automated code review techniques static analysis",
        "llm as a judge software quality audit",
    ],
    "browser_skill": [
        "playwright python web scraping tutorial",
        "crawling javascript rendered pages dynamic content",
    ],
    "cache_pilot_skill": [
        "redis caching design patterns and eviction policies",
        "memcached vs redis performance comparison",
    ],
    "calendar_skill": [
        "python icalendar parsing and rrule generation",
        "google calendar API integration python guide",
    ],
    "code_search_skill": [
        "bm25 vs vector search code retrieval",
        "ripgrep performance search index architecture",
    ],
    "coding_workflow_skill": [
        "refactoring large codebases clean code guidelines",
        "test driven development tdd workflow python",
    ],
    "computer_use_skill": [
        "anthropic computer use API documentation",
        "OSWorld agent benchmark OS interaction",
    ],
    "context_weaver_skill": [
        "managing long context windows in llms",
        "vector database memory retrieval systems",
    ],
    "crypto_mining_skill": [
        "monero randomx proof of work protocol",
        "how mining pools communicate stratum protocol",
    ],
    "data_analysis_skill": [
        "pandas data processing workflows python",
        "numpy vectorization performance tips",
    ],
    "dev_skill": [
        "python package management pyproject toml setup",
        "writing robust unit tests pytest mock",
    ],
    "endpoint_guard_skill": [
        "web API rate limiting and security headers",
        "protecting endpoints against OWASP top 10",
    ],
    "filesystem_skill": [
        "python pathlib operating system path manipulation",
        "handling concurrent file writes python locks",
    ],
    "interpreter_skill": [
        "sandboxing python code execution safely",
        "python AST abstract syntax tree dynamic evaluation",
    ],
    "log_voyager_skill": [
        "centralized logging ELK stack vs Grafana Loki",
        "structured logging JSON format best practices",
    ],
    "lsp_skill": [
        "language server protocol LSP integration python",
        "jedi language server autocompletion config",
    ],
    "manus_skill": [
        "multi agent system frameworks autogen crewai",
        "collaborative agent execution workflows",
    ],
    "math_skill": [
        "python numpy scipy mathematical computing",
        "symbolic math sympy python tutorial",
    ],
    "memory_skill": [
        "episodic vs semantic memory systems in AI agents",
        "hierarchical memory architectures for agent planning",
    ],
    "mutation_pilot_skill": [
        "mutation testing software engineering coverage",
        "cosmic-ray python mutation test guide",
    ],
    "obsidian_skill": [
        "obsidian local REST API automation",
        "markdown knowledge graph management obsidian",
    ],
    "pdf_skill": [
        "python pypdf pdfplumber text extraction",
        "processing scanned pdf layout analysis OCR",
    ],
    "recall_skill": [
        "information retrieval systems tf-idf vs embeddings",
        "hybrid search indexing database strategies",
    ],
    "research_skill": [
        "duckduckgo search API documentation search scraping",
        "crawling search engines without rate limits",
    ],
    "security_skill": [
        "static application security testing sast tools python",
        "dependency vulnerability scanning pip-audit safety",
    ],
    "shell_skill": [
        "powershell core scripting windows administration",
        "bash scripting advanced syntax guide",
    ],
    "spreadsheet_skill": [
        "python openpyxl reading writing excel spreadsheets",
        "pandas read_excel write_excel tips",
    ],
    "summarize_skill": [
        "text summarization algorithms bart pegasus llm",
        "extractive vs abstractive text summarization",
    ],
    "system_control_skill": [
        "windows win32gui window management process control",
        "cross platform process monitoring psutil python",
    ],
    "tasks_skill": [
        "kanban task management data structures",
        "to-do task list orchestration software architecture",
    ],
    "time_skill": [
        "python datetime timezone handling zoneinfo pytz",
        "cron expression parsing and job scheduling python",
    ],
    "website_skill": [
        "html parsing beautifulsoup4 lxml selectors python",
        "http requests aiohttp curl authentication headers",
    ],
}


class LearningBridge:
    def __init__(self, learning: LearningModule):
        self.learning = learning
        self.air_gap = False


def analyze_skill_file(filepath: Path) -> tuple[str, str, dict[str, Any]] | None:
    """
    Parses a python skill file statically using AST.
    Avoids dynamic imports to prevent missing dependency crashes on host systems.
    """
    try:
        content = filepath.read_text(encoding="utf-8")
        node = ast.parse(content)

        for item in node.body:
            if isinstance(item, ast.ClassDef):
                # We target class inheriting from BaseSkill or ending with 'Skill'
                is_skill = any(isinstance(b, ast.Name) and b.id == "BaseSkill" for b in item.bases)
                if not is_skill and not item.name.endswith("Skill"):
                    continue

                class_name = item.name
                docstring = ast.get_docstring(item) or ""
                properties: dict[str, Any] = {}

                # Look for name, description, schema properties or methods
                for subitem in item.body:
                    if isinstance(subitem, ast.FunctionDef):
                        func_name = subitem.name
                        if func_name in ["name", "description", "schema"]:
                            # Find the return statement
                            for stmt in subitem.body:
                                if isinstance(stmt, ast.Return) and stmt.value:
                                    try:
                                        # Safely evaluate literal return values (e.g. string, dict)
                                        properties[func_name] = ast.literal_eval(stmt.value)
                                    except Exception:
                                        # If not a literal, save representation
                                        properties[func_name] = ast.unparse(stmt.value)

                return class_name, docstring, properties
    except Exception as e:
        print(f"  Warning: Failed to parse {filepath.name}: {e}")
    return None


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Multi-Skill Knowledge Learning loop for VIKI.")
    parser.add_argument(
        "--duration-hours",
        type=float,
        default=3.0,
        help="Target runtime duration in hours (default: 3.0)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Custom database data directory path",
    )
    args = parser.parse_args()

    if not HAS_DDG:
        print("ERROR: DDG search package not available. Run: pip install ddgs", file=sys.stderr)
        return 1

    # Resolve Data Directory
    if args.data_dir:
        data_path = Path(args.data_dir).resolve()
    else:
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

    skills_dir = REPO_ROOT / "src" / "viki" / "skills" / "builtins"
    if not skills_dir.is_dir():
        print(f"ERROR: skills directory not found: {skills_dir}", file=sys.stderr)
        return 1

    skill_files = sorted(skills_dir.glob("*.py"))
    skill_files = [f for f in skill_files if f.name != "__init__.py"]

    if not skill_files:
        print(f"ERROR: No python skill files found in {skills_dir}", file=sys.stderr)
        return 1

    print("=== VIKI Multi-Skill Self-Learning ===")
    print(f"Skills Directory: {skills_dir}")
    print(f"Detected Skills : {len(skill_files)}")
    print(f"Data Directory  : {data_path}")
    print(f"Target Duration : {args.duration_hours} hours ({args.duration_hours * 60:.1f} minutes)")

    learning = LearningModule(str(data_path))
    bridge = LearningBridge(learning)
    research = ResearchSkill(controller=bridge)

    start_time = time.time()
    duration_seconds = args.duration_hours * 3600
    lessons_before = learning.get_total_lesson_count()
    queries_run = 0
    skills_processed = 0

    # Calculate time allocated per skill
    time_per_skill = duration_seconds / len(skill_files)
    print(
        f"Time allocated per skill: {time_per_skill:.1f} seconds (~{time_per_skill / 60:.1f} minutes)\n"
    )

    try:
        for filepath in skill_files:
            elapsed = time.time() - start_time
            if elapsed >= duration_seconds:
                print("\nTarget duration reached. Exiting learning loop.")
                break

            skill_start = time.time()
            skills_processed += 1
            print(
                f"\n[{skills_processed}/{len(skill_files)}] Processing Skill file: {filepath.name}"
            )

            # Step 1: Static AST Analysis
            result = analyze_skill_file(filepath)
            if not result:
                continue

            class_name, docstring, props = result
            skill_name = props.get("name") or filepath.stem.replace("_skill", "")
            description = props.get("description") or docstring.split("\n")[0] or "No description"
            schema = props.get("schema") or {}

            # Save static analysis definitions into SQLite knowledge database
            await asyncio.to_thread(
                learning.save_lesson,
                trigger=f"SKILL_SPEC: How does the '{skill_name}' skill work?",
                fact=(
                    f"The '{skill_name}' skill (Python class: {class_name}) is defined as: {description}. "
                    f"Class docstring: {docstring}. Schema parameter structure: {json.dumps(schema)}"
                ),
                source=filepath.name,
                source_task="static_analysis",
            )
            print("  Saved local skill specification facts to database.")

            # Step 2: Formulate Web Search Queries
            queries = []
            if filepath.stem in SKILL_QUERY_MAPPING:
                queries.extend(SKILL_QUERY_MAPPING[filepath.stem])
            else:
                queries.append(f"how to use {skill_name} in programming python")
                queries.append(f"{skill_name} library documentation tutorial")

            # Execute web searches during the skill's time slot
            for query in queries:
                # Check overall time constraint
                if time.time() - start_time >= duration_seconds:
                    break

                # Check if we exceeded this skill's time budget
                if time.time() - skill_start >= time_per_skill:
                    print(f"  Time budget for {skill_name} reached. Moving to next skill.")
                    break

                queries_run += 1
                rem_sec = max(0.0, duration_seconds - (time.time() - start_time))
                time_str = f"[{int((time.time() - start_time) // 60)}m elapsed | {int(rem_sec // 60)}m remaining]"
                print(f"  {time_str} ({queries_run}) Searching: '{query}'")

                try:
                    res_text = await asyncio.wait_for(
                        research.execute({"query": query}), timeout=40.0
                    )
                    if (
                        "No results found" in res_text
                        or "Error" in res_text
                        or "Safety Block" in res_text
                    ):
                        print(f"    skip: {res_text[:80]}...")
                    else:
                        print("    ok (injected lessons from search summaries)")
                except Exception as e:
                    print(f"    error: {e}")

                # Sleep to pace search requests
                delay = random.uniform(6.0, 12.0)
                await asyncio.sleep(delay)

            # Ensure we fill the remaining time slot for this skill (rate-limiting buffer)
            skill_elapsed = time.time() - skill_start
            remaining_slot = time_per_skill - skill_elapsed
            if remaining_slot > 0 and (time.time() - start_time) < duration_seconds:
                print(f"  Pacing delay. Waiting {remaining_slot:.1f}s before next skill...")
                await asyncio.sleep(remaining_slot)

    except KeyboardInterrupt:
        print("\n\nSelf-learning loop interrupted by user.")

    # Final summary report
    lessons_after = learning.get_total_lesson_count()
    delta = lessons_after - lessons_before
    elapsed_total = time.time() - start_time

    print("\n" + "=" * 50)
    print("SKILL INGESTION RUN COMPLETE")
    print("=" * 50)
    print(
        f"Total Run Time      : {int(elapsed_total // 3600)}h {int((elapsed_total % 3600) // 60)}m {int(elapsed_total % 60)}s"
    )
    print(f"Skills Processed    : {skills_processed}/{len(skill_files)}")
    print(f"Web Queries Run     : {queries_run}")
    print(f"Lessons Before Run  : {lessons_before}")
    print(f"Lessons After Run   : {lessons_after}")
    print(f"New Lessons Ingested: {delta}")
    print("=" * 50)
    print("Next step - bake these lessons into the default default model profile:")
    print("  python scripts/build_viki_model.py")
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
