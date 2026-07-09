"""Helper functions extracted from orchestrator.py to reduce file size."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, cast

import yaml

logger = logging.getLogger(__name__)


def write_json(path: str, payload: Any, indent: int | None = None) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=indent, default=str)


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text_truncated(path: str, max_len: int) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read(max_len)


def load_yaml(path: str) -> dict[str, Any]:
    try:
        with open(path) as f:
            return cast("dict[str, Any]", yaml.safe_load(f))
    except (OSError, yaml.YAMLError, FileNotFoundError) as e:
        logger.warning("Failed to load YAML config from %s: %s", path, e)
        return {}


def persona_from_soul_path(soul_path: str) -> str:
    if not soul_path:
        return "sovereign"
    base = os.path.basename(soul_path)
    if "personas" in soul_path and base.endswith(".yaml"):
        return base[:-5]
    return "sovereign"


def json_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def is_explanation_requested(input_text: str) -> bool:
    triggers = {
        "explain",
        "why",
        "how does",
        "what does",
        "describe",
        "clarify",
        "elaborate",
        "break down",
        "in detail",
        "walk me through",
        "tell me about",
    }
    lower = input_text.lower().strip()
    return any(lower.startswith(t) or f" {t}" in lower or lower.endswith(t) for t in triggers)


_LAZY_SKILL_SPECS = [
    (
        "look_at_screen",
        "Capture and describe screen content.",
        "viki.skills.builtins.vision_skill",
        "VisionSkill",
        False,
        "safe",
    ),
    (
        "python_interpreter",
        "Execute Python in a sandbox.",
        "viki.skills.builtins.interpreter_skill",
        "InterpreterSkill",
        True,
        "medium",
    ),
    (
        "browser",
        "Headless browser navigation and scraping.",
        "viki.skills.builtins.browser_skill",
        "BrowserSkill",
        False,
        "medium",
    ),
    (
        "swarm_control",
        "Multi-agent swarm orchestration.",
        "viki.skills.builtins.swarm_skill",
        "SwarmSkill",
        True,
        "medium",
    ),
    (
        "draw_overlay",
        "Floating overlay UI.",
        "viki.skills.builtins.overlay_skill",
        "OverlaySkill",
        False,
        "safe",
    ),
    (
        "short_video_agent",
        "Generate short videos.",
        "viki.skills.builtins.short_video_skill",
        "ShortVideoSkill",
        True,
        "safe",
    ),
    (
        "calendar",
        "Google Calendar integration.",
        "viki.skills.builtins.calendar_skill",
        "CalendarSkill",
        True,
        "safe",
    ),
    ("email", "Gmail integration.", "viki.skills.builtins.email_skill", "EmailSkill", True, "safe"),
    (
        "messaging",
        "Unified messaging across Discord/Telegram/etc.",
        "viki.skills.builtins.messaging_skill",
        "UnifiedMessagingSkill",
        True,
        "safe",
    ),
    (
        "twitter",
        "Twitter/X integration.",
        "viki.skills.builtins.twitter_skill",
        "TwitterSkill",
        False,
        "safe",
    ),
    (
        "summarize",
        "Summarize long text/web pages.",
        "viki.skills.builtins.summarize_skill",
        "SummarizeSkill",
        True,
        "safe",
    ),
    (
        "image_gen",
        "Generate images.",
        "viki.skills.builtins.image_gen_skill",
        "ImageGenSkill",
        False,
        "safe",
    ),
    (
        "obsidian",
        "Obsidian vault notes.",
        "viki.skills.builtins.obsidian_skill",
        "ObsidianSkill",
        True,
        "safe",
    ),
    (
        "tasks",
        "Task list management.",
        "viki.skills.builtins.tasks_skill",
        "TasksSkill",
        True,
        "safe",
    ),
    (
        "whisper",
        "Audio transcription.",
        "viki.skills.builtins.whisper_skill",
        "WhisperSkill",
        True,
        "safe",
    ),
    (
        "pdf",
        "PDF reading and extraction.",
        "viki.skills.builtins.pdf_skill",
        "PdfSkill",
        True,
        "safe",
    ),
    (
        "smart_home",
        "Smart-home device control.",
        "viki.skills.builtins.smart_home_skill",
        "SmartHomeSkill",
        False,
        "medium",
    ),
    ("gif", "GIF generation.", "viki.skills.builtins.gif_skill", "GifSkill", False, "safe"),
    (
        "data_analysis",
        "DataFrame analysis.",
        "viki.skills.builtins.data_analysis_skill",
        "DataAnalysisSkill",
        True,
        "safe",
    ),
    (
        "presentation",
        "Slide deck generation.",
        "viki.skills.builtins.presentation_skill",
        "PresentationSkill",
        True,
        "safe",
    ),
    (
        "spreadsheet",
        "Spreadsheet generation/editing.",
        "viki.skills.builtins.spreadsheet_skill",
        "SpreadsheetSkill",
        True,
        "safe",
    ),
    (
        "website",
        "Website scaffolding/editing.",
        "viki.skills.builtins.website_skill",
        "WebsiteSkill",
        True,
        "safe",
    ),
    (
        "code_search",
        "Repository code search.",
        "viki.skills.builtins.code_search_skill",
        "CodeSearchSkill",
        True,
        "safe",
    ),
    (
        "plan_edit",
        "Multi-file plan-edit-verify loop.",
        "viki.skills.builtins.plan_edit_skill",
        "PlanEditSkill",
        True,
        "medium",
    ),
    (
        "computer_use",
        "Vision-grounded UI automation.",
        "viki.skills.builtins.computer_use_skill",
        "ComputerUseSkill",
        True,
        "medium",
    ),
    (
        "analyze_image",
        "Image OCR, properties, format conversion, and vision-LLM description.",
        "viki.skills.builtins.img_analysis_skill",
        "ImageAnalysisSkill",
        False,
        "safe",
    ),
    (
        "test_gen",
        "Generate pytest test stubs from Python source files.",
        "viki.skills.builtins.test_gen_skill",
        "TestGenSkill",
        False,
        "safe",
    ),
    (
        "autonomous_auditor",
        "Performs deep security and architectural audits of files.",
        "viki.skills.builtins.autonomous_auditor_skill",
        "AutonomousAuditorSkill",
        True,
        "medium",
    ),
    (
        "cache_pilot",
        "Manages the semantic cache: stats, list, prune, warm.",
        "viki.skills.builtins.cache_pilot_skill",
        "CachePilotSkill",
        True,
        "safe",
    ),
    (
        "context_weaver",
        "Manages pinned code context for RAG: pin, unpin, list, clear, expand.",
        "viki.skills.builtins.context_weaver_skill",
        "ContextWeaverSkill",
        True,
        "safe",
    ),
    (
        "data_mining",
        "Extract patterns and structured info from raw data or the web.",
        "viki.skills.builtins.data_mining_skill",
        "DataMiningSkill",
        True,
        "safe",
    ),
    (
        "engineering_playbook",
        "Structured engineering workflows: spec, plan, build, test, review, ship.",
        "viki.skills.builtins.engineering_playbook_skill",
        "EngineeringPlaybookSkill",
        True,
        "safe",
    ),
    (
        "log_voyager",
        "Analyzes system telemetry and logs for root-cause analysis.",
        "viki.skills.builtins.log_voyager_skill",
        "LogVoyagerSkill",
        True,
        "safe",
    ),
    (
        "manus",
        "Autonomous task delivery agent in a sandboxed Ubuntu environment.",
        "viki.skills.builtins.manus_skill",
        "ManusSkill",
        True,
        "medium",
    ),
    (
        "market_explorer",
        "End-to-end market research agent that browses, analyzes, and reports.",
        "viki.skills.builtins.market_explorer_skill",
        "MarketExplorerSkill",
        True,
        "safe",
    ),
    (
        "megatron_lm_playbook",
        "Megatron-LM repository agent skills: containers, uv, CI, Slurm, training.",
        "viki.skills.builtins.megatron_lm_playbook_skill",
        "MegatronLmPlaybookSkill",
        True,
        "safe",
    ),
    (
        "mind_trace",
        "Visualizes VIKI cognitive trace and routing decisions.",
        "viki.skills.builtins.mind_trace_skill",
        "MindTraceSkill",
        True,
        "safe",
    ),
    (
        "mutation_pilot",
        "Mutation testing and autonomous healing for code quality.",
        "viki.skills.builtins.mutation_pilot_skill",
        "MutationPilotSkill",
        True,
        "safe",
    ),
    (
        "reverse_engineering",
        "Binary analysis and reverse engineering tools.",
        "viki.skills.builtins.reverse_engineering_skill",
        "ReverseEngineeringSkill",
        True,
        "medium",
    ),
    (
        "crypto_mining",
        "Bitcoin and cryptocurrency mining tools.",
        "viki.skills.builtins.crypto_mining_skill",
        "CryptoMiningSkill",
        True,
        "medium",
    ),
]


def _build_env_overrides() -> dict[str, object]:
    """Read VIKI_* environment variables and return a flat dict of override values."""
    import os

    overrides: dict[str, object] = {}

    if os.environ.get("VIKI_DATA_DIR"):
        overrides["data_dir"] = os.path.abspath(os.path.expanduser(os.environ["VIKI_DATA_DIR"]))
    if os.environ.get("VIKI_WORKSPACE_DIR"):
        overrides["workspace_dir"] = os.path.abspath(
            os.path.expanduser(os.environ["VIKI_WORKSPACE_DIR"])
        )
    if os.environ.get("VIKI_PERSONA"):
        overrides["persona"] = os.environ["VIKI_PERSONA"].strip()

    if os.environ.get("VIKI_SHADOW_MODE", "").lower() in ("1", "true", "yes"):
        overrides["shadow_mode"] = True
    if os.environ.get("VIKI_AIR_GAP", "").lower() in ("1", "true", "yes"):
        overrides["air_gap"] = True
    if os.environ.get("VIKI_LOCAL_LLM_ONLY") is not None:
        overrides["local_llm_only"] = os.environ.get("VIKI_LOCAL_LLM_ONLY", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
    if os.environ.get("VIKI_GIT_CONTEXT", "").lower() in ("1", "true", "yes"):
        overrides["git_workspace_context"] = True
    if os.environ.get("VIKI_LOW_RESOURCE", "").lower() in ("1", "true", "yes"):
        overrides["low_resource_mode"] = True
    if os.environ.get("VIKI_SESSION_USAGE_LOG") is not None:
        overrides["session_usage_log"] = os.environ.get(
            "VIKI_SESSION_USAGE_LOG", ""
        ).strip().lower() in ("1", "true", "yes")
    if os.environ.get("VIKI_AUTO_WEB_RESEARCH") is not None:
        overrides["auto_web_research_when_uncertain"] = os.environ.get(
            "VIKI_AUTO_WEB_RESEARCH", ""
        ).strip().lower() in ("1", "true", "yes", "on")
    if os.environ.get("VIKI_BIO_WEBCAM") is not None:
        overrides["bio_webcam_enabled"] = os.environ.get("VIKI_BIO_WEBCAM", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

    return overrides


def _build_env_nested_overrides() -> dict[str, dict[str, object]]:
    """Read VIKI_* env vars that map into nested config sections."""
    import os

    overrides: dict[str, dict[str, object]] = {}

    if os.environ.get("VIKI_ENDPOINT_GUARD") is not None:
        raw = os.environ["VIKI_ENDPOINT_GUARD"].strip().lower()
        val: dict[str, object] = {}
        if raw in ("1", "true", "yes", "on"):
            val["enabled"] = True
            val["auto_start_watcher"] = True
        elif raw in ("0", "false", "no", "off"):
            val["enabled"] = False
        overrides["endpoint_guard"] = val

    if os.environ.get("VIKI_BACKGROUND_EVOLUTION_AT_BOOT") is not None:
        raw = os.environ["VIKI_BACKGROUND_EVOLUTION_AT_BOOT"].strip().lower()
        overrides["forge"] = {"background_evolution_at_boot": raw in ("1", "true", "yes", "on")}

    if os.environ.get("VIKI_LESSON_EXPORT_MIN_ACCESS") is not None:
        raw = os.environ["VIKI_LESSON_EXPORT_MIN_ACCESS"].strip()
        try:
            overrides.setdefault("system", {})["lesson_export_min_access_count"] = max(1, int(raw))
        except ValueError:
            pass

    return overrides


def compress_output(text: str) -> str:
    lines = text.splitlines()
    compressed = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and "file:" not in stripped.lower():
            continue
        if stripped.startswith("```"):
            skip = not skip
            compressed.append(line)
            continue
        if skip:
            compressed.append(line)
            continue
        if stripped == "" and compressed and compressed[-1].strip() == "":
            continue
        compressed.append(line)
    return "\n".join(compressed)
