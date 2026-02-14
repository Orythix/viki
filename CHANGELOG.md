# Changelog

All notable changes to the VIKI Sovereign Intelligence project will be documented in this file.

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
