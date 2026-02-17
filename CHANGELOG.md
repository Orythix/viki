# Changelog

All notable changes to the VIKI Sovereign Intelligence project will be documented in this file.

## [7.3.1] - 2026-02-17 (First public pre-release)

### Added
- **Docker support:** Dockerfile and docker-compose for running the API in containers; FLASK_HOST env for binding; DOCKER.md and README section.
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
- Security details: `viki/SECURITY_SETUP.md`, security focus plan in `plans/`.

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
- **Documentation**: `SECURITY_SETUP.md`, `IMPLEMENTATION_SUMMARY.md`, `MODEL_ENHANCEMENT_SUMMARY.md`, `OBSERVABILITY.md`, `ARCHITECTURE_REFACTOR.md`, `PERFORMANCE_NOTES.md`; README docs table and version bump to 7.2.0.

### Fixed
- **Security**: PowerShell injection in notification skill; path sandboxing in filesystem skill; SSRF/SSL in research skill; removed `shell=True` and validated input in system control skill; reflex path runs full security pipeline.
- **Blocking I/O**: Security skill and image loading wrapped in `asyncio.to_thread()`; research `save_lesson` made async.
- **Duplicate DB Work**: Removed duplicate `get_semantic_knowledge` by passing pre-fetched `narrative_wisdom` into `get_full_context()`.
- **Debounced Persistence**: WorldModel, Scorecard, Reflex, Evolution use debounced saves and `flush()` for clean shutdown.

### References
- Implementation details: `viki/IMPLEMENTATION_SUMMARY.md`, `viki/MODEL_ENHANCEMENT_SUMMARY.md`, `viki/SECURITY_SETUP.md`.

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
- **Documentation Overhaul**: Updated `README.md`, `ARCHITECTURE.md`, and `SETUP.md` for v7.1.0; added `run-viki` workflow.
- **CORS Stability**: Explicitly configured cross-origin resource sharing to prevent UI/API connection failures.

### The Governance Pillar
- **CapabilityRegistry**: Implemented a granular permission system. Skills like `filesystem_write` and `shell_exec` are now strictly gated behind capability checks.
- **Judgment Engine v20**: Refined the cognitive triage (Reflex/Shallow/Deep) with post-judgment gates, ensuring required capabilities exist before deliberation begins.
- **The Ollama Oven**: Created an automated model-forging pipeline. VIKI can now "bake" her learned wisdom directly into a custom **Mistral/DeepSeek** Modelfile, forging `viki-born-again`.
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
