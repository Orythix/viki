> **Supreme Architect of The Code Eternal. An advanced autonomous AI agent system with cognitive architecture (Orythix), local multi-model routing, self-healing incident response, and high-performance terminal interface.**

<div align="center">

# 🤖 VIKI: Sovereign Autonomous AI Agent & Local LLM Engineer

**Local LLM Orchestration • Air-Gapped Privacy • Autonomous Self-Evolution • Full-SDLC Engineering Swarm**

[![Build & Tests](https://img.shields.io/badge/pytest-487%20passed-success.svg)](https://github.com/Orythix/viki)
[![Mypy Strict](https://img.shields.io/badge/mypy-0%20errors-success.svg)](https://mypy-lang.org)
[![Ruff](https://img.shields.io/badge/ruff-passing-brightgreen.svg)](https://docs.astral.sh/ruff)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![Local LLMs](https://img.shields.io/badge/Local%20LLM-LM%20Studio%20%7C%20Ollama-blue.svg)](https://lmstudio.ai)
[![Cloud LLMs](https://img.shields.io/badge/Cloud%20LLMs-OpenAI%20%7C%20Claude%20%7C%20Gemini-orange.svg)](https://github.com/Orythix/viki)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](./docs/DOCKER.md)

---

[Key Features](#-key-features) • [Multi-Model Provider Matrix](#-multi-model-provider-matrix) • [Architecture](#-technical-architecture) • [Quick Start](#-quick-start) • [Engineering Playbooks](#-engineering-playbooks--sdlc) • [Neural Forge](#-build-your-viki-model-neural-forge) • [FAQ](#-frequently-asked-questions) • [License](#-license)

</div>

---

## 💡 What is VIKI? (Project Overview)

**VIKI** (**Virtual Intelligence Knowledge Interface**) is a production-grade, **self-hosted autonomous AI agent** and **developer-first AI engineer** written in Python. Built for **local-first privacy** and **zero data leakage**, VIKI runs natively on your hardware via **LM Studio** and **Ollama**, while seamlessly supporting cloud frontier models (**OpenAI GPT-4o**, **Anthropic Claude 3.7 Sonnet**, **Google Gemini 2.5 Pro**).

Powered by the **Orythix Cognitive Architecture**, VIKI provides deep ReAct reasoning, multi-agent swarm orchestration, automated incident healing (Sentry/Datadog stack trace ingestion), persistent SQLite RAG memory, and self-evolution through the **Neural Forge**—all accessible via an ultra-fast **CLI-first** REPL and web dashboard.

---

## ⚡ Key Features

- 🔒 **100% Sovereign & Air-Gap Capable**: Default operation never leaves your local network (`VIKI_AIR_GAP=1`). Zero telemetry, zero external tracking.
- 🧠 **Orythix 5-Layer Cognitive Cortex**: Judgment, Deliberation, Reflection, Execution, and Meta-Cognition layers reduce hallucinations and audit plans before execution.
- 🔄 **Multi-Model Provider Routing**: Instantly switch or auto-route between **LM Studio**, **Ollama**, **OpenAI**, **Anthropic Claude**, and **Google Gemini**.
- 🛠️ **Full-SDLC & Jira Automation**: Automated Jira ticket parsing, technical spec generation, TDD test suites, AST codemods, and OpenAPI 3.1 / gRPC proto generation.
- 🚑 **Autonomous Incident Healing**: Connects to Sentry/Datadog webhooks, reproduces bugs in isolated Git worktrees, applies targeted fixes, verifies via pytest, and creates PRs.
- ⚡ **Multi-Agent Swarm Engineering**: Execute complex DAG tasks using leader-worker agent swarms and Monte Carlo Tree Search (MCTS) reasoning.
- 📦 **Local Neural Forge**: Bakes user feedback and lessons accumulated in SQLite directly into custom model system prompts without GPU training.
- 🚀 **Low-Hardware Optimization**: Runs efficiently on **8 GB RAM** laptops (with dedicated 4k token caps, prompt compression, and LRU entity extraction caching).
- ⚙️ **Capability Gating & Security**: Sandboxed file and shell execution (`viki/core/sandbox.py`) with strict permission boundaries and prompt injection detection.

---

## 🤖 Multi-Model Provider Matrix

VIKI dynamically routes queries to the optimal provider profile configured in [`config/models.yaml`](config/models.yaml):

| Provider | Supported Models / Endpoints | Privacy / Mode | Best For |
| :--- | :--- | :--- | :--- |
| **LM Studio** | `gemma-4-e4b`, `qwen3.5-9b`, `deepseek-r1` (`http://localhost:1234/v1`) | **100% Local / Air-Gapped** | Default offline coding & privacy |
| **Ollama** | `llama3`, `codellama`, `mistral`, `phi3` (`http://localhost:11434/v1`) | **100% Local / Air-Gapped** | Local CLI automation & zero-cost tasks |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini`, `o3-mini` | Cloud API | Deep architectural reasoning & code review |
| **Anthropic** | `claude-3-7-sonnet`, `claude-3-5-haiku` | Cloud API | Full-SDLC engineering & complex refactoring |
| **Google** | `gemini-2-5-pro`, `gemini-2-5-flash` | Cloud API | Multimodal vision & massive context research |

---

## 🏗️ Technical Architecture

VIKI executes tasks through a deterministic **5-Layer Consciousness Cortex**:

```mermaid
graph TD
    A["User Prompt / Event Trigger"] --> B["Layer 1: Perception & Request Pipeline"]
    B --> C["Layer 2: Judgment Engine (Reflex vs Deliberation)"]
    C -->|Reflex Path| D["Instant Short-Circuit Execution"]
    C -->|Deliberate Path| E["Layer 3: Cortex & Multi-Model Router"]
    E --> F["Layer 4: Reflection & Hallucination Audit"]
    F --> G["Layer 5: Execution & Capability Registry"]
    G --> H["Layer 6: Meta-Cognition & Memory Persistence"]
    H --> I["SQLite RAG Wisdom DB & Neural Forge"]
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+** (3.10, 3.11, and 3.12 supported)
- **Local Inference Server**: [LM Studio](https://lmstudio.ai) or [Ollama](https://ollama.ai) running locally (`http://localhost:1234` or `http://localhost:11434`)

### 1. Installation

```bash
# Clone repository
git clone https://github.com/Orythix/viki.git
cd viki

# Create & activate virtual environment
python -m venv .venv
# On Windows (PowerShell):
./.venv/Scripts/Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install core package
pip install -e .
```

### 2. Configure Environment

```bash
cp .env.example .env
```
*(Optionally set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or custom `VIKI_PERSONA` in `.env`)*

### 3. Launch VIKI

```bash
# Start interactive CLI REPL in current workspace
viki

# Single-shot command (runs task and exits)
viki "refactor auth logic in src/viki/core/security.py"

# Run with Dev Persona (coding-focused skills)
VIKI_PERSONA=dev viki
```

---

## 🐳 Docker Deployment

Run VIKI in an isolated container using Docker Compose:

```bash
# Build and run interactive container
docker compose build
docker compose run --rm -it viki
```

*See [docs/DOCKER.md](docs/DOCKER.md) for advanced container configurations.*

---

## 📚 Engineering Playbooks & SDLC

VIKI includes **40+ built-in engineering playbooks** spanning the complete software development lifecycle:

- 📐 **Define & Plan**: `idea_refine`, `spec_driven_development`, `planning_and_task_breakdown`, `jira_sdlc_workflow`
- 🔨 **Build & Refactor**: `incremental_implementation`, `test_driven_development`, `ast_codemod`, `openapi_schema`, `frontend_ui_engineering`
- 🔍 **Verify & Review**: `browser_testing_with_devtools`, `debugging_and_error_recovery`, `code_review_and_quality`, `security_and_hardening`
- 🚢 **Ship & Recover**: `git_workflow_and_versioning`, `ci_cd_and_automation`, `autonomous_incident_healing`

---

## 🧪 Build Your VIKI Model (Neural Forge)

Bake your accumulated SQLite lessons and project wisdom directly into custom LM Studio model profiles without GPU training:

```bash
# Bake top lessons into data/Modelfile.viki_evolved
python scripts/build_viki_model.py

# Set models.yaml default profile to lmstudio-gemma4e4b
python scripts/build_viki_model.py --set-default
```

---

## 📊 Comparison: VIKI vs Other AI Agents

| Feature | VIKI | AutoGPT | LangChain | Manus / Devin |
| :--- | :---: | :---: | :---: | :---: |
| **Air-Gapped Privacy** | ✅ 100% Local | ❌ Cloud API | ⚠️ Library only | ❌ Cloud Hosted |
| **Local LLM Native** | ✅ LM Studio / Ollama | ⚠️ Limited | ⚠️ Requires code | ❌ Cloud Hosted |
| **Incident Healing (Sentry)** | ✅ Built-in | ❌ No | ❌ No | ⚠️ Proprietary |
| **Neural Forge Evolution** | ✅ Built-in | ❌ No | ❌ No | ❌ No |
| **MCTS Swarm Execution** | ✅ Built-in | ❌ No | ⚠️ Manual DAG | ⚠️ Proprietary |
| **Open Source License** | ✅ Apache-2.0 | ✅ MIT | ✅ MIT | ❌ Closed |

---

## ❓ Frequently Asked Questions

<details>
<summary><b>Is VIKI completely free and open source?</b></summary>
Yes! VIKI is released under the <b>Apache-2.0</b> open source license. You can self-host, modify, and deploy VIKI freely without any required cloud subscription.
</details>

<details>
<summary><b>Does VIKI support cloud AI models like Claude or GPT-4o?</b></summary>
Yes! VIKI features a unified provider adapter supporting LM Studio, Ollama, OpenAI (GPT-4o), Anthropic (Claude 3.7 Sonnet), and Google Gemini (2.5 Pro). Configure your API keys in <code>.env</code> or <code>config/models.yaml</code>.
</details>

<details>
<summary><b>Can VIKI run on laptops with 8 GB RAM?</b></summary>
Yes! VIKI is specifically optimized for low-spec hardware (4 GB / 8 GB RAM) with aggressive token capping, prompt compression, LRU entity extraction caching, and lazy skill loading.
</details>

---

## 📖 Documentation Index

- 📑 [Full Documentation Sitemap](docs/DOCUMENTATION.md)
- 🚀 [Installation & Setup Guide](docs/SETUP.md)
- 📖 [VIKI Runbook & Troubleshooting](docs/VIKI_RUNBOOK.md)
- 🐳 [Docker Deployment Guide](docs/DOCKER.md)
- 🏛️ [System Architecture & Data Flow](docs/ARCHITECTURE.md)
- 🔒 [Security Policy & Capability Gating](docs/SECURITY.md)

---

## 🔍 Keywords & Topics

`Local AI Agent` • `Autonomous AI Engineer` • `Self-Hosted AI Assistant` • `LM Studio Agent` • `Ollama Agent` • `Air-Gapped AI` • `Sovereign AI` • `ReAct Reasoning` • `Model Context Protocol (MCP)` • `Agentic SDLC` • `Sentry Bug Healing` • `Neural Forge` • `Private LLM` • `Python AI Agent`

---

## 📄 License

VIKI is licensed under the [Apache License 2.0](./LICENSE).
