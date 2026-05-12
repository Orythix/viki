# VIKI: Sovereign Digital Intelligence
> **Autonomous AI Agent System | Orythix Cognitive Architecture | Virtual Intelligence Knowledge Interface**

<div align="center">

**Polymorphic Intelligence | Recursive Governance | Autonomous Self-Forging**

[![Version](https://img.shields.io/badge/version-7.3.2-blue.svg)](./CHANGELOG.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-orange.svg)](https://ollama.ai)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![CI](https://github.com/Orythix/viki/actions/workflows/ci.yml/badge.svg)](https://github.com/Orythix/viki/actions/workflows/ci.yml)

---

**VIKI** is an open-source autonomous AI agent and **Sovereign Digital Intelligence** for absolute privacy and **local-first** operation. Run with **Ollama**, **Phi-3**, **Mistral**, or **DeepSeek**—no cloud required. Uses the **Orythix Cognitive Architecture** for deep reasoning, multi-tool orchestration, and recursive self-improvement without leaking your data.

[Features](#core-pillars-v732) • [Architecture](#technical-architecture) • [Quick Start](#quick-start) • [Build the VIKI model](#build-your-viki-model) • [Security](#security--ethics) • [Contributing](./CONTRIBUTING.md)

**Pre-release:** VIKI is in active development. We welcome feedback and bug reports via [GitHub Issues](https://github.com/Orythix/viki/issues) and questions via [GitHub Discussions](https://github.com/Orythix/viki/discussions). Set `VIKI_API_KEY` and see [SECURITY_SETUP.md](viki/SECURITY_SETUP.md) before exposing the API.

</div>

---

## Overview (what VIKI is)

**VIKI** (**Virtual Intelligence Knowledge Interface**) is an **open-source AI agent** and **self-hosted autonomous assistant** written in **Python**. It targets **local-first** and **air-gapped** setups using **Ollama** (Phi, Mistral, Qwen, DeepSeek, and other local models), with optional cloud profiles when you opt in. The stack includes an intuitive **CLI**, **Flask REST API** (chat with **SSE streaming**, missions, forge, traces), **MCP** tool integration, **RAG-style** semantic memory over SQLite, **Neural Forge** baking of lessons into custom **Ollama** images, and a comprehensive **React + Vite** operator **dashboard** (text chat, hologram voice UI, token usage tracking, code search, MCP monitors, sub-agents). Governance uses **capability gating**, an ethical governor, and structured logging—not a multi-tenant SaaS; you run it on **your** machine or **Docker**.

**Repository:** [github.com/Orythix/viki](https://github.com/Orythix/viki) · **License:** Apache 2.0

## Frequently asked questions

### What is VIKI used for?

Coding assistance, local research with citations, task automation (files, shell, browser via Playwright), presentations and spreadsheets, messaging connectors (Telegram, Discord, Slack, WhatsApp), voice interaction, and experiments with **multi-step agents** and **tool use**—all with a strong **privacy** story because the default path never leaves your network.

### Is VIKI free? Can I self-host?

Yes. VIKI is **Apache-2.0** open source. You install from this repo, run `python viki/main.py` or Docker, and supply your own **Ollama** models. There is no required cloud subscription.

### Does VIKI run offline?

You can run in **air-gap** mode (`VIKI_AIR_GAP=1`) so routing sticks to local models and outbound research is disabled. You still need local LLM weights (e.g. via Ollama) on disk.

### How is VIKI different from LangChain, AutoGPT, or “ChatGPT desktop”?

VIKI ships as a **single opinionated agent system**: judgment/reflex layers, SQLite-backed **lessons**, **forge** pipeline to **Ollama** Modelfiles, first-class **dashboard** and **API**, and a broad **builtin skill** set. It is not a thin wrapper library; it is a runnable **sovereign agent** product you deploy yourself.

### What are the minimum requirements?

**Python 3.10+**, **Ollama** (or another supported local inference path per config), and enough RAM for your chosen model (many setups work on **8 GB**; **4 GB** is possible with small models and `low_resource_mode`). See [README § Running on low-end PCs](#running-on-low-end-pcs).

---

## The Sovereign Evolution

VIKI is a **Sovereign Digital Intelligence** designed to be more than just an assistant—she is a partner that evolves alongside your workflow. Built on a foundation of **local-first privacy** and **deterministic governance**, VIKI balances the raw power of LLMs with the safety of a modular, capability-aware architecture.

### Core Pillars (v7.3.2)

*   **Intelligence Governance**: Powered by the **Judgment Engine**. Every directive is filtered through a cognitive triage (Reflex, Shallow, Deep) to ensure the right model is used for the right task while maintaining absolute safety.
*   **The Neural Forge**: A integrated pipeline in the core kernel. VIKI extracts "Wisdom" from her SQLite-backed semantic memory and bakes it into a local **Ollama** image (default tag **`viki-neural-forge`**, profile **`viki-evolved`** in `models.yaml`) on top of bases such as **Phi-3**, **Mistral**, **Qwen**, or **DeepSeek-R1**.
*   **Capability-Aware Execution**: Granular permission gating. Skills like `filesystem_write` and `shell_exec` are managed by a centralized `CapabilityRegistry`, ensuring high-risk actions never bypass security protocols.
*   **Recursive Self-Reflection**: Utilizing the **Reflection Layer**, VIKI critiques her own plans before execution, reducing hallucinations and improving tool-use accuracy.
*   **Unified Persistence Layer**: A **SQLAlchemy-backed** multi-tiered architecture that allows VIKI to retain project context, user preferences, and historical lessons through a modern Repository pattern.
*   **Industrial Clean Architecture**: A decoupled, testable system powered by **Dependency Injection**, ensuring VIKI is ready for enterprise-grade expansion and isolated module evolution.

### What makes VIKI specific

VIKI is not a generic assistant. It is differentiated by:

*   **Local Neural Forge**: Evolves model variants from your interactions and lessons—no cloud training.
*   **Orythix governance**: Ethical governor, judgment engine, and capability gating keep behavior deterministic and auditable.
*   **Reflex layer**: Fast, low-latency intent recognition for habitual tasks without full deliberation.
*   **Air-gap capable**: Run with no external API calls; all reasoning and evolution stay on your machine.

### Personas

One codebase, multiple specialized “VIKIs”. Switch by setting `system.persona` in `viki/config/settings.yaml` or the `VIKI_PERSONA` environment variable.

| Persona     | Focus                    | Use when                          |
|------------|---------------------------|-----------------------------------|
| **sovereign** | Full capability (default) | You want all skills and no filter. |
| **dev**      | Coding, Forge, shell, FS  | You want a local-first coding partner. |
| **research** | Search, recall, browser   | You want accurate, cited research. |
| **home**     | Calendar, email, media, voice | You want a life/productivity assistant. |

Example: `VIKI_PERSONA=dev python viki/main.py` runs VIKI Dev with only dev-focused skills.

### Engineering playbooks

VIKI now includes 20 production engineering workflows grouped across Define, Plan, Build, Verify, Review, and Ship, sourced from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) under the MIT license.
It also includes a second in-house wave of 20 original playbooks spanning Architecture, Reliability, Data, Platform, AI/Agents, and Crypto engineering domains.

- Define: `idea_refine`, `spec_driven_development`
- Plan: `planning_and_task_breakdown`
- Build: `incremental_implementation`, `test_driven_development`, `context_engineering`, `source_driven_development`, `frontend_ui_engineering`, `api_and_interface_design`
- Verify: `browser_testing_with_devtools`, `debugging_and_error_recovery`
- Review: `code_review_and_quality`, `code_simplification`, `security_and_hardening`, `performance_optimization`
- Ship: `git_workflow_and_versioning`, `ci_cd_and_automation`, `deprecation_and_migration`, `documentation_and_adrs`, `shipping_and_launch`

Example skill invocations:

- `engineering_playbook`:
  `{"playbook":"spec_driven_development","section":"Process","format":"summary"}`
- `coding_workflow`:
  `{"phase":"build","task":"Add repository-level code search skill","context":"Files: viki/skills/builtins/code_search_skill.py, viki/tests/test_code_search.py"}`

### Task delivery and comparison (more than Manus)

Like universal agents that deliver finished work (e.g. [Manus](https://www.manusai.info/)), VIKI delivers complete artifacts, not just suggestions:

- **Data analysis**: Load CSV/Excel, describe stats, visualize (charts), optional LLM summary (`data_analysis` skill).
- **Presentations**: Generate PowerPoint (PPTX) from an outline or from natural language (`presentation` skill).
- **Spreadsheets**: Create or update XLSX and CSV from headers/rows or list-of-dicts (`spreadsheet` skill).
- **Websites**: Static site scaffold or custom pages (HTML/CSS) in the workspace (`website` skill).
- **Existing**: PDF edit, image generation, research, code execution (sandboxed), browser automation.

VIKI goes further: **voice** (TTS/STT), **smart home** (e.g. Hue), **Obsidian** vault, **tasks** (file or Things 3), **Twitter**, **Whisper** transcription, **unified messaging** (Telegram, Discord, Slack, WhatsApp), **local Neural Forge**, **Orythix governance**, and **air-gap capable** operation. The API exposes `subtasks` and `total_steps` for task progress; the CLI emits progress events during multi-step ReAct.

---

## Technical Architecture

### 🌌 **The Nexus Stack (OpenClaw-Grade Autonomy)**
VIKI is no longer confined to a single terminal. She is a multi-platform autonomous presence:
- **Unified Messaging Nexus**: Simultaneous integration with **Telegram, Discord, Slack, and WhatsApp**.
- **Autonomous Productivity**: Managed via dedicated **Email** and **Calendar** skills.
- **Deep Research**: Real-time web browsing and information synthesis using Playwright.
- **System Orchestration**: Cross-platform control for Windows, macOS, and Linux.

VIKI operates on a **5-Layer Consciousness Stack**:

1.  **Perception**: Ingests multi-modal inputs (Text, Vision via the `vision` skill, Audio via Whisper). Image/audio attachments are now piped through `_AttachmentStage` in `viki/core/request_pipeline.py`.
2.  **Interpretation**: Judgment Engine classifies intent and risk.
3.  **Deliberation**: The Cortex reasons across specialized local models.
4.  **Reflection**: Evaluates the plan against safety and logic constraints.
5.  **Execution**: Capability-gated skill deployment via the Controller, with optional Docker sandboxing for `python_interpreter`/`shell` (`viki/core/sandbox.py`).

### Running on low-end PCs

VIKI is designed to stay responsive on machines with 4 GB RAM and 2–4 cores. Two knobs do most of the work:

1. **Backend low-resource mode** — set `system.low_resource_mode: true` in `viki/config/settings.yaml` (or export `VIKI_LOW_RESOURCE=1`). This:
   - lazy-loads all heavy skills (vision, browser, whisper, pdf, image-gen, computer-use, plan-edit, …) so they only import on first use,
   - skips the autonomous startup pulse, wellness pulse, dream cycle, reflector, watchdog, and continuous-learning loop,
   - keeps the Cortex `PatternTracker` capped (`VIKI_PATTERN_TRACKER_MAX`, default 5000) with debounced disk writes.

2. **UI lite mode** — append `?lite=1` to the dashboard URL or set `localStorage.viki_lite = '1'`. The 3D hologram view is replaced with a 60-line CSS orb, and `three.js` / `drei` are dynamically imported instead of bundled into the initial paint. Lite mode is also auto-enabled when the browser reports `navigator.hardwareConcurrency <= 4` or `navigator.deviceMemory <= 4 GB`.

You can also tune individual cadences:

```yaml
proactive:
  wellness_interval_s: 3600        # 1 h instead of 30 min
  wellness_idle_threshold_s: 14400 # 4 h idle before any prompt

forge:
  continuous_learning_warmup_s: 1800     # 30 min
  continuous_learning_interval_s: 43200  # 12 h
```

Other small wins for cold boot: leave `system.local_llm_only: true` (skip cloud DNS lookups), keep `system.security_scan_requests: false`, and turn `system.use_ensemble` off if you want first-token latency over depth-of-deliberation.

#### Why is the first response slow?

The very first turn after boot pays a stack of one-time costs that subsequent turns do not. If you typed "hello viki" and waited 15+ seconds, the cause is almost certainly one of these:

1. **Ollama cold-loads the model on the first call.** A 4 GB Q4 model can take 5–15 s to read off disk. To shave this, leave the new flag `system.prewarm_default_model: true` on (default) — VIKI fires a 1-token ping at boot so the model is already resident when you hit Enter. Disabled automatically in `low_resource_mode` and `air_gap`.
2. **`Runtime health: degraded`** in the welcome banner. If a configured model is missing, VIKI silently falls back to a slower one. The banner now prints the unavailable model name and a concrete `ollama pull <model>` hint — run it once and the warning goes away.
3. **First sentence-transformer load**. The encoder weights (~150 MB) used by lessons / narrative recall are now lazy-loaded on first non-trivial query. Greetings, acks, and farewells skip them entirely thanks to the reflex layer.
4. **Governor safety check**. The ethical governor still issues a semantic-veto LLM call on every input longer than ~5 chars; that is intentional and unchanged.
5. **Token streaming**. For trivial conversational turns, deliberation now streams tokens through `chat_stream` so the first character lands in ~700 ms even though total wall-clock is unchanged. Set `system.use_ensemble: false` if you want the leanest possible deliberation prompt.
6. **Long idle re-load**. Ollama unloads the model from RAM after `OLLAMA_KEEP_ALIVE` (default 5 min). The first request after a long idle pays the cold-load again. Either bump `OLLAMA_KEEP_ALIVE=24h` in your environment, or just send any cheap message (a greeting hits the reflex layer and is free) before the real question.

If you really want the absolute lowest latency, combine: `low_resource_mode: true`, `use_ensemble: false`, `prewarm_default_model: true`, and a small Ollama model (`qwen2.5:1.5b` or similar).

### Frontier wiring (2026)

The pillars below are now actually wired (not just "Phase X complete" labels):

- **MCP integration** loaded at boot (`viki/integrations/mcp_client.py`), exposed at `/api/mcp/servers`, configured via `viki/config/mcp_servers.yaml`.
- **Real SSE chat streaming** at `/api/chat/stream`, consumed incrementally by `ui/src/App.jsx` with a stop button.
- **WebSocket `/ws`** for live mission/sub-agent events and operator interrupts (`flask-sock`).
- **LSP bridge**: hover, references, definition, and `publishDiagnostics` against real `pyright`/`typescript-language-server`.
- **Computer-use grounding**: confidence-gated, with an OmniParser-V2 ONNX adapter (set `VIKI_OMNIPARSER_ONNX`).
- **Best-of-N worktree runner** (`viki/core/worktree_runner.py`) for isolated parallel attempts.
- **Capability Index (forge)**: bootstrap CIs, min-task thresholds, SHA256 provenance hashes; operator promote/rollback at `/api/forge/promote` and `/api/forge/rollback`.
- **Persistent traces** with parent IDs, surfaced as a Gantt panel in the dashboard.
- **Mission CRUD + sub-agent tree** in the dashboard (`/api/missions`, `/api/subagents`, `/api/missions/<id>/graph`, `/api/artifacts/<mission_id>`).
- **Slash commands**: `/restore`, `/undo` (rolls back the most recent checkpoint).
- **Bio sensing is now experimental by default**; opt into a real DeepFace path with `system.bio_backend: deepface` (or `VIKI_BIO_BACKEND=deepface`).

### Directory Structure

```text
VIKI/
├── viki/
│   ├── core/               # Cognitive Kernel (Judgment, Cortex, Learning)
│   ├── config/             # Orchestration & Soul profiles
│   ├── skills/             # Modular Ability System (FS, Shell, Research)
│   ├── api/                # Unified Nexus (Discord, Telegram, Web)
│   ├── eval/               # RAG eval fixtures + README
│   └── main.py             # Authoritative entry point
├── ui/                     # Vite + React dashboard (chat, hologram, operator UI)
├── security-lab/           # Standalone defensive AI security lab (FastAPI + Docker)
├── qa-automation/          # Multi-stack QA learning tracks (pytest, Java, Playwright, k6, …)
├── docs/                   # Repo-wide documentation index (see DOCUMENTATION.md)
├── data/                   # SQLite wisdom & facts (gitignored by default)
├── logs/                   # Structured telemetry (gitignored by default)
└── viki/tests/             # Core stability & integration suites
```

---

## Quick Start

### Prerequisites
*   **Python 3.10+** (3.10, 3.11, and 3.12 are supported; CI runs 3.10 and 3.11 on Ubuntu).
*   **Ollama CLI**: Installed and running (the desktop app or service usually already listens on `127.0.0.1:11434`; a second `ollama serve` is only needed if nothing is bound to that port).
*   **Recommended Models**: `phi3` (Reflex), `deepseek-r1` (Reasoning). For the **Neural Forge** bake step, pull whatever base you configure (commonly `qwen3.5:latest` or `gemma4:latest`); see [Build your VIKI model](#build-your-viki-model).

### Installation
1.  **Clone & Initialize**:
    ```powershell
    git clone https://github.com/Orythix/viki.git
    cd viki
    python -m venv .venv
    ./.venv/Scripts/Activate.ps1
    pip install -e .
    ```
    For tests and lint: `pip install -e ".[dev]"`. Dependencies are declared in `pyproject.toml`; `requirements.txt` only installs the package in editable mode (`-e .`).

#### Install profiles (optional extras)

Extras are defined in [`pyproject.toml`](pyproject.toml) under `[project.optional-dependencies]`:

- **`dev`** — `pytest`, `pytest-asyncio`, `ruff` (CI and local development).
- **`windows`** — `pypiwin32` for Windows-specific integrations.
- **`optional-network`** — `scapy`.
- **`vad`** — `silero-vad` (voice activity).
- **`qt`** — `PyQt5` (e.g. desktop overlay in `viki/ui/overlay.py`).
- **`embeddings`** — `sentence-transformers`, `torch`, `torchaudio`.
- **`browser`** — `playwright` (run `playwright install chromium` after install for the browser skill).
- **`vision`** — `opencv-python`.
- **`agent-full`** — convenience bundle of common agent dependencies (see `pyproject.toml` for the exact list).

Examples:

```powershell
pip install -e ".[dev]"
pip install -e ".[windows,qt]"
```

2.  **Configure environment** (recommended so paths and secrets are not hardcoded):
    ```powershell
    copy .env.example .env
    # Edit .env and set VIKI_API_KEY, VIKI_ADMIN_SECRET, and optionally VIKI_DATA_DIR, VIKI_WORKSPACE_DIR, VIKI_PERSONA.
    ```
    Or set variables manually. For API: `VIKI_API_KEY` and `VIKI_ADMIN_SECRET` are required. Generate with:
    ```powershell
    python -c "import secrets; print(secrets.token_urlsafe(32))"
    ```
    See [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md) and `.env.example` for all options.

3.  **Launch VIKI (CLI)**:
    ```powershell
    python viki/main.py
    ```

### Using VIKI from the CLI (like Claude Code)

Install the `viki` command so you can run it from any directory with the current (or a given) project as workspace:

- **Install**: From the repo root, run `pip install -e .` (or use the one-line install scripts below).
- **Run**:
  - `viki` — use current directory as workspace and enter the interactive REPL.
  - `viki /path/to/project` — use that directory as workspace and enter the interactive REPL.
  - `viki "fix the bug"` — execute a single-shot query in the current directory, apply changes, and exit.
  - `viki /path/to/project "add logging"` — run a single-shot query in a specific directory.
  - `VIKI_PERSONA=dev viki` — run with the dev persona (coding-focused skills).
- **Confirm/reject**: When VIKI asks "Confirm to proceed" for a medium or destructive action, reply `yes` or `confirm` to run it, or `no` or `reject` to cancel. You can also use `/confirm` or `/reject`.
- **Useful in-chat commands**: `/help`, `/skills`, `/shadow` (simulate only), `/scan` (re-scan workspace codebase).

**One-line install (optional)**:

- Windows: `irm https://raw.githubusercontent.com/Orythix/viki/main/install.ps1 | iex` (or from repo: `.\install.ps1`)
- Unix: `curl -fsSL https://raw.githubusercontent.com/Orythix/viki/main/install.sh | bash` (or from repo: `./install.sh`)

4.  **Launch with Hologram Face UI** (talk to VIKI with voice):
    ```powershell
    # Terminal 1: start the UI
    cd ui && npm run dev

    # Terminal 2: start VIKI with API and open browser to the hologram
    python viki/main.py --ui
    ```
    The app opens at `http://localhost:5173` with the **Hologram** view by default: a hologram-style face and voice conversation (browser speech-to-text and text-to-speech). Use **Full dashboard** to switch to the text chat view. The UI requires the same API key: set `VITE_VIKI_API_KEY` in `ui/.env` (or in your shell when building) to match `VIKI_API_KEY`. See [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md).

5.  **Launch Dashboard (UI) only**:
    Open two terminals:
    - Terminal 1 (API): `python viki/api/server.py` — API requires `Authorization: Bearer $VIKI_API_KEY` for all requests.
    - Terminal 2 (UI): `cd ui; npm run dev`
    Access at `http://localhost:5173`

6.  **Run with Docker**:
    Build and run the API in a container. Ollama should be running on the host (or in another container). See [DOCKER.md](DOCKER.md) for details.
    ```powershell
    copy .env.example .env
    # Edit .env and set VIKI_API_KEY (required)
    docker compose up --build
    ```
    Then run the UI on the host: `cd ui && npm run dev`, and set `VITE_VIKI_API_BASE=http://localhost:5000/api` in `ui/.env`. On Windows/Mac the compose file sets `OLLAMA_HOST=http://host.docker.internal:11434` so the container can reach Ollama on the host.

---

## Build your VIKI model

**Neural Forge** — you can turn VIKI’s **reinforced lessons** (SQLite-backed learning DB under `data/`) into a **local Ollama image** whose system prompt embeds that wisdom. This is the main way to “build” the agent’s baked-in personality and corrections without cloud training.

### What gets built (default: `prompt_bake`)

The script [`scripts/build_viki_model.py`](scripts/build_viki_model.py) exports a small JSONL dataset, writes `data/Modelfile.viki_evolved` with `FROM <your-base-model>` plus a **SYSTEM** block of top lessons, then runs `ollama create` to produce an Ollama **tag** (default: `viki-neural-forge`; configurable in `settings.yaml` / `VIKI_FORGE_OUTPUT_OLLAMA_MODEL`). No GPU is required for this path.

Optional **GPU** strategies (`--strategy lora`, `dpo`, `orpo`) are documented in the script header and need CUDA plus env flags (`VIKI_UNSLOTH_RUN_TRAIN`, etc.).

### Prerequisites

1. **Ollama** reachable (`ollama list` works).
2. **Base model** pulled, e.g. `ollama pull qwen3.5:latest` (or `gemma4:latest`, or any tag you pass with `--base`).
3. **Some lessons** in the DB (the script will fail if there are zero). Use VIKI normally so reinforced lessons accumulate.

### Configure the base model

Set the bake base in **`viki/config/settings.yaml`**:

```yaml
system:
  forge_base_ollama_model: "qwen3.5:latest"   # or gemma4:latest, etc. (Modelfile FROM)
  forge_output_ollama_tag: "viki-neural-forge"  # ollama create tag; override with VIKI_FORGE_OUTPUT_OLLAMA_MODEL
```

Override for one session: `$env:VIKI_FORGE_BASE_OLLAMA_MODEL = "gemma4:latest"` or `$env:VIKI_FORGE_OUTPUT_OLLAMA_MODEL = "my-viki-tag"` (PowerShell).

### Build commands (repo root)

```powershell
cd D:\path\to\VIKI   # your clone

# Prompt-bake using settings / env base → creates Ollama tag viki-neural-forge (default)
python scripts/build_viki_model.py

# Same, but force a specific base and output tag (keep multiple variants side by side)
python scripts/build_viki_model.py --base gemma4:latest --name viki-neural-forge-gemma

# Bake and set models.yaml default profile to viki-evolved (see below)
python scripts/build_viki_model.py --set-default
```

Useful flags: `--min-count N` (only lessons seen at least *N* times), `--no-export`, `--dry-run`. Run `python scripts/build_viki_model.py --help` for the full list.

### Wire the image into VIKI

- The Ollama **image name** is whatever you passed as `--name` (otherwise **`forge_output_ollama_tag`** in settings, env **`VIKI_FORGE_OUTPUT_OLLAMA_MODEL`**, or **`viki-neural-forge`**).
- The **`viki-evolved`** entry in [`viki/config/models.yaml`](viki/config/models.yaml) maps the profile to that image via `model_name` (by default `viki-neural-forge`).
- **`python scripts/build_viki_model.py --set-default`** sets `models.default: viki-evolved` so the app prefers your forged model.
- If you used a custom `--name`, either update `model_name` under `viki-evolved` or add another profile and set `default:` to it.

### Try it

```powershell
ollama run viki-neural-forge
```

In the **VIKI app**, local Ollama calls default to **`think: false`** (see `system.ollama_enable_thinking` in `settings.yaml`) so end users do not see long reasoning traces; the raw `ollama run` CLI may still show thinking unless you pass flags such as `--hidethinking` / `--think=false` for your model.

### Publish to ollama.com (optional)

After you have a local tag (e.g. **`viki-neural-forge:latest`** from `build_viki_model.py`), you can push it under your Ollama namespace. Example for username **`orythix`**:

1. **Sign in** to Ollama from the CLI (one-time): `ollama signin` — follow the browser flow ([CLI docs](https://docs.ollama.com/cli)).
2. **Copy** the local image to your namespace (name must be `yourname/model`):
   ```powershell
   ollama cp viki-neural-forge:latest orythix/viki-neural-forge:latest
   ```
3. **Upload** (large; may take a while):
   ```powershell
   ollama push orythix/viki-neural-forge
   ```

Others can then run: `ollama pull orythix/viki-neural-forge` and `ollama run orythix/viki-neural-forge`. Your listing will appear under `https://ollama.com/orythix/viki-neural-forge`. Review the **base model license** and any **baked `SYSTEM` text** before publishing.

### Ongoing evolution

Unlike static bots, VIKI also grows during normal use: interact, lessons accumulate, then **re-run** `build_viki_model.py` when you want a fresh `ollama create` with updated baked-in knowledge.

---

## Security & Ethics
*   **API Authentication**: All API endpoints require `VIKI_API_KEY`. Set via environment variable; see [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md).
*   **Admin Commands**: Super-admin uses `VIKI_ADMIN_SECRET` (env). Never commit secrets; use env or a secrets manager.
*   **Privacy**: 100% Local. No telemetry. No external API calls unless explicitly configured for internet research.
*   **Control**: Every skill run passes `validate_action`; file paths are sandboxed (dev_tools, whisper, PDF, data_analysis, filesystem). Shell command chaining is treated as destructive. Output and logs redact secrets.
*   **Audit**: Check `logs/viki.log` and `viki/SECURITY_SETUP.md` for capability checks and setup.

## Documentation

**Full index:** [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) (core VIKI, UI, `security-lab`, `qa-automation`, eval, playbooks).

| Document | Description |
|----------|-------------|
| [SETUP.md](SETUP.md) | Installation and environment |
| [VIKI_RUNBOOK.md](VIKI_RUNBOOK.md) | Operations, troubleshooting, RAG eval, boot evolution |
| [DOCKER.md](DOCKER.md) | Run VIKI in Docker (`docker compose`) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design and data flow |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [SECURITY.md](SECURITY.md) | Security policy and reporting |
| [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md) | API keys, CORS, capability setup |
| [viki/eval/README.md](viki/eval/README.md) | RAG retrieval evaluation (`run_rag_eval.py`) |
| [security-lab/README.md](security-lab/README.md) | Local defensive AI security lab |
| [qa-automation/README.md](qa-automation/README.md) | QA automation learning monorepo |
| [viki/ARCHITECTURE_REFACTOR.md](viki/ARCHITECTURE_REFACTOR.md) | Controller / pipeline refactor notes |
| [`scripts/build_viki_model.py`](scripts/build_viki_model.py) | CLI: bake lessons into an Ollama model (`prompt_bake` / LoRA / DPO) |

---

## Keywords and topics

**Local AI agent** · **Self-hosted AI assistant** · **Open-source AI agent** · **Autonomous AI** · **Ollama agent** · **Python AI agent** · **LLM agent** · **ReAct agent** · **Tool-use agent** · **MCP integration** · **RAG** · **Semantic memory** · **Private AI** · **Privacy-first AI** · **Air-gapped AI** · **Sovereign AI** · **Local LLM** · **Offline LLM** · **Neural Forge** · **Ollama Modelfile** · **Capability gating** · **AI agent dashboard** · **Voice AI assistant** · **CLI AI** · **Self-improving AI** · **Orythix** · **Multi-model routing** · **Agentic workflow** · **Windows AI agent** · **Linux AI agent**

---

## License

VIKI is released under the [Apache License 2.0](./LICENSE). See [NOTICE](./NOTICE) for third-party attributions.

## Contributing

We welcome pull requests, bug reports, and feature ideas. Please read [CONTRIBUTING.md](./CONTRIBUTING.md) and our [Code of Conduct](./CODE_OF_CONDUCT.md) before opening a PR.

---

**VIKI: Virtual Intelligence, Real Evolution.**