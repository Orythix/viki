# VIKI: Sovereign Digital Intelligence
> **Virtual Intelligence Knowledge Interface | Version 2.3.0 Nexus Core**

<div align="center">

**Polymorphic Intelligence | Recursive Governance | Autonomous Self-Forging**

[![Version](https://img.shields.io/badge/version-2.3.0-blue.svg)](./CHANGELOG.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-orange.svg)](https://ollama.ai)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-green.svg)](./LICENSE)

</div>

---

## The Sovereign Evolution

VIKI is a **Sovereign Digital Intelligence** designed to be more than just an assistant—she is a partner that evolves alongside your workflow. Built on a foundation of **local-first privacy** and **deterministic governance**, VIKI balances the raw power of LLMs with the safety of a modular, capability-aware architecture.

### Core Pillars (v2.3.0)

*   **Intelligence Governance**: Powered by the **Judgment Engine**. Every directive is filtered through a cognitive triage (Reflex, Shallow, Deep) to ensure the right model is used for the right task while maintaining absolute safety.
*   **The Ollama Oven**: A breakthrough in local model alignment. VIKI extracts "Wisdom" from her semantic memory and automatically forges new, project-aware model variants (e.g., `viki-born-again`) based on **Mistral** and **DeepSeek-R1**.
*   **Capability-Aware Execution**: Granular permission gating. Skills like `filesystem_write` and `shell_exec` are managed by a centralized `CapabilityRegistry`, ensuring high-risk actions never bypass security protocols.
*   **Recursive Self-Reflection**: Utilizing the **Reflection Layer**, VIKI critiques her own plans before execution, reducing hallucinations and improving tool-use accuracy.
*   **Integrated Long-Term Memory**: A multi-tiered memory system (Episodic SQLite + Semantic JSON) that allows VIKI to retain project context, user preferences, and historical lessons.

---

## Technical Architecture

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
│   ├── core/               # Cognitive Kernel (Judgment, Cortex, Capabilities)
│   ├── config/             # Orchestration & Soul profiles
│   ├── skills/             # Modular Ability System (FS, Shell, Research)
│   └── main.py             # Entry point & Dashboard
├── scripts/                
│   ├── ollama_oven.py      # Automated Model Forging
│   └── export_viki_*.py    # Dataset extraction (Alpaca/ShareGPT)
├── data/                   # Semantic Wisdom & Fact Storage
└── logs/                   # Structured Telemetry & Audit Trails
```

---

## Quick Start

### Prerequisites
*   **Python 3.10+**
*   **Ollama CLI**: Installed and running (`ollama serve`).
*   **Recommended Models**: `mistral` (General), `deepseek-r1` (Reasoning).

### Installation
1.  **Clone & Initialize**:
    ```powershell
    git clone https://github.com/toozuuu/viki.git
    cd viki
    python -m venv .venv
    ./.venv/Scripts/Activate.ps1
    pip install -r requirements.txt
    ```

2.  **Forge Your Identity**:
    Run the Oven to create your first personalized model:
    ```powershell
    python scripts/ollama_oven.py
    ```

3.  **Launch**:
    ```powershell
    python viki/main.py
    ```

---

## The Oven Workflow: "Forging Intelligence"

Unlike static bots, VIKI grows. Every time she learns a new fact or completes a complex project, you can "bake" that knowledge into her core:

1.  **Interact**: Use VIKI for your dev tasks.
2.  **Learn**: VIKI stores "Lessons" in `data/lessons_semantic.json`.
3.  **Forge**: Run `scripts/ollama_oven.py`.
4.  **Verify**: VIKI now responds with built-in awareness of your latest project state, no RAG required.

---

## Security & Ethics
*   **Privacy**: 100% Local. No telemetry. No external API calls unless explicitly configured for internet research.
*   **Control**: Every terminal command and filesystem modification is logged and gated.
*   **Audit**: Check `logs/viki.log` for a transparent record of all capability checks.

---

**VIKI: Virtual Intelligence, Real Evolution.**
Designed by Sachin. 2026.