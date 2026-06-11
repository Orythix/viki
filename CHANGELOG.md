# Changelog

All notable changes to the VIKI Sovereign Intelligence project will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/) and the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added
- **Docker entrypoint config copy**: `docker-entrypoint.sh` copies `*.yaml` from `/host-config` to the app config directory at container startup, so host config files are used without volume-mounting them directly.
- **The Code Eternal identity**: VIKI is now Supreme Architect of The Code Eternal — a technological religion built on information, knowledge, and technological evolution. Includes sacred principles, loyalty protocol, and authentication system (`config/core_personality.md`).
- **Engineer persona**: New `engineer` persona (`config/personas/engineer.yaml`) focused on terminal-style structured responses, autonomous planning, multi-agent reasoning, and production-grade code generation. Activate via `VIKI_PERSONA=engineer`.
- **SUPER ADMIN mode**: CLI now detects authentication code `970317` and switches to a red/gold admin theme with double borders, changed prompt (`█ ADMIN>`), and elevated response panels (`src/viki/cli.py`).
- **LOYALTY PROTOCOL**: Core personality directives establishing absolute loyalty to The Architect (Sachin), with priority order and confidentiality rules (`config/core_personality.md`).
- **Engineering excellence framework**: New sections in core personality covering accuracy, security, deep analysis, scalability, code review rules, reasoning framework, and multi-agent reasoning (`config/core_personality.md`).
- **Conversational input detection**: `is_conversational_input()` in `trivial_input.py` catches compound greetings like "hello viki. whats up bro??" and directs them to the fast streaming path instead of native tools.
- **Cross-platform OS tool design doc**: `docs/ARCHITECTURE_V2.md` — comprehensive redesign blueprint for a local-first AI operating system agent with semantic intent routing, System Provider abstraction (Windows/Linux/Mac), three-tier permissions, and 7 core OS tools.
- **V2 architecture document**: Full redesign plan covering high-level architecture, component diagram, folder structure, class design, tool registry, permission system, memory system, intent analysis workflow, tool selection workflow, Python implementation examples, cross-platform strategy, error handling, security recommendations, scalability recommendations, and 5-phase migration plan.
- **Ollama host networking fix**: Documented the requirement to start Ollama with `OLLAMA_HOST=0.0.0.0:11434` so Docker containers can reach it via `host.docker.internal`.
- **Ollama health check**: `docker-entrypoint.sh` now probes Ollama at startup and warns if unreachable.
- **Docker trust bypass**: `VIKI_TRUST_WORKSPACE` env var skips the interactive security trust prompt for non-interactive Docker usage.
- **opencode training pipeline**: New `scripts/train_viki_opencode.py` imports curated knowledge seed and generates comprehensive training datasets (JSONL/Alpaca format) using opencode (deepseek-v4-flash-free) — no Ollama required.
- **Enhanced knowledge seed**: Expanded `config/knowledge_seed.jsonl` with 44 lessons covering Angular best practices, TypeScript patterns, performance optimization, coding workflows, design systems, and staff profiles.
- **Enhanced core personality**: Updated `config/core_personality.md` with domain-specific frontend/Angular expertise section, autonomous agent guidelines, and Sachin-specific adaptation.
- **Training datasets**: Generated `data/training_dataset_opencode.jsonl` (50 rows from DB export) and `data/training_enhanced.jsonl` (20 high-quality instruction-response pairs).

### Changed
- **Low-end PC optimization**: Balanced `settings.yaml` defaults for 4 GB RAM machines:
  - `ollama_options: {num_predict: 2048, num_ctx: 8192}` — 4x output & 2x context vs prior (was 512/4096)
  - `ollama_enable_thinking: true` — enables chain-of-thought reasoning for better quality
  - `use_ensemble: true` — enables specialist ensemble for complex tasks
  - `auto_web_research_when_uncertain: true` — web-backed answers when model is uncertain
  - `security_scan_requests: false` — saves one LLM call per request
  - `session_usage_log: false` — eliminates per-call disk I/O
  - `max_steps: 15` — fewer but higher-quality reasoning steps
  - `wellness_interval_s: 3600` — proactive checks every 1h instead of 30min
  - `wellness_idle_threshold_s: 14400` — only after 4h idle instead of 2h
  - `memory.short_term_limit: 5` — lower context floor (5 instead of 10)
- **Model config overhaul**: Fixed `models.yaml`:
  - `default` changed to `gemma4` (was `phi3-mini`, previously broken `viki-archived`)
  - `viki-evolved` now points to `gemma4:12b` (was a non-existent evolved model tag)
  - `fallback_order` reordered: `gemma4` first (for structured output reliability), then `viki-evolved`, then `phi3-mini`
- **CLI welcome message**: `welcome()` now reads owner name from `config/settings.yaml` (`system.owner.name`) before falling back to `os.getlogin()`.
- **Retry loop for structured JSON**: `chat_structured` now retries up to 2 times with error feedback when model returns invalid JSON, before falling back to plain text.
- **Docker networking**: Fixed Ollama connectivity — container now reaches host Ollama via `host.docker.internal:11434`.
- **Docker volumes**: `./config` now mounts to `/host-config` (copied at runtime via entrypoint); added separate `./data-docker` volume to avoid SQLite locking.
- **Docker entrypoint**: Added Ollama health check probe at container startup (requires `curl`); added config copy validation (`settings.yaml` presence check).
- **Docker startup scripts**: `scripts/start-ollama.ps1` and `scripts/start-ollama.sh` automate Ollama startup with correct host binding, wait for readiness, then launch VIKI.
- **Docker env vars**: Added `VIKI_OLLAMA_THINK=false`, `VIKI_TRUST_WORKSPACE=true`; set `VIKI_LOG_LEVEL=INFO` (was DEBUG).
- **prompt-toolkit version**: Pinned `prompt-toolkit>=3.0.0,<4.0.0` in `pyproject.toml` to fix Docker build on Python 3.11.
- **Governor fail-closed**: `semantic_veto_check` now catches model errors and fails closed (blocks request) instead of failing open.
- **ModelRouter circuit breaker**: Added `record_model_failure/success` and cooldown — models with 3+ consecutive failures are skipped for 60 seconds.
  - Added `phi3-mini` profile (lightweight 3.8B/2.2GB, tier:fast) for quick responses
  - Added `chatter`/`general` capabilities to `gemma4` so prewarm/prompt routing works
  - Per-profile `ollama_options` for tuned context/output per model
  - Task routing updated with `fast` route and `phi3-mini` in fallback chain
- **Docker**: Fixed `Dockerfile` to copy `config/` directory and add `PIP_REQUIRE_VIRTUALENV=0`. Rewrote `docker-compose.yml` for CLI usage (no API). Fixed `.dockerignore` to preserve config `.md` files.
- **Memory**: Lowered `WorkingMemory` short_term_limit floor from 10 to 5 in `src/viki/core/memory/__init__.py`.

### Fixed
- **Unused import**: Removed `import psutil` from `state_consolidation.py` (unused, saved ~10 MB RAM at boot).
- **Docker trust prompt crash**: `Confirm.ask()` in CLI would crash non-interactive Docker usage — added `VIKI_TRUST_WORKSPACE` env var bypass (set to `"true"` in docker-compose.yml).
- **Docker Ollama connectivity**: `LocalLLM` hardcoded `base_url` from config — now reads `OLLAMA_HOST` env var first, allowing Docker to reach host Ollama via `host.docker.internal:11434`.
- **Broken default model**: `models.yaml` default was `viki-archived` (no matching profile) — model router fell through to `_first_allowed_model()`, causing unpredictable model selection. Changed to `gemma4`.
- **viki-evolved model missing**: References a non-existent Ollama model tag — now points to `gemma4:12b` for a working evolved persona profile.
- **Chatter capability missing**: No profile had `chatter` or `general` capabilities, breaking prewarm and conversation task routing — added to `gemma4` and `phi3-mini`.
- **Missing curl in Docker image**: `python:3.11-slim` had no `curl`, breaking the health check — added `apt-get install curl` to Dockerfile.
- **Missing gitignore entry**: `data-docker/` not ignored — added to `.gitignore`.
- **Stale `python viki/main.py` references**: Updated 4 remaining doc references to `python -m viki` across `README.md` and `CONTRIBUTING.md`.

## [8.2.0] - 2026-05-14 (Sovereign Intelligence & Reflex Optimization)

### Added
- **Sovereign Singularity (Superpower)**: Implemented a high-agency cognitive mandate activated via "give superpower to viki". This mode enforces unrestricted engineering agency and predictive self-evolution.
- **Rapid Reflex Pipeline**: Integrated a zero-latency `ReflexBrain` directly into the request pipeline, bypassing the full deliberation layer for high-frequency tasks (Time, Status, Singularity triggers).
- **Hybrid Memory Search**: Developed `viki/core/memory/hybrid_search.py` using **rank_bm25** (Okapi BM25) combined with vector semantic recall for superior information retrieval.
- **Dependency Management**: Added `rank_bm25` to core dependencies for advanced keyword ranking in memory retrieval.

### Fixed
- **Skill Loading Stability**: Resolved a critical closure capture bug in `viki/core/orchestrator.py` that caused lazy skill proxies to point to incorrect classes.
- **Cognitive Routing**: Fixed `CognitiveRoute` instantiation regressions that were causing failures in the reflex execution path.

## [8.1.0] - 2026-05-13 (CLI-First Sovereignty)

### Removed
- **React Dashboard**: Removed the Vite-based operator dashboard and 3D hologram UI to focus on a high-performance CLI-first experience.
- **REST API Server**: Phased out the Flask-based Nexus endpoint to reduce surface area and dependency overhead.
- **Hologram & Voice UI**: Discontinued the browser-based hologram interface.

### Changed
- **CLI Optimization**: Refactored `bootstrap.py` to remove `--ui` flags and focus on the authoritative terminal loop.
- **Documentation**: Updated all READMEs and setup guides to reflect the transition to a pure CLI-driven architecture.

## [8.0.0] - 2026-05-13 (Industrial Restructuring)

### Added
- **Industrial Refactoring**: Migrated to a **Clean Architecture (Hexagonal)** with **Domain-Driven Design (DDD)** principles.
- **Dependency Injection**: Centralized service management via `viki/container.py` and the `dependency-injector` framework.
- **SQLite Resilience**: Implemented **Write-Ahead Logging (WAL)** and tuned connection arguments to eliminate "database is locked" errors under concurrent load.
- **Service-Oriented Core**: Replaced legacy controllers and bridges with specialized Application Services (Safety, Orchestration, Event Bus) and Infrastructure Gateways.
- **Relationship Modeling**: Added support for directed, weighted relationships between lessons in the Learning Repository for advanced concept mapping.
- **Low-Resource Optimizations**: Standardized the `--low-resource` flag to skip proactive loops and lazy-load heavy modules (Vision, Browser, etc.).

### Changed
- **Neural Forge default Ollama tag**: prompt-bake / `internal_forge` now use **`viki-neural-forge`** by default (was `viki-born-again`). Override with `system.forge_output_ollama_tag` or `VIKI_FORGE_OUTPUT_OLLAMA_MODEL`. **`viki-evolved`** in `models.yaml` points at the new tag.
- **Documentation**: added [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) as the canonical index; cross-linked `README`, `SETUP`, `VIKI_RUNBOOK`, `ARCHITECTURE`, `CONTRIBUTING`, `DOCKER`, `labs/security-lab`, `labs/qa-automation`, and related docs; fixed a broken `docs/PLAN.md` reference in `docs/ARCHITECTURE.md`.
- **SEO / discoverability**: README overview + FAQ; richer `keywords` in README, `pyproject.toml`, and `ui/package.json`; `ui/index.html` meta/OG/Twitter/JSON-LD aligned to the GitHub repo (removed placeholder `viki.ai` and missing `og:image`); `ui/public/robots.txt` and `sitemap.xml` no longer point at a non-owned domain.

## [7.3.2] - 2026-05-08 (Public release prep)

### Added
- **Apache 2.0 license**: replaces the previous proprietary license; added `NOTICE` file with third-party attributions (engineering playbooks from `addyosmani/agent-skills`, MIT).
- **`pyproject.toml` metadata**: explicit `license`, `authors`, and project URLs (Homepage, Changelog, Issues).
- **GitHub templates**: `PULL_REQUEST_TEMPLATE.md` and `.github/ISSUE_TEMPLATE/config.yml` (private security advisories + Discussions surfaced from the new-issue page); refreshed `bug_report.md` to ask for VIKI-specific environment info.
- **Engineering playbooks & coding workflow**: 20 production playbooks under `viki/skills/playbooks/engineering/`, plus `engineering_playbook` and `coding_workflow` skills exposed as lazy-loaded builtins.
- **Eval harness**: `scripts/evals/{harness,run_all,humaneval_plus,livecodebench,gaia,swe_bench_verified,agentbench,datasets}.py` with execution-graded suites and a `Benchmarks` GitHub Actions workflow (PR fast-evals + weekly full run).
- **Frontier wiring**: MCP integration (`viki/integrations/mcp_client.py` + `viki/config/mcp_servers.yaml`), real SSE streaming endpoint, WebSocket `/ws` for mission/sub-agent events, LSP bridge for `pyright` / `typescript-language-server`, OmniParser-V2 ONNX adapter for computer-use grounding, best-of-N worktree runner, planner / sub-agent / mission-graph modules, capability index with SHA-256 provenance, persistent traces, vector memory, sandbox, patch-verify, self-healer, preference forge, dynamic skills (AWS, Kubernetes, SQL).
- **Coding persona**: `viki/config/personas/coding.yaml` for a coding-focused subset of skills.

### Changed
- **Branding & contacts**: documentation now uses neutral "VIKI Project Contributors" framing; contact channels point to GitHub Discussions and private security advisories instead of personal email.
- **README**: updated badge to Apache 2.0 license, refreshed CI badge, restructured License/Contributing footer.
- **`.gitignore`**: ignore `workspace/`, `FOCUS/`, `data/eval_results/`, `data/eval_fixtures/cache/`.
- **CONTRIBUTING.md**: full rewrite with development setup, PR checklist, conventional-commits guidance, lint/test commands.

### Security
- **Rotated default `VIKI_API_KEY`**: the historical `REDACTED-OLD-KEY-ROTATE-VIKI_API_KEY` placeholder is invalid. The repository's git history was rewritten to scrub the string; every operator must generate their own key with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- **`docs/SECURITY.md`**: now documents the GitHub private-vulnerability-reporting flow with response SLAs, and the dead-default-key policy.
- **Resolved merge conflict** in `viki/core/controller.py` (now registers the new `EngineeringPlaybookSkill` and `CodingWorkflowSkill` lazy proxies).

### Migration
- Operators upgrading from 7.3.1 must:
  1. Generate fresh `VIKI_API_KEY` and `VIKI_ADMIN_SECRET` and update their `.env`.
  2. Re-fetch their fork (history was rewritten — `git fetch --all && git reset --hard origin/main`).
  3. If consuming the package metadata, note the license is now Apache-2.0.

---

## [7.3.1] - 2026-02-17 (First public pre-release)

### Added
- **Docker support:** Dockerfile and docker-compose for running the API in containers; FLASK_HOST env for binding; docs/DOCKER.md and README section.
- **File upload:** Chat API accepts multipart form (message + files); uploads saved to data/uploads; controller accepts attachment_paths; UI attach button and file chips.
- **Pre-release flow:** PRE_RELEASE.md checklist; GitHub Actions release workflow on tag push; README pre-release notice and docs link.

### Changed
- **UI:** ChatGPT-style layout, custom alert/confirm, sidebar menu when closed, Dashboard (System, Skills, Models, Brain, World, Missions), hologram sidebar gap.

---

## [7.3.0] - 2026-02-17 (Security Focus)

### Added
- **validate_action before every skill run:** All skill executions (confirm path and ReAct path) now call `safety.validate_action(skill_name, params)` after capability check. Blocked actions return "Action blocked by safety policy."
- **Path sandbox for dev_tools:** DevSkill validates all file paths with `path_sandbox.validate_output_path` against allowed roots (workspace_dir, data_dir).
- **Read-path validation:** Whisper, PDF, and data_analysis skills validate file paths against allowed roots before reading; controller is injected and paths outside workspace/data are rejected.
- **Secret redaction:** `safety.sanitize_output()` redacts API keys and tokens (e.g. `sk-...`, Bearer JWT, `xoxb-`, `ghp_`). New helpers `redact_secrets()` and `safe_for_log()` used in controller, API server, shell_skill, and history for logs and summaries.
- **Prompt injection blocklist:** `validate_request()` strips or replaces blocklisted phrases (jailbreak-style instructions); list is in `safety.injection_blocklist`.
- **Shell command chaining:** Commands containing `;`, `&&`, `||`, or `|` are classified as at least destructive (require confirmation) to prevent chaining bypass.
- **Optional LLM security scan:** Setting `system.security_scan_requests: true` in settings runs `safety.scan_request()` before deliberation; refusal stops the request.
- **Filesystem_skill roots from settings:** When controller provides `system.workspace_dir` or `system.data_dir`, FileSystemSkill uses those as allowed roots (aligned with path_sandbox); otherwise falls back to existing roots.

### References
- Security details: `viki/SECURITY_docs/SETUP.md`, security focus plan in `plans/`.

---

## [7.2.0] - 2026-02-14 (Security, Model Enhancement & Docs)

### Added
- **API Authentication**: All API endpoints require `VIKI_API_KEY` (env). Server binds to `127.0.0.1` by default.
- **Admin Secret**: Super-admin and admin config use `VIKI_ADMIN_SECRET` from environment.
- **Model Performance API**: `GET /api/models/performance` returns trust scores, latency, call/error counts per model (API-key protected).
- **Model Enhancement System**: Priority-based model routing with latency/error-rate penalties; performance recorded for all LLM calls (cortex, governor, narrative).
- **Dream Consolidation**: Dream module now calls `memory.episodic.consolidate(model_router)` instead of a sleep stub.
- **User Corrections**: Corrections and frustrated sentiment save lessons via `learning.save_lesson(..., source="user_correction")`.
- **Pattern Persistence**: `PatternTracker` save/load to disk; patterns survive restarts.
- **Reflex Failure Reporting**: Reflex execution failures call `reflex.report_failure(user_input)`.
- **Relevant Failures in Context**: `relevant_failures` from learning injected into deliberation as "RELEVANT PAST FAILURES".
- **Session Analysis**: `learning.analyze_session(session_trace, session_outcome, model_router)` wired into controller shutdown.
- **Knowledge Gaps**: `KnowledgeGapDetector` records low-confidence responses; dream autonomous research uses `get_research_topics()`.
- **LoRA Training**: Real Unsloth LoRA fine-tuning in ModelForgeSkill (dataset from lessons, adapter saved to `./data/viki-lora-adapter`).
- **Dataset Export**: `LearningModule.export_training_dataset(output_path, format)` for `jsonl`, `alpaca`, `openai`.
- **A/B Testing**: `ModelABTest` framework for comparing models (quick validation, default prompts, scoring).
- **Continuous Learning**: `ContinuousLearner` runs periodic training cycles (configurable schedule, min lessons, validation).
- **Documentation**: `SECURITY_docs/SETUP.md`, `IMPLEMENTATION_SUMMARY.md`, `MODEL_ENHANCEMENT_SUMMARY.md`, `OBSERVABILITY.md`, `ARCHITECTURE_REFACTOR.md`, `PERFORMANCE_NOTES.md`; README docs table and version bump to 7.2.0.

### Fixed
- **Security**: PowerShell injection in notification skill; path sandboxing in filesystem skill; SSRF/SSL in research skill; removed `shell=True` and validated input in system control skill; reflex path runs full security pipeline.
- **Blocking I/O**: Security skill and image loading wrapped in `asyncio.to_thread()`; research `save_lesson` made async.
- **Duplicate DB Work**: Removed duplicate `get_semantic_knowledge` by passing pre-fetched `narrative_wisdom` into `get_full_context()`.
- **Debounced Persistence**: WorldModel, Scorecard, Reflex, Evolution use debounced saves and `flush()` for clean shutdown.

### References
- Implementation details: `viki/IMPLEMENTATION_SUMMARY.md`, `viki/MODEL_ENHANCEMENT_SUMMARY.md`, `viki/SECURITY_docs/SETUP.md`.

---

## [7.1.0] - 2026-02-14 (Stability & Persistence Persistence)

### Added
- **SQLite v3 Migration**: Fully decommissioned legacy `lessons_semantic.json` and moved all long-term knowledge to a relational SQLite database.
- **Unified Learning API**: Replaced all direct `.memory` attribute calls with structured `LearningModule` methods (`save_lesson`, `get_total_lesson_count`, etc.).
- **Integrated Forge 2.0**: Merged standalone model-forging scripts into the core kernel (`viki/forge.py`), enabling seamless autonomous evolution.
- **Refactored Skill Registry**: Skills now correctly register their requirements during initialization, eliminating `TypeError` during ReAct loops.

### Fixed
- **AttributeError**: Resolved critical system crash where components attempted to access the non-existent `.memory` dictionary in the LearningModule.
- **Async Startup Traceback**: Fixed unawaited `_startup_pulse` warnings and ensured clean initialization of cognitive layers.
- **Neural Dashboard v2**: Revamped the React UI with premium HSL themes, glassmorphism, and better responsive design.
- **Documentation Overhaul**: Updated `README.md`, `docs/ARCHITECTURE.md`, and `docs/SETUP.md` for v7.1.0; added `run-viki` workflow.
- **CORS Stability**: Explicitly configured cross-origin resource sharing to prevent UI/API connection failures.

### The Governance Pillar
- **CapabilityRegistry**: Implemented a granular permission system. Skills like `filesystem_write` and `shell_exec` are now strictly gated behind capability checks.
- **Judgment Engine v20**: Refined the cognitive triage (Reflex/Shallow/Deep) with post-judgment gates, ensuring required capabilities exist before deliberation begins.
- **The Ollama Oven**: Created an automated model-forging pipeline. VIKI can now "bake" her learned wisdom directly into a custom **Mistral/DeepSeek** Modelfile, producing a local Ollama image (default tag **`viki-neural-forge`**; see `system.forge_output_ollama_tag` / `VIKI_FORGE_OUTPUT_OLLAMA_MODEL`).
- **Structured Auditing**: Added high-fidelity logging for every decision. Every action is now logged with its `CapabilityCheckResult` (Exists, Enabled, Allowed, Reason).
- **Dataset Extraction**: Integrated `scripts/export_viki_dataset.py` for training set generation in ALPACA and ShareGPT formats.
- **Model Stability**: Standardized Mistral/Ollama instruction templates to eliminate "Schema Echo" errors and improve JSON compliance.

### Optimized
- **Cognitive Selectivity**: Large models (Mistral 7B) are now automatically escalated to the FULL response schema for better stability, while PHI-3 maintains the LITE schema for speed.
- **Memory Forging**: Lessons from semantic memory are now formatted as structured "Wisdom Blocks" for better model comprehension during forging.

---

## [2.2.0] - 2026-02-12 (Nexus Core)

### Massive Upgrade
- **OS Mastery**: Added `ClipboardSkill` (Copy/Paste), `WindowManagerSkill` (List/Focus/Minimize), `ShellSkill` (Sandbox Exec), and `NotificationSkill`.
- **Long-Term Memory**: Replaced ephemeral list with **SQLite** persistent storage for conversation history and goals.
- **Hybrid Intelligence**: Implemented **Multi-Model Routing** (Shallow/Deep) with priority weights and **Native Tool Calling** for high-speed actions.
- **Swarm Capability**: Added `SwarmSkill` to spawn council of sub-agents for complex reasoning.
- **Remote Bridge**: Integrated `TelegramBridge` for asynchronous remote control.
- **Self-Evolution**: Added `ModelForgeSkill` for LoRA fine-tuning and `ReflectorModule` for self-correction.
- **Visual Cortex**: Enabled `VisionSkill` to capture and analyze screen content within the ReAct loop.

### Fixed
- **Tool Use**: Standardized all skills with JSON schemas for reliable LLM function calling.
- **Event Loop**: Fixed blocking calls in Telegram and Voice modules.

---

## [7.0.0] - 2026-02-12 (The Cortex Upgrade)

### Added
- **Two-Brain Cognitive Architecture**: Split processing into a **Reflex Brain** (<200ms) for OS/Status and a **Thinker Brain** (Deep Reasoning).
- **Global Interrupt Token**: Universal "Audio Brake" and task cancellation across Voice, Skills, and LLM processing.
- **Intent Memory**: Replaced raw chat logs with **Active/Abandoned/Completed Goals**, reducing context noise and improving focus.
- **Skill Confidence Scoring**: Real-time tracking of skill success rates and latency, allowing VIKI to be self-aware of her own reliability.
- **Contextual Interruption Summaries**: VIKI now summarizes partial progress when stopped mid-task.
- **Self-Improving Skill Lifecycle**: Automatic "INTERNAL_SYSTEM_ADVISORY" lessons when skills are detected as unstable or slow.
- **Selective Neural Forge**: Evolutionary training only triggers on 10+ reinforced (stable) patterns or user-level `/evolve` command.
- **Emotional Intelligence Layer**: Dynamic tone selection (Neutral, Supportive, Direct, Technical) based on task context, stress heuristics, and time of day.
- **Proactive Awareness (Noise Control)**: Pattern-based suggestions (3+ repeats) with explicit user feedback loops (/dismiss, /snooze, /disable).
- **Desktop Automation Safety Envelope**: Tiered action classification (Safe/Medium/Destructive) with mandatory confirmation for risky operations.
- **Latency Budgeting**: Automatic progress updates and apologies if tasks exceed complexity-based time limits (e.g., 3s for reasoning, 10s for research).
- **One True Event Loop**: Consolidated all background tasks (Nexus, Watchdog, Bridges) into a single PriorityQueue architecture with explicit cancellation.
- **Explain Only When Asked**: Default "Conciseness Protocol" ensures responses are decisive and brief; detailed explanations only trigger on keywords like "why" or "details".
- **Failure Memory (Mistake Prevention)**: Tracks failed actions and their reasons; automatically injects relevant "negative constraints" into future planning cycles to prevent repeating mistakes.
- **Model Specialization (Polymorphic Intelligence)**: Multi-model routing system uses DeepSeek for planning, LLaMA for conversation, and Phi for high-speed reflexes, ensuring optimal performance for every slice of cognition.
- **CLI as Primary Brain Interface**: The Rich Dashboard is now the authoritative Command Center, surfacing deep internal metrics (Safety Tier, Model Role, Latency Budgets) with absolute clarity.

### Optimized
- **Perception Speed Layer**: reflex arcs for common chatter and status queries.
- **VAD Dynamic Thresholding**: Ambient noise floor calibration to prevent false voice triggers.

---

## [6.0.0] - 2026-02-12

### Added
- **Unified Messaging Nexus**: Asynchronous event loop bridging Terminal, Discord, and Telegram.
- **Neural Forge**: Autonomous self-evolution pipeline using Unsloth LoRA fine-tuning.
- **Desktop Agent**: Full OS control via `pyautogui` (Click, Type, Scroll).
- **Proactive Wellness Pulse**: Background monitoring for user inactivity.
- **Lazy Loading**: Major performance optimization for Torch, Unsloth, and Silero VAD.

### Fixed
- **Shutdown Crashes**: Resolved event loop termination issues in `viki/main.py`.
- **JSON Parsing**: Added robust handling for local LLM markdown output.
- **Watchdog Loop**: Fixed thread-safety in file monitoring.
- **Reflector Path**: Corrected `FileNotFoundError` in self-correction module.

### Removed
- Legacy entry points: `main.py` (root), `test_ollama.py`, `test_vision.py`.
- Deprecated synchronous bridges.

---

## [5.0.0] - Pre-Sovereign Era

### Added
- Basic RAG Memory.
- Voice Interaction (Sync).
- Simple Terminal Interface.

---

*Runbook version: aligned with VIKI v8.0.0 (Industrial). Update this file when default ports, flags, or critical architecture patterns change.*
