# VIKI: Sovereign Digital Intelligence
> **Autonomous AI Agent System | Orythix Cognitive Architecture | Virtual Intelligence Knowledge Interface**

<div align="center">

**Polymorphic Intelligence | Recursive Governance | Autonomous Self-Forging**

[![Version](https://img.shields.io/badge/version-7.2.0-blue.svg)](./CHANGELOG.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-orange.svg)](https://ollama.ai)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-green.svg)](./LICENSE)

---

**VIKI** is the world's first **Sovereign Digital Intelligence** built for absolute privacy and local-first autonomy. Unlike standard chatbots, VIKI utilizes the **Orythix Cognitive Architecture** to perform deep reasoning, multi-tool orchestration, and recursive self-improvement without ever leaking your data to the cloud.

[Features](#core-pillars-v720) • [Architecture](#technical-architecture) • [Quick Start](#quick-start) • [Security](#security--ethics)

</div>

---

## The Sovereign Evolution

VIKI is a **Sovereign Digital Intelligence** designed to be more than just an assistant—she is a partner that evolves alongside your workflow. Built on a foundation of **local-first privacy** and **deterministic governance**, VIKI balances the raw power of LLMs with the safety of a modular, capability-aware architecture.

### Core Pillars (v7.2.0)

*   **Intelligence Governance**: Powered by the **Judgment Engine**. Every directive is filtered through a cognitive triage (Reflex, Shallow, Deep) to ensure the right model is used for the right task while maintaining absolute safety.
*   **The Neural Forge**: A integrated pipeline in the core kernel. VIKI extracts "Wisdom" from her SQLite-backed semantic memory and automatically forges new, project-aware model variants (e.g., `viki-evolved`) based on **Phi-3**, **Mistral**, and **DeepSeek-R1**.
*   **Capability-Aware Execution**: Granular permission gating. Skills like `filesystem_write` and `shell_exec` are managed by a centralized `CapabilityRegistry`, ensuring high-risk actions never bypass security protocols.
*   **Recursive Self-Reflection**: Utilizing the **Reflection Layer**, VIKI critiques her own plans before execution, reducing hallucinations and improving tool-use accuracy.
*   **Unified Persistence Layer**: A multi-tiered SQLite architecture that allows VIKI to retain project context, user preferences, and historical lessons without the overhead of legacy JSON files.

---

## Technical Architecture

### 🌌 **The Nexus Stack (OpenClaw-Grade Autonomy)**
VIKI is no longer confined to a single terminal. She is a multi-platform autonomous presence:
- **Unified Messaging Nexus**: Simultaneous integration with **Telegram, Discord, Slack, and WhatsApp**.
- **Autonomous Productivity**: Managed via dedicated **Email** and **Calendar** skills.
- **Deep Research**: Real-time web browsing and information synthesis using Playwright.
- **System Orchestration**: Cross-platform control for Windows, macOS, and Linux.

VIKI operates on a **5-Layer Consciousness Stack**:

1.  **Perception**: Ingests multi-modal inputs (Text, Visuals, Signals).
2.  **Interpretation**: Judgment Engine classifies intent and risk.
3.  **Deliberation**: The Cortex reasons across specialized local models.
4.  **Reflection**: Evaluates the plan against safety and logic constraints.
5.  **Execution**: Capability-gated skill deployment via the Controller.

### Directory Structure

```text
VIKI/
├── viki/
│   ├── core/               # Cognitive Kernel (Judgment, Cortex, Learning)
│   ├── config/             # Orchestration & Soul profiles
│   ├── skills/             # Modular Ability System (FS, Shell, Research)
│   ├── api/                # Unified Nexus (Discord, Telegram, Web)
│   └── main.py             # Autoritative Entry point
├── data/                   # SQLite Persistent Wisdom & Facts
├── logs/                   # Structured Telemetry & Audit Trails
└── tests/                  # Core stability & Benchmark suites
```

---

## Quick Start

### Prerequisites
*   **Python 3.11+**
*   **Ollama CLI**: Installed and running (`ollama serve`).
*   **Recommended Models**: `phi3` (Reflex), `deepseek-r1` (Reasoning).

### Installation
1.  **Clone & Initialize**:
    ```powershell
    git clone https://github.com/toozuuu/viki.git
    cd viki
    python -m venv .venv
    ./.venv/Scripts/Activate.ps1
    pip install -r requirements.txt
    ```

2.  **Set Security Variables** (required for API; optional for CLI):
    ```powershell
    $env:VIKI_API_KEY = (python -c "import secrets; print(secrets.token_urlsafe(32))")
    $env:VIKI_ADMIN_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(32))")
    ```
    See [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md) for full details.

3.  **Launch VIKI (CLI)**:
    ```powershell
    python viki/main.py
    ```

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

---

## The Forge Workflow: "Baking Intelligence"

Unlike static bots, VIKI grows. Every 10 stable lessons learned, she initiates a **Neural Evolution**:

1.  **Interact**: Use VIKI for your dev tasks.
2.  **Learn**: VIKI stores "Lessons" in her internal SQLite knowledge base.
3.  **Forge**: The system automatically triggers the forge when stability milestones are met.
4.  **Verify**: VIKI now responds with built-in awareness of your latest project state, no RAG required.

---

## Security & Ethics
*   **API Authentication**: All API endpoints require `VIKI_API_KEY`. Set via environment variable; see [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md).
*   **Admin Commands**: Super-admin uses `VIKI_ADMIN_SECRET` (env). Never commit secrets; use env or a secrets manager.
*   **Privacy**: 100% Local. No telemetry. No external API calls unless explicitly configured for internet research.
*   **Control**: Every terminal command and filesystem modification is logged and gated. File operations are sandboxed.
*   **Audit**: Check `logs/viki.log` and `viki/SECURITY_SETUP.md` for capability checks and setup.

## Documentation
| Document | Description |
|----------|--------------|
| [SETUP.md](SETUP.md) | Installation and environment |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design and data flow |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [viki/DOCS_INDEX.md](viki/DOCS_INDEX.md) | Index of all viki documentation |
| [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md) | Security configuration |
| [viki/IMPLEMENTATION_SUMMARY.md](viki/IMPLEMENTATION_SUMMARY.md) | Security & stability fixes |
| [viki/MODEL_ENHANCEMENT_SUMMARY.md](viki/MODEL_ENHANCEMENT_SUMMARY.md) | Model improvement system |
| [viki/ARCHITECTURE_REFACTOR.md](viki/ARCHITECTURE_REFACTOR.md) | Future refactoring roadmap |
| [viki/OBSERVABILITY.md](viki/OBSERVABILITY.md) | Logging and metrics plan |
| [viki/PERFORMANCE_NOTES.md](viki/PERFORMANCE_NOTES.md) | Performance optimization notes |

---

**VIKI: Virtual Intelligence, Real Evolution.**
Designed by Orythix. 2026.