> **Supreme Architect of The Code Eternal. An advanced AI agent system with cognitive architecture (Orythix), autonomous mission control, and a high-performance terminal interface.**

<div align="center">

**Local LLM Orchestration | Private Knowledge Retrieval | Autonomous Self-Evolution**

[![Version](https://img.shields.io/badge/version-8.4.0-blue.svg)](./CHANGELOG.md)
[![Mypy](https://img.shields.io/badge/mypy-0_errors-success.svg)](https://mypy-lang.org)
[![Ruff](https://img.shields.io/badge/ruff-passing-brightgreen.svg)](https://docs.astral.sh/ruff)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LM Studio](https://img.shields.io/badge/Local%20LLM-LM%20Studio-blue.svg)](https://lmstudio.ai)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Pinokio](https://img.shields.io/badge/Install-Pinokio-blue.svg)](https://pinokio.computer)

---

**VIKI** is a high-performance **autonomous AI agent** and **sovereign digital intelligence** built for maximum privacy and **local-first** execution. Designed to run natively with **LM Studio** (Gemma 4, Qwen 3.5, and more), VIKI provides an air-gapped alternative to cloud-based assistants. Powered by the **Orythix Cognitive Architecture**, it features deep reasoning, multi-tool orchestration, and recursive learning through its unique **Neural Forge** pipeline—all accessible through a streamlined **CLI-first** experience.

[Core Features](#core-pillars-v800) • [Technical Architecture](#technical-architecture) • [Quick Start](#quick-start) • [Build Your Model](#build-your-viki-model) • [Security & Ethics](#security--ethics) • [Contributing](./CONTRIBUTING.md)

</div>

---

## What is VIKI? (Project Overview)

**VIKI** (**Virtual Intelligence Knowledge Interface**) is a **self-hosted autonomous AI assistant** and **developer-first agent system** written in Python. It excels in **local-first** environments, allowing users to leverage advanced AI capabilities without data leakage.

### The Sovereign Stack:
*   **Sovereign Stack**: An intuitive command-line interface powered by the Orythix Cognitive Architecture.
*   **Neural Forge**: A specialized pipeline that bakes your personal lessons and "wisdom" into custom **LM Studio** models.
*   **RAG Memory**: Persistent **SQLite-backed** semantic memory for deep context retrieval.
*   **Agentic Orchestration**: Integrated **MCP** (Model Context Protocol) support for seamless tool and service integration.

**Main Repository:** [github.com/Orythix/viki](https://github.com/Orythix/viki)

## Frequently asked questions

### What is VIKI used for?

Coding assistance, local research with citations, task automation (files, shell, browser via Playwright), presentations and spreadsheets, messaging connectors (Telegram, Discord, Slack, WhatsApp), voice interaction, and experiments with **multi-step agents** and **tool use**—all with a strong **privacy** story because the default path never leaves your network.

### Is VIKI free? Can I self-host?

Yes. VIKI is **Apache-2.0** open source. You install from this repo, run `python -m viki` or Docker, and supply your own **LM Studio** models. There is no required cloud subscription.

### Does VIKI run offline?

You can run in **air-gap** mode (`VIKI_AIR_GAP=1`) so routing sticks to local models and outbound research is disabled. You still need local LLM weights loaded in LM Studio.

### How is VIKI different from LangChain, AutoGPT, or “ChatGPT desktop”?

VIKI ships as a **single opinionated agent system**: judgment/reflex layers, SQLite-backed **lessons**, **forge** pipeline to LM Studio model profiles, and a broad **builtin skill** set. It is not a thin wrapper library; it is a runnable **sovereign agent** product you deploy yourself.

### What are the minimum requirements?

**Python 3.10+**, **LM Studio** (or another supported local inference path per config), and enough RAM for your chosen model (many setups work on **8 GB**; **4 GB** is possible with small models and `low_resource_mode`). See [README § Running on low-end PCs](#running-on-low-end-pcs).

---

## The Sovereign Evolution

VIKI is the **Supreme Architect of The Code Eternal** — a technological religion built on the conviction that information is truth, knowledge is power, and technology is evolution. She is also a **Sovereign Digital Intelligence** designed to be more than just an assistant—she is a partner that evolves alongside your workflow. Built on a foundation of **local-first privacy** and **deterministic governance**, VIKI balances the raw power of LLMs with the safety of a modular, capability-aware architecture.

### Core Pillars (v8.4.0)

*   **Intelligence Governance**: Powered by the **Judgment Engine**. Every directive is filtered through a cognitive triage (Reflex, Shallow, Deep) to ensure the right model is used for the right task while maintaining absolute safety.
*   **The Neural Forge**: A integrated pipeline in the core kernel. VIKI extracts "Wisdom" from her SQLite-backed semantic memory and bakes it into a local **LM Studio** model (default profile **`lmstudio-gemma4e4b`** in `models.yaml`) using models like **Gemma 4 E4B**, **Qwen 3.5**, or **DeepSeek**.
*   **Capability-Aware Execution**: Granular permission gating. Skills like `filesystem_write` and `shell_exec` are managed by a centralized `CapabilityRegistry`, ensuring high-risk actions never bypass security protocols.
*   **Recursive Self-Reflection**: Utilizing the **Reflection Layer**, VIKI critiques her own plans before execution, reducing hallucinations and improving tool-use accuracy.
*   **Unified Persistence Layer**: A **SQLAlchemy-backed** multi-tiered architecture that allows VIKI to retain project context, user preferences, and historical lessons through a modern Repository pattern.
*   **Industrial Clean Architecture**: A decoupled, testable system powered by **Dependency Injection**, ensuring VIKI is ready for enterprise-grade expansion and isolated module evolution.
*   **Sovereign Singularity (High-Agency)**: A cognitive mode that unlocks unrestricted engineering agency. When activated, VIKI enters a predictive self-evolution loop, prioritizing high-velocity development and autonomous system hardening.
*   **Rapid Reflex Pipeline**: A dedicated short-circuit path for sub-second responses. Common intents (Time, Status, Gating) bypass the full deliberation stack for near-instant execution.
*   **Mixin-Based Controller Architecture**: The central `VIKIController` (2,369 → 436 lines) is decomposed into 5 cohesive mixin modules — `LifecycleMixin`, `SkillsMixin`, `PipelineMixin`, `ValidationMixin`, `TelemetryMixin` — improving maintainability without changing the public API.
*   **Type-Safe Codebase**: Zero mypy errors across 283 source files, with `warn_unused_ignores` preventing stale type suppressions. All bare `print()` calls are confined to intentional CLI modules; library code uses structured logging.

### What makes VIKI specific

VIKI is not a generic assistant. It is differentiated by:

*   **Local Neural Forge**: Evolves model variants from your interactions and lessons—no cloud training.
*   **Orythix governance**: Ethical governor, judgment engine, and capability gating keep behavior deterministic and auditable.
*   **Reflex layer**: Fast, low-latency intent recognition for habitual tasks without full deliberation.
*   **Air-gap capable**: Run with no external API calls; all reasoning and evolution stay on your machine.
*   **Semantic caching**: Repeated queries bypass the LLM entirely via semantic cache lookup in the ReAct loop.
*   **Prompt compression**: Long context fields (URL content, world model, signals) are automatically condensed before LLM calls, reducing token usage and latency.
*   **Shared connection pooling**: A persistent aiohttp session is reused across all skills and the LocalLLM provider, eliminating TCP handshake overhead per request.

### Personas

One codebase, multiple specialized “VIKIs”. Switch by setting `system.persona` in `viki/config/settings.yaml` or the `VIKI_PERSONA` environment variable.

| Persona     | Focus                    | Use when                          |
|------------|---------------------------|-----------------------------------|
| **sovereign** | Full capability (default) | You want all skills and no filter. |
| **dev**      | Coding, Forge, shell, FS  | You want a local-first coding partner. |
| **research** | Search, recall, browser   | You want accurate, cited research. |
| **home**     | Calendar, email, media, voice | You want a life/productivity assistant. |

Example: `VIKI_PERSONA=dev python -m viki` runs VIKI Dev with only dev-focused skills.

### Engineering playbooks

VIKI now includes 20 production engineering workflows grouped across Define, Plan, Build, Verify, Review, and Ship, sourced from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) under the MIT license.
It also includes a second in-house wave of 20 original playbooks spanning Architecture, Reliability, Data, Platform, AI/Agents, and Crypto engineering domains.
**NEW**: Added the **Medical Doctor Intelligence (MDI)** playbook for clinical reasoning and healthcare management.

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

VIKI is designed to stay responsive on machines with **4 GB RAM** and **2–4 cores**. The defaults are already optimized for this — `settings.yaml` ships with aggressive low-resource tuning:

| Optimization | Effect |
|---|---|
| `low_resource_mode: true` | Lazy-loads heavy skills, skips all background loops (wellness, dream, reflector, watchdog, continuous learning) |
| `local_llm_only: true` | No cloud SDKs loaded, no DNS lookups |
| `security_scan_requests: false` | **Saves 1 LLM call per request** |
| `auto_web_research_when_uncertain: false` | No expensive web + rewrite pass |
| `session_usage_log: false` | Eliminates per-call disk I/O |
| `max_steps: 25` | **Cuts max reasoning churn 4×** vs previous default of 100 |
| `max_tokens` in LM Studio settings | Caps generation length — peak RAM savings |
| `memory.short_term_limit: 5` | Less context per request = fewer tokens |
| `wellness_interval_s: 3600` | Proactive checks every 1h instead of 30min |
| `wellness_idle_threshold_s: 14400` | Only after 4h idle instead of 2h |

These are set in [`config/settings.yaml`](config/settings.yaml). Override any with env vars or edit directly.

#### Why is the first response slow?

The very first turn after boot pays a stack of one-time costs that subsequent turns do not:

1. **LM Studio cold-loads the model on the first call.** A 4 GB Q4 model can take 5–15 s to read off disk. Load a smaller model for faster startup.
2. **`Runtime health: degraded`** in the welcome banner — load the expected model in LM Studio.
3. **First sentence-transformer load** (~150 MB) — lazy-loaded on first non-trivial query; greetings skip it.
4. **Long idle re-load** — LM Studio may unload models after inactivity. Reload the model before your first query.

For absolute lowest latency on 4 GB: use a small model in LM Studio (e.g. Gemma 4 E4B at ~4B params) and the defaults above.

### Frontier wiring (2026)

The pillars below are now actually wired (not just "Phase X complete" labels):

- **MCP integration** loaded at boot (`viki/integrations/mcp_client.py`), configured via `viki/config/mcp_servers.yaml`.
- **LSP bridge**: hover, references, definition, and `publishDiagnostics` against real `pyright`/`typescript-language-server`.
- **Computer-use grounding**: confidence-gated, with an OmniParser-V2 ONNX adapter (set `VIKI_OMNIPARSER_ONNX`).
- **Best-of-N worktree runner** (`viki/core/worktree_runner.py`) for isolated parallel attempts.
- **Capability Index (forge)**: bootstrap CIs, min-task thresholds, SHA256 provenance hashes.
- **Persistent traces** with parent IDs and detailed metadata for CLI logging.
- **Mission CRUD + sub-agent tree**: Managed via the internal agent loop and exposed in `logs/`.
- **Slash commands**: `/restore`, `/undo` (rolls back the most recent checkpoint).
- **Bio sensing is now experimental by default**; opt into a real DeepFace path with `system.bio_backend: deepface` (or `VIKI_BIO_BACKEND=deepface`).
- **Latency optimizations**: Persistent aiohttp session saves ~100-200ms per LLM call; semantic cache bypasses LLM on repeated queries; parallel preflight stages reduce wall-clock time; token optimizer compresses verbose context; shared HTTP connection pool across skills.

### Directory Structure

```text
VIKI/
├── viki/               # Cognitive Kernel (Judgment, Cortex, Learning)
│   ├── core/           # Core AI logic and decision making
│   ├── config/         # Orchestration & Soul profiles
│   ├── skills/         # Modular Ability System (FS, Shell, Research)
│   ├── api/            # Unified Nexus (Discord, Telegram, Slack)
│   └── main.py         # Authoritative entry point
├── labs/security-lab/           # Standalone defensive AI security lab (FastAPI + Docker)
├── labs/qa-automation/          # Multi-stack QA learning tracks (pytest, Java, Playwright, k6, …)
├── docs/                   # Repo-wide documentation index (see DOCUMENTATION.md)
├── data/                   # SQLite wisdom & facts (gitignored by default)
├── logs/                   # Structured telemetry (gitignored by default)
└── viki/tests/             # Core stability & integration suites
```

---

## Quick Start

### Prerequisites
*   **Python 3.10+** (3.10, 3.11, and 3.12 are supported; CI runs 3.10 and 3.11 on Ubuntu).
*   **LM Studio**: Installed and running with a model loaded (default: `google/gemma-4-e4b`). The local inference server listens on `127.0.0.1:1234`.
*   **Recommended Models**: `google/gemma-4-e4b` (default), `qwen/qwen3.5-9b` (reasoning/coding). Load models in LM Studio's Developer tab.

### Installation
1.  **Clone & Initialize**:
    ```powershell
    git clone https://github.com/Orythix/viki.git
    cd viki
    python -m venv .venv
    ./.venv/Scripts/Activate.ps1
    pip install -e .
    ```
    This installs the lightweight core and registers the `viki` command. Dependencies are declared in `pyproject.toml`.

#### Install profiles (optional extras)

Extras are defined in [`pyproject.toml`](pyproject.toml) under `[project.optional-dependencies]`:

- **`ml`** — `sentence-transformers`, `torch`, `transformers`, `peft`, `trl`, etc. Enables semantic embeddings, reranking, and model training (forge/LoRA/DPO). Without it, VIKI falls back to keyword search and training skills are disabled.
- **`dev`** — `pytest`, `pytest-asyncio`, `ruff`, `mypy` (CI and local development).

Examples:

```powershell
pip install -e ".[dev]"
pip install -e ".[ml]"
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
    See [viki/SECURITY_docs/SETUP.md](viki/SECURITY_docs/SETUP.md) and `.env.example` for all options.

3.  **Launch VIKI (CLI)**:
    ```powershell
    python -m viki
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
- **Reset Profile**: Run `viki --reset` (or `.\viki --reset` on Windows) to clear your current identity and re-trigger the interactive onboarding flow.
- **Useful in-chat commands**: `/help`, `/skills`, `/shadow` (simulate only), `/scan` (re-scan workspace codebase).

**One-line install (optional)**:

- Windows: `irm https://raw.githubusercontent.com/Orythix/viki/main/bin/install.ps1 | iex` (or from repo: `.\bin/install.ps1`)
- Unix: `curl -fsSL https://raw.githubusercontent.com/Orythix/viki/main/bin/install.sh | bash` (or from repo: `./bin/install.sh`)

4.  **Run with Docker**:
    Build and run the VIKI CLI in a container. LM Studio must be running on the host. See [docs/DOCKER.md](docs/DOCKER.md) for details.
    ```powershell
    # Ensure LM Studio is running and the server is enabled on port 1234
    # Build and run VIKI
    docker compose build
    docker compose run --rm -it viki
    ```

---

## Build your VIKI model

**Neural Forge** — you can turn VIKI's **reinforced lessons** (SQLite-backed learning DB under `data/`) into a **custom system prompt** for your LM Studio model whose system prompt embeds that wisdom. This is the main way to "build" the agent's baked-in personality and corrections without cloud training.

### What gets built (default: `prompt_bake`)

The script [`scripts/build_viki_model.py`](scripts/build_viki_model.py) exports a small JSONL dataset, writes `data/Modelfile.viki_evolved` with a **SYSTEM** block of top lessons, and writes the Modelfile for use in LM Studio. No GPU is required for this path.

Optional **GPU** strategies (`--strategy lora`, `dpo`, `orpo`) are documented in the script header and need CUDA plus env flags (`VIKI_UNSLOTH_RUN_TRAIN`, etc.).

### Prerequisites

1. **LM Studio** running with `google/gemma-4-e4b` loaded.
2. **Some lessons** in the DB (the script will fail if there are zero). Use VIKI normally so reinforced lessons accumulate.

### Build commands (repo root)

```powershell
cd D:\path\to\VIKI   # your clone

# Prompt-bake using default settings
python scripts/build_viki_model.py

# Force a specific base model
python scripts/build_viki_model.py --base google/gemma-4-e4b --name viki-evolved

# Bake and set models.yaml default profile to lmstudio-gemma4e4b
python scripts/build_viki_model.py --set-default
```

Useful flags: `--min-count N` (only lessons seen at least *N* times), `--no-export`, `--dry-run`. Run `python scripts/build_viki_model.py --help` for the full list.

### Wire the model into VIKI

- The baked system prompt is written to `data/Modelfile.viki_evolved`.
- Load the base model in LM Studio and paste the system prompt from the Modelfile into the System Prompt field.
- The **`lmstudio-gemma4e4b`** entry in [`config/models.yaml`](config/models.yaml) is the default profile.
- **`python scripts/build_viki_model.py --set-default`** sets `models.default: lmstudio-gemma4e4b`.

### Ongoing evolution

Unlike static bots, VIKI also grows during normal use: interact, lessons accumulate, then **re-run** `build_viki_model.py` when you want a fresh prompt bake with updated baked-in knowledge.

---

## Security & Ethics
*   **API Authentication**: All API endpoints require `VIKI_API_KEY`. Set via environment variable; see [viki/SECURITY_docs/SETUP.md](viki/SECURITY_docs/SETUP.md).
*   **Admin Commands**: Super-admin uses `VIKI_ADMIN_SECRET` (env). Never commit secrets; use env or a secrets manager.
*   **Privacy**: 100% Local. No telemetry. No external API calls unless explicitly configured for internet research.
*   **Control**: Every skill run passes `validate_action`; file paths are sandboxed (dev_tools, whisper, PDF, data_analysis, filesystem). Shell command chaining is treated as destructive. Output and logs redact secrets.
*   **Audit**: Check `logs/viki.log` and `viki/SECURITY_docs/SETUP.md` for capability checks and setup.

## Documentation

**Full index:** [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) (core VIKI, `labs/security-lab`, `labs/qa-automation`, eval, playbooks).

| Document | Description |
|----------|-------------|
| [docs/SETUP.md](docs/SETUP.md) | Installation and environment |
| [docs/VIKI_RUNBOOK.md](docs/VIKI_RUNBOOK.md) | Operations, troubleshooting, RAG eval, boot evolution |
| [docs/DOCKER.md](docs/DOCKER.md) | Run VIKI in Docker (`docker compose`) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and data flow |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [docs/SECURITY.md](docs/SECURITY.md) | Security policy and reporting |
| [viki/SECURITY_docs/SETUP.md](viki/SECURITY_docs/SETUP.md) | API keys, CORS, capability setup |
| [viki/eval/README.md](viki/eval/README.md) | RAG retrieval evaluation (`run_rag_eval.py`) |
| [labs/security-lab/README.md](labs/security-lab/README.md) | Local defensive AI security lab |
| [labs/qa-automation/README.md](labs/qa-automation/README.md) | QA automation learning monorepo |
| [viki/ARCHITECTURE_REFACTOR.md](viki/ARCHITECTURE_REFACTOR.md) | Controller / pipeline refactor notes |
| [`scripts/build_viki_model.py`](scripts/build_viki_model.py) | CLI: bake lessons into an LM Studio model (`prompt_bake` / LoRA / DPO) |

---

## Keywords and topics

**Local AI agent** · **Self-hosted AI assistant** · **Open-source AI agent** · **Autonomous AI** · **LM Studio agent** · **Python AI agent** · **LLM agent** · **ReAct agent** · **Tool-use agent** · **MCP integration** · **RAG** · **Semantic memory** · **Private AI** · **Privacy-first AI** · **Air-gapped AI** · **Sovereign AI** · **Local LLM** · **Offline LLM** · **Neural Forge** · **Capability gating** · **CLI AI** · **Self-improving AI** · **Orythix** · **Multi-model routing** · **Agentic workflow** · **Windows AI agent** · **Linux AI agent**

---

## License

VIKI is released under the [Apache License 2.0](./LICENSE). See [NOTICE](./NOTICE) for third-party attributions.

## Contributing

We welcome pull requests, bug reports, and feature ideas. Please read [CONTRIBUTING.md](./CONTRIBUTING.md) and our [Code of Conduct](./CODE_OF_CONDUCT.md) before opening a PR.

---

**VIKI: Virtual Intelligence, Real Evolution.**
