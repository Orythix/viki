import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import yaml
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from viki.core.forge_config import DEFAULT_FORGE_OUTPUT_OLLAMA_TAG
from viki.core.learning import LearningModule
from viki.core.llm import LocalLLM
from viki.skills.builtins.research_skill import ResearchSkill


FACT_PREFIX = "FACT:"
STAFF_ROLE_PREFIX = "STAFF_ROLE:"


@dataclass(frozen=True)
class TrainingConfig:
    index_url: str
    pair_size: int
    max_profiles: Optional[int]
    sleep_seconds: float


def _get_repo_root() -> str:
    # scripts/ -> repo root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_settings(settings_path: str) -> dict:
    with open(settings_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_components(settings_path: str):
    """
    Build minimal components needed for staff extraction:
    - LearningModule for persistence
    - LocalLLM for extracting FACT lines (plain text, no VIKIResponse schema)
    - ResearchSkill for fetching page content
    """
    load_dotenv()

    settings = _load_settings(settings_path)
    system = settings.get("system", {})
    data_dir = system.get("data_dir", "./data")

    models_config_path = settings.get("models_config", "viki/config/models.yaml")
    if not os.path.isabs(models_config_path):
        models_config_path = os.path.join(REPO_ROOT, models_config_path)

    models_cfg = {}
    with open(models_config_path, "r", encoding="utf-8") as f:
        models_cfg = yaml.safe_load(f) or {}

    models_root = models_cfg.get("models", {})
    default_profile_name = models_root.get("default", "viki-evolved")
    profiles = models_root.get("profiles", {})
    providers = models_root.get("providers", {})

    profile = profiles.get(default_profile_name, {})
    provider_name = profile.get("provider", "ollama")
    provider = providers.get(provider_name, {})

    local_config = {
        "type": provider.get("type", "local"),
        "base_url": provider.get("base_url", "http://127.0.0.1:11434"),
        "model_name": profile.get("model_name", DEFAULT_FORGE_OUTPUT_OLLAMA_TAG),
    }

    learning = LearningModule(data_dir=data_dir)
    llm = LocalLLM(local_config)
    research_skill = ResearchSkill(controller=None)
    return learning, llm, research_skill


def _extract_profile_urls(index_html: str, index_url: str) -> List[str]:
    soup = BeautifulSoup(index_html, "html.parser")
    hrefs = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if not href:
            continue
        hrefs.add(urljoin(index_url, href))

    profile_urls: List[str] = []
    for u in sorted(hrefs):
        parsed = urlparse(u)
        path = parsed.path or ""
        if not path.startswith("/our-team/"):
            continue

        remainder = path[len("/our-team/"):].strip("/")
        if not remainder:
            continue
        # Only accept single slug profiles, e.g. /our-team/name/ (no nested paths).
        if "/" in remainder:
            continue

        profile_urls.append(u.rstrip("/") + "/")

    # De-duplicate while preserving order
    seen = set()
    unique: List[str] = []
    for u in profile_urls:
        if u in seen:
            continue
        seen.add(u)
        unique.append(u)
    return unique


def _is_contactish(text: str) -> bool:
    # Skip obvious PII/contact patterns (emails, long digit runs).
    if "@" in text:
        return True
    if re.search(r"\b\d{8,}\b", text):
        return True
    return False


def _chunked(items: List[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _build_extraction_prompt(url_list_tag: str) -> str:
    return (
        "You are extracting staff member knowledge for VIKI memory.\n"
        "Task: For each provided staff profile page text, extract ONLY company-level, non-sensitive facts.\n"
        "Output requirements (STRICT):\n"
        "1) Output ONLY lines starting with `FACT:`.\n"
        "2) Each line must contain: FACT: STAFF_ROLE: <Name> | <Role/Title> | <Key responsibilities> | <Key skills/experience>\n"
        "3) Do NOT include email, phone, addresses, or any contact details.\n"
        "4) Do NOT guess. If a detail isn't present, omit it.\n"
        f"5) Profile pages in this batch: {url_list_tag}\n"
        "6) If extraction yields nothing for a page, output nothing for that page.\n"
    )


def _truncate_page_sections(urls: List[str], contents: List[object], max_chars: int = 3500) -> List[str]:
    truncated_sections: List[str] = []
    for u, c in zip(urls, contents):
        if isinstance(c, Exception) or not c:
            continue
        text = str(c)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...(truncated)"
        truncated_sections.append(f"--- PAGE: {u} ---\n{text}\n")
    return truncated_sections


def _parse_fact_lines(model_output: str) -> List[str]:
    facts: List[str] = []
    for line in str(model_output).splitlines():
        line = line.strip()
        if not line.startswith(FACT_PREFIX):
            continue
        fact = line[len(FACT_PREFIX) :].strip()
        if not fact:
            continue
        if _is_contactish(fact):
            continue
        facts.append(fact)
    return facts


async def _train_one_batch(learning: LearningModule, llm: LocalLLM, research_skill: ResearchSkill, urls: List[str], batch_idx: int, total: int) -> List[str]:  #NOSONAR
    url_list_tag = ", ".join(urls)
    prompt = _build_extraction_prompt(url_list_tag=url_list_tag)

    # 1) Fetch page content (no LLM calls)
    contents = await asyncio.gather(
        *[research_skill.execute({"url": u}) for u in urls],
        return_exceptions=True,
    )

    # 2) Truncate to keep prompts bounded
    truncated_sections = _truncate_page_sections(urls=urls, contents=contents, max_chars=3500)

    if not truncated_sections:
        print(f"[{batch_idx}/{total}] No page text retrieved; skipping.")
        return []

    user_prompt = prompt + "\n\n" + "\n".join(truncated_sections)
    messages = [
        {"role": "system", "content": "Return only plain text."},
        {"role": "user", "content": user_prompt},
    ]

    # 3) Extract facts via local LLM (plain text, no VIKI schema)
    response = await llm.chat(messages, temperature=0.0)
    facts = _parse_fact_lines(model_output=str(response))

    # Persist facts deterministically so even if the normal auto-learning skips some, we still store staff facts.
    # LearningModule.save_lesson de-duplicates by lesson id.
    for fact in facts:
        if fact.startswith(STAFF_ROLE_PREFIX):
            staff_fact = fact[len(STAFF_ROLE_PREFIX) :].strip()
            learning.save_lesson(
                trigger="STAFF_ROLE",
                fact=staff_fact,
                source_task="WeMakePlatformsStaff",
            )

            # Also store tenant "operating procedure" fragments as durable playbooks.
            # Extract responsibilities into an event/club playbook lesson that can guide future Ops planning.
            try:
                parts = [p.strip() for p in staff_fact.split("|")]
                # Expected: <Name> | <Role/Title> | <Responsibilities> | <Skills/Experience>
                if len(parts) >= 3:
                    role_title = parts[1] if len(parts) > 1 else parts[0]
                    responsibilities = parts[2]
                    skills = parts[3] if len(parts) > 3 else ""
                    playbook = f"{role_title} — responsibilities: {responsibilities}"
                    if skills:
                        playbook += f" | skills: {skills}"
                    learning.save_lesson(
                        trigger="EVENT_PLAYBOOK",
                        fact=playbook[:700],
                        source_task="WeMakePlatformsStaff:Playbook",
                    )
            except Exception:
                # Best-effort parsing; never fail the whole batch because one line is malformed.
                pass
        else:
            # For safety, ignore non-STAF_ROLE facts from the extraction step.
            continue

    print(f"[{batch_idx}/{total}] Stored {len(facts)} staff FACT lines from {len(urls)} URL(s).")
    return facts


async def main():
    parser = argparse.ArgumentParser(description="Train VIKI memory on WeMakePlatforms staff pages.")
    parser.add_argument("--index-url", default="https://www.wemakeplatforms.io/our-team")
    parser.add_argument("--pair-size", type=int, default=2, help="How many profile URLs per request (VIKI fetches up to 2).")
    parser.add_argument("--max-profiles", type=int, default=0, help="0 means all profiles.")
    parser.add_argument("--sleep-seconds", type=float, default=0.5, help="Delay between batches.")
    args = parser.parse_args()

    max_profiles = None if args.max_profiles <= 0 else args.max_profiles
    cfg = TrainingConfig(
        index_url=args.index_url,
        pair_size=max(1, args.pair_size),
        max_profiles=max_profiles,
        sleep_seconds=max(0.0, args.sleep_seconds),
    )

    print(f"Fetching staff index: {cfg.index_url}")
    resp = requests.get(cfg.index_url, timeout=30)
    resp.raise_for_status()
    profile_urls = _extract_profile_urls(resp.text, cfg.index_url)

    if cfg.max_profiles is not None:
        profile_urls = profile_urls[: cfg.max_profiles]

    print(f"Discovered {len(profile_urls)} staff profile URLs.")
    if not profile_urls:
        return

    settings_path = os.path.join(REPO_ROOT, "viki", "config", "settings.yaml")
    learning, llm, research_skill = _build_components(settings_path)

    print("Starting staff training (this may take a while)...")
    batches = list(_chunked(profile_urls, cfg.pair_size))
    total = len(batches)
    for i, urls in enumerate(batches, start=1):
        await _train_one_batch(
            learning=learning,
            llm=llm,
            research_skill=research_skill,
            urls=urls,
            batch_idx=i,
            total=total,
        )
        if cfg.sleep_seconds:
            await asyncio.sleep(cfg.sleep_seconds)


if __name__ == "__main__":
    asyncio.run(main())

