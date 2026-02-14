# VIKI: Sovereign Digital Intelligence
> **Virtual Intelligence Knowledge Interface | Version 7.1.0 Nexus Core**

<div align="center">

**Polymorphic Intelligence | Recursive Governance | Autonomous Self-Forging**

[![Version](https://img.shields.io/badge/version-7.1.0-blue.svg)](./CHANGELOG.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-orange.svg)](https://ollama.ai)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-green.svg)](./LICENSE)

</div>

---

## The Sovereign Evolution

VIKI is a **Sovereign Digital Intelligence** designed to be more than just an assistant—she is a partner that evolves alongside your workflow. Built on a foundation of **local-first privacy** and **deterministic governance**, VIKI balances the raw power of LLMs with the safety of a modular, capability-aware architecture.

### Core Pillars (v7.1.0)

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

2.  **Launch VIKI (CLI)**:
    ```powershell
    python viki/main.py
    ```

3.  **Launch Dashboard (UI)**:
    Open two terminals:
    - Terminal 1 (API): `python viki/api/server.py`
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
*   **Privacy**: 100% Local. No telemetry. No external API calls unless explicitly configured for internet research.
*   **Control**: Every terminal command and filesystem modification is logged and gated.
*   **Audit**: Check `logs/viki.log` for a transparent record of all capability checks.

---

**VIKI: Virtual Intelligence, Real Evolution.**
Designed by Sachin. 2026.