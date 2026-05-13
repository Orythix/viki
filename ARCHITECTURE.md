# VIKI Architecture (v8.1.1 Industrial)

## Core Philosophy
Following the **Industrial Restructuring**, VIKI follows a **Clean Architecture (Hexagonal)** and **Domain-Driven Design (DDD)** pattern:
1.  **Dependency Injection (Inversion of Control)**: All core services and use cases are managed by a central `Container` (`viki/container.py`). This decouples object creation from business logic.
2.  **Layered Separation of Concerns**:
    *   **Domain**: Pure business logic, entities, and repository interfaces. No external dependencies.
    *   **Application**: Orchestrates use cases and application services (e.g., `SafetyService`).
    *   **Infrastructure**: Concrete implementations of domain interfaces.
    *   **Presentation**: External interfaces (CLI, REST API, Event Bus).
3.  **Repository Pattern**: Data access is abstracted through interfaces, allowing seamless swapping of persistence layers.
4.  **Autonomous Safety**: Safety logic is encapsulated in an application service and injected into the execution pipeline, ensuring consistent policy enforcement.
5.  **Polymorphic Intelligence**: Cognition remains tiered (Reflex, Chatter, Planning), but orchestrated through clean use-case boundaries.

## Module Breakdown

### 1. The Container (`viki/container.py`)
*   **Role**: Composition Root.
*   **Function**: Manages the lifecycle and wiring of all application components. Uses `dependency-injector` to provide singleton services to the controller and presentation layers.

### 2. The Controller (`viki/core/controller.py`)
*   **Role**: Application Coordinator.
*   **Function**: Acts as the primary entry point for the "Think-Action-Learn" loop. Dependencies (Safety, Memory Recall, Model Router) are injected from the Container. It manages **Latency Budgeting** to maintain system responsiveness during high-complexity tasks.

### 3. Application Services (`viki/application/`)
*   **Safety Service**: Encapsulates the safety envelope and action validation.
*   **Memory Recall Use Case**: Orchestrates semantic retrieval from the learning repository.

### 4. Infrastructure Adapters (`viki/infrastructure/`)
*   **Learning Repository**: SQLAlchemy-based implementation for managing lessons and failures in SQLite with WAL mode.
*   **Inference Gateway**: Bridge to Ollama and cloud providers.
*   **Event Bus**: Asynchronous message passing.

### 5. Model Enhancement & Observability
*   **Knowledge Gaps** (`viki/core/knowledge_gaps.py`): Records low-confidence responses; dream research uses `get_research_topics()`.
*   **Pattern Tracker**: Persists patterns to disk; survives restarts.
*   **Performance Metrics**: Tracked internally for model routing and selection.
*   **Continuous Learner** (`viki/core/continuous_learning.py`): Optional periodic training cycles with validation.

See [viki/skills/creation/forge.py](viki/skills/creation/forge.py) (Neural Forge: prompt-bake writes `data/Modelfile.viki_evolved`, then `ollama create` with default tag **`viki-neural-forge`**, overridable via `system.forge_output_ollama_tag` / `VIKI_FORGE_OUTPUT_OLLAMA_MODEL`; optional LoRA) and [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md) for operational details. CLI entry: [scripts/build_viki_model.py](scripts/build_viki_model.py).

## Cognitive Data Flow
```mermaid
    User[User Input] --> Nexus{Priority Nexus}
    Nexus -->|P10: Urgent| Controller
    Nexus -->|P30: Proactive| Controller
    
    Controller --> SafetyCheck{Safety Envelope}
    SafetyCheck -->|Safe| Executor[Skill Executor]
    SafetyCheck -->|Risky| Confirm[Awaiting /confirm]
    
    Controller --> Memory[RAG + Failure Memory]
    Controller --> Router{Model Router}
    
    Router -->|Reflex| Phi3(Local)
    Router -->|Chat| Llama3(Local)
    Router -->|Plan| DeepSeek(Cloud/Local)
    
    Executor -->|Success| UI[CLI / Messaging Bridge]
    Executor -->|Fail| Record[Record Failure]
    Record --> Memory
```

## Frontier Wiring (2026 Gap-Closure)

The original "5-Layer Consciousness Stack" claims now match implementation. Each
of the items below was wired up during the internal **frontier / gap-closure** effort
and is exercised by tests under `viki/tests/`:

- **MCP integration is live.** [`viki/integrations/mcp_client.py`](viki/integrations/mcp_client.py) is loaded at controller boot via `attach_mcp_skills_sync`. External tools listed in [`viki/config/mcp_servers.yaml`](viki/config/mcp_servers.yaml) appear as native skills.
- **Promotion gate fixed.** `ContinuousLearner._capability_index_for` now constructs `CapabilityIndex(results_root, min_tasks, bootstrap_iters)` using positional/typed args.
- **LSP bridge is functional.** `hover`, `references`, `definition`, and `publishDiagnostics` are implemented in [`viki/integrations/lsp_bridge.py`](viki/integrations/lsp_bridge.py).
- **Computer-use grounding is real.** No more dummy full-screen bbox; low-confidence detections are rejected, and an OmniParser-V2 ONNX adapter is loaded when `VIKI_OMNIPARSER_ONNX` points at a model file.
- **Vector memory lexical fallback ranks.** `_LexicalFallbackBackend.search` now does Jaccard token-overlap scoring.
- **Capability Index hardening (P2).** Min-task threshold, 95% bootstrap CI per suite, and SHA256 provenance hashes are computed in [`viki/core/capability_index.py`](viki/core/capability_index.py).
- **Real benchmark adapters.** [`scripts/evals/datasets.py`](scripts/evals/datasets.py) provides downloadable adapters for major datasets.
- **Persistent code-search index + watcher.** [`viki/skills/builtins/code_search_skill.py`](viki/skills/builtins/code_search_skill.py) writes to `data/code_index.db`.
- **Best-of-N worktrees.** [`viki/core/worktree_runner.py`](viki/core/worktree_runner.py) runs parallel `PlanEditSkill` attempts in isolated `git worktree`s.
- **Sandboxed code execution.** [`viki/core/sandbox.py`](viki/core/sandbox.py) provides a Docker backend used by the python-interpreter and shell skills.
- **Tracing is persistent.** [`viki/core/tracing.py`](viki/core/tracing.py) propagates `trace_id`/`parent_span_id` via `contextvars` and persists to `data/traces.db`.
- **Multi-modal attachments.** `_AttachmentStage` in [`viki/core/request_pipeline.py`](viki/core/request_pipeline.py) routes images through a `vision` skill, audio through `whisper`, and inlines text attachments.
- **`history.undo_last()` is implemented.** Used by the new `/undo` slash command.
- **Bio sensing is honest about scope (P2).** `BioModule(backend="stub")` is the default. Set `system.bio_backend: deepface` to opt into the real DeepFace path.
- **Dynamic skills (P2).** SQL skill supports SQLite/Postgres/MySQL; AWS skill uses boto3 paginators; kubectl skill supports streamed logs.
- **Tier-1 integration tests.** Boot smoke ([`viki/tests/test_controller_boot.py`](viki/tests/test_controller_boot.py)), MCP ([`viki/tests/test_mcp_integration.py`](viki/tests/test_mcp_integration.py)), continuous learning ([`viki/tests/test_continuous_learning_integration.py`](viki/tests/test_continuous_learning_integration.py)), Cortex layers ([`viki/tests/test_cortex_layers.py`](viki/tests/test_cortex_layers.py)), and existing LSP bridge tests pin the wiring.

## Low-resource mode (low-end PC optimization)

VIKI ships with two coordinated low-resource paths so the agent stays usable on 4 GB / 4-core machines:

- **Lazy heavy skills.** `viki/skills/lazy_skill.py` defines `LazySkillProxy`, registered in place of every skill that imports an optional heavy dep (`torch`, `playwright`, `pandas`, `pdfplumber`, `whisper`, `onnxruntime`, …). The proxy advertises stable metadata (name, description, schema, safety tier) so the planner can list the skill without paying the import cost. The real class is constructed inside an `asyncio.Lock`-guarded loader on first `execute(...)`. Failed imports are sticky: subsequent calls return a typed "unavailable" error instead of retrying.
- **`system.low_resource_mode` flag.** When true (or `VIKI_LOW_RESOURCE=1`), `_register_default_skills` logs the mode and the controller skips the autonomous startup pulse, wellness pulse, dream monitor, reflector, watchdog, and the continuous-learning loop. Settings-driven cadences (`proactive.wellness_interval_s`, `forge.continuous_learning_*_s`) let operators dial down the remaining heartbeats further.
- **Bounded `PatternTracker`.** `viki/core/cortex.py` caps in-memory entries at `VIKI_PATTERN_TRACKER_MAX` (default 5000) with LRU eviction by `last_seen`, and debounces JSON dumps every `VIKI_PATTERN_TRACKER_SAVE_EVERY` writes (default 10) to keep cheap SSDs / spinning disks happy.

Tests pin both paths: [`viki/tests/test_lazy_skill_proxy.py`](viki/tests/test_lazy_skill_proxy.py) verifies metadata-without-load, deferred import, and failure isolation. [`viki/tests/test_low_resource_mode.py`](viki/tests/test_low_resource_mode.py) boots a real controller with `VIKI_LOW_RESOURCE=1` and asserts that `viki.skills.builtins.{vision,browser,computer_use,whisper,pdf,…}_skill` modules are *not* in `sys.modules` after construction.

## Monorepo siblings (not imported by `viki/`)

These directories ship in the same repository but are **optional** sidecars:

| Path | Role |
|------|------|
| [`security-lab/`](security-lab/) | Standalone FastAPI lab: prompt-injection heuristics, RBAC tools, audit DB |
| [`qa-automation/`](qa-automation/) | Learning-oriented API/UI/perf test examples and CI samples |

They do not change runtime imports for `python viki/main.py`; see each folder’s README for setup.

---

*Runbook version: aligned with VIKI v8.1.1 (Industrial). Update this file when default ports, flags, or critical architecture patterns change.*
