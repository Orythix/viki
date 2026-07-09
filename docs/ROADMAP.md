# VIKI Roadmap

The plan to make VIKI the most capable *personal* AI system available — and
the argument for why a local-first system can win against hosted assistants.

Baseline: the production-quality restructure (PR #20, merged July 2026).

**Current status: v8.4.0** — post-restructure work continues with type-safety and architectural clean-up complete (zero mypy errors, mixin-based controller, raised coverage gate).

Update this file as items land; delete what ships, prune what stops making
sense.

---

## The thesis: out-system, not out-model

VIKI will never out-model a frontier lab on raw weights — and it doesn't need
to. Hosted assistants are stateless, sandboxed, and rented. VIKI's edge is
everything *around* the model, and every feature below serves one of these
five advantages:

| # | Advantage | Why hosted assistants can't match it |
|---|-----------|--------------------------------------|
| 1 | **Owned memory** | VIKI's memory is a local database the user owns forever. Hosted context windows reset; VIKI compounds. A year of use should make it measurably smarter *for its owner* than any fresh frontier session. |
| 2 | **True autonomy** | VIKI runs on the user's machine 24/7 — watchers, missions, scheduled work. Hosted agents act only when summoned and die when the tab closes. |
| 3 | **Self-improvement** | The Neural Forge bakes the user's own reinforced lessons into the weights (prompt-bake / LoRA / DPO). The model literally becomes personal. No hosted model retrains on one user. |
| 4 | **Computer-native** | Full OS access: filesystem semantics (`SemanticFS`), window control, overlay, clipboard, shell — not a browser sandbox with screenshots. |
| 5 | **Absolute privacy** | Air-gap mode is a first-class setting. Everything — inference, memory, telemetry — can stay on-device. This is not a policy promise; it's an architecture. |

**Definition of winning.** "Better than existing AI models" is measurable, not
rhetorical. VIKI wins when, for its owner's recurring tasks:

- **Personal task completion** — ≥ 90% completion on the owner's tracked
  mission types, beating a fresh frontier-model session *on those same tasks*
  (the eval harness makes this an A/B, not a vibe).
- **Memory advantage** — recall of owner-specific facts/preferences at ≥ 95%
  precision after 6 months of use (frontier baseline: near zero across sessions).
- **Reflex latency** — < 300 ms for reflex-path answers, < 2 s first token for
  local deliberation on mid-range hardware.
- **Autonomy throughput** — useful background work completed per week
  (missions, ingestion, self-training runs) — a number hosted assistants
  cannot post at all.
- **Zero-egress mode** — full feature set minus web research with the network
  cable pulled.

Track all five on the scorecard dashboard (`IntelligenceScorecard` already
persists trends).

---

## Done (restructure, July 2026)

See PR #20 and `CHANGELOG.md` for detail.

- **Packaging** — `viki` console entry point, optional `[ml]` extra,
  committed `uv.lock`, single pytest config.
- **Content extraction** — 228 playbooks moved to `playbooks/` (wheel:
  0.6 MB); sovereign skill library ships as package data (fixed a silent
  no-load bug).
- **Import canonicalization** — single `viki.*` namespace; dual-identity
  `sys.path` hack removed.
- **Orchestrator split** — `VIKIController` 2,369 → 436 lines via five
  thematic mixins (Lifecycle, Skills, Pipeline, Validation, Telemetry).
- **Tests** — `tests/unit/` + test modules throughout codebase; three
  never-collected test files revived, 10 new controller-mixin tests added.
- **CI** — whole-repo ruff + format gates, strict mypy (zero errors),
  coverage gate set to 40%, security-lab workflow.

## Done (post-restructure, through August 2026)

### Reflex & latency
- **ReflexBrain** — instant reflex path (< 300 ms) for known patterns
  (`src/viki/core/rapid_response_system.py`); `_process_reflex_outcome`
  hook for background verification.
- **Token streaming** — streaming path exists in the cortex; partial CLI
  and dashboard integration.

### Memory & knowledge
- **HierarchicalMemory** — working, episodic, and semantic tiers live in
  `src/viki/core/memory/` with cross-tier promotion.
- **IntelligenceScorecard** — persists trend data; measures latency, task
  pass rate, and memory precision (`src/viki/core/scorecard.py`).
- **KnowledgeGapDetector** — identifies gaps and feeds ingestion
  (`src/viki/core/knowledge_gaps.py`).
- **DreamModule** — idle-time state consolidation with deduplication and
  contradiction resolution (`src/viki/core/state_consolidation.py`).
- **PreferenceForge** — captures `/confirm`/`/reject` as DPO pairs
  (`src/viki/core/preference_forge.py`).

### Inference & routing
- **ModelRouter** — telemetry-driven task routing with automatic failover
  (local → LM Studio → cloud API); provider support for Ollama, LM Studio,
  OpenAI, Azure, Anthropic, Google, NVIDIA NIM
  (`src/viki/core/model/model_router.py`).
- **OpenAI-compatible provider** — LM Studio / vLLM / llama.cpp server
  provider with documented config.
- **Structured prompting** — `chat_structured` with parse-and-retry for
  `VIKIResponse` (`src/viki/core/model/structured_prompt.py`).
- **ModelABTest** — A/B comparison harness (`variant_optimizer.py`).

### Autonomy & architecture
- **Single DI container** — `service_registry.py` replaces the dual-DI
  pattern (zero-dependency, ~215 lines).
- **Request pipeline** — `request_pipeline.py` extracted from
  `VIKIController._process_request_impl` (518 lines, testable stages).
- **Clean-architecture layers** — `domain/entities/`, `domain/interfaces/`,
  `application/services/`, `application/use_cases/`, `infrastructure/`
  committed; `sqlalchemy_learning_repository` noted as blocked (no
  SQLAlchemy dep).
- **Type-safety enforcement** — mypy runs with zero errors across 283 files;
  `warn_unused_ignores` prevents stale suppressions. Bare `print()` banned
  from library code; 63 silent exception handlers now emit structured
  warnings (`pyproject.toml`, dozens of `src/viki/` modules).
- **CLI restructuring** — `cli.py` (1,218 lines) split into a 3-module
  package under `viki.cli/`, preserving the `viki.cli:run` entry point.
- **MissionControl** — persists missions with mission types, status,
  and progress events (`src/viki/core/mission_control.py`).
- **MissionGraph** — DAG-based mission decomposition and execution
  (`src/viki/core/mission_graph.py`).

### Computer-native features
- **SemanticFS** — filesystem layer with semantic operations
  (`src/viki/core/filesystem_v2.py`).
- **WorldModel** — live environment model with project landmarks and
  safety zones (`src/viki/core/world.py`).
- **SwarmOrchestrator** — basic sub-agent delegation with type contracts
  and budgets (`src/viki/application/services/swarm_orchestrator.py`).
- **MessagingNexus** — bridge hub for Telegram, Discord, Slack, WhatsApp
  (`src/viki/api/central_nexus.py`).
- **Dashboard** — aiohttp web dashboard with streaming, memory browser,
  and event bus (`src/viki/api/dashboard.py` + `dashboard.html`).
- **MCP client** — Model Context Protocol client for external tool
  integration (`src/viki/integrations/mcp_client.py`).
- **audio_gateway** — VoiceModule with VAD, wake word detection, TTS
  (`src/viki/core/audio_gateway.py`).
- **overlay_skill** — screen overlay for action previews and click
  targets (`src/viki/skills/builtins/overlay_skill.py`).
- **Computer use** — vision + grounding + perceive-act-verify loop
  (`src/viki/skills/builtins/computer_use.py`).

### Self-improvement
- **Neural Forge** — LoRA fine-tuning pipeline (`forge_lora.py`),
  `ForgeOrchestrator` in application layer, `evolution_engine.py` as
  top-level orchestrator.
- **SelfCritique** — agent output quality self-assessment
  (`src/viki/core/self_critique.py`).
- **Reranker** — second-stage RAG reranker for retrieval precision
  (`src/viki/core/reranker.py`).

### Skills ecosystem
- **60 built-in skills** — overlay, computer use, shell, filesystem,
  browser, calendar, clipboard, code_search, coding_workflow, context
  weaver, data_analysis, email, engineering_playbook, image_gen, LSP,
  memory, messaging, mind_trace, mutation_pilot, obsidian, pdf, plan_edit,
  recall, research, swarm, system_control, vision, voice, whisper,
  window_management, and more (`src/viki/skills/builtins/`).
- **Dynamic skill creation** — forge-driven skill synthesis with automatic
  registration (`src/viki/skills/creation/forge.py`).
- **Public Safety framework** — domain structure with agents, audit,
  auto-learning, NL bridge (`src/viki/skills/public_safety/`).

---

## Remaining engineering phases

These make the codebase trustworthy enough to build the feature waves on.
Order matters: don't stack features on unstable ground.

### Phase A — Stabilize the restructure ✓
- [x] Manual smoke of interactive CLI (`viki --low-resource`) and dashboard
  (`viki --dashboard`) — verified working.
- [x] CI runs on the 3.10–3.12 matrix — stable across Windows/3.11 and
  torch-free venv.

### Phase B — Type-safety ratchet
- [~] Burn down mypy module-by-module: `viki.core.schema`, `viki.config`,
  the new mixins, then outward — ongoing.
- [x] Typed `ControllerProto` protocol for mixin `self` attributes
  (`src/viki/core/protocols.py`).
- [ ] Flip CI mypy from advisory to blocking.

### Phase C — Finish the de-godification ✓
- [x] Collapse the two DI mechanisms (`service_registry` + the `cli.py`
  container) into one — `service_registry.py` now serves as the single
  zero-dependency DI container (~215 lines).
- [x] Extract `_process_request_impl` into the `request_pipeline` stage
  model — `request_pipeline.py` (518 lines, testable preflight stages).
- [x] Resolve the half-built clean-architecture layer — `domain/`,
  `application/`, `infrastructure/` committed; `sqlalchemy_learning_repository`
  rewritten as pure sqlite3 (zero SQLAlchemy dependency,
  `src/viki/infrastructure/database/sqlalchemy_learning_repository.py`).

### Phase D — Scripts to first-class tools
- [x] Console entry points: `viki-forge`, `viki-eval`, `viki-ingest`,
  `viki-mcp` (`src/viki/entry_points.py`, `pyproject.toml`).
- [ ] Fold `scripts/verify_*.py` into `tests/integration/` (marked
  `slow`/`manual`) or delete duplicates.
- [~] Move `scripts/evals/` under `src/viki/eval/` — `src/viki/eval/` exists
  with RAG evaluation utilities; benchmark runners (`scripts/evals/`) pending
  consolidation.

### Phase E — Quality gates ratchet
- [ ] Coverage floor 20 → 25 → 35 → 50 as tests grow.
- [ ] `pip-audit` + Dependabot/Renovate.
- [ ] Docker build in CI; slim (no-`[ml]`) image variant.
- [ ] **Nightly eval harness run** against a pinned local model, scorecard as
  CI artifact — this is the metrics backbone for the whole thesis above.

### Phase F — Release engineering
- [ ] Version from git tags (`setuptools-scm`); changelog per release.
- [ ] PyPI publishing from `release.yml` on tag.
- [ ] Decide `labs/` extraction to separate repos.

---

## Feature waves

Each feature names the existing subsystem it builds on — nothing here starts
from zero. Waves are ordered by dependency and value; within a wave, items
are roughly value-to-effort sorted.

### Wave 1 — Foundation features (make the core loop excellent)

**Intelligence & inference**
- [~] **End-to-end token streaming** in CLI and dashboard — the cortex
  streaming path exists and is partially surfaced; complete coverage across
  all interfaces is ongoing.
- [x] **Telemetry-driven model routing** — routes by task class *and* live
  latency/cost/success stats with automatic failover tiers: local Ollama →
  LM Studio → cloud API (`ModelRouter`, `get_router_telemetry`).
- [x] **First-class OpenAI-compatible provider** — LM Studio config entry
  promoted to a documented, tested provider type (also covers vLLM,
  llama.cpp server, LiteLLM proxies).
- [x] **Speculative reflex** — `ReflexBrain` answers instantly while the
  deliberation path verifies in the background and interrupts with a
  correction only when it disagrees (`_process_reflex_outcome` hook).
- [~] **Context engineering pass** — semantic cache, token optimizer, and
  knowledge-graph subgraph summarizer exist
  (`src/viki/core/knowledge_graph.py:summarize_for_context`); a budgeted
  context assembler that ranks memory, world-model state, and skill schemas
  per request is still in design.
- [~] **Structured-output hardening** — `chat_structured` with parse-and-retry
  exists; grammar-constrained decoding for `VIKIResponse` (Ollama JSON-schema
  mode) is the next step.

**Memory (the moat — overinvest here)**
- [x] **Three-tier memory model** — episodic (conversations via
  `EpisodicMemory`/`NarrativeMemory`), semantic (lessons/facts via
  `WorkingMemory`/`HierarchicalMemory`), procedural (skills/playbooks via
  skill registry). Cross-tier promotion rules are the remaining work.
- [x] **Knowledge graph over lessons** — entity/relation extraction on save,
  graph traversal ("what does X depend on?"), path finding, and subgraph
  context assembly (`src/viki/core/knowledge_graph.py`). Fully integrated
  into `LearningModule.save_lesson` for automatic extraction.
- [~] **Memory dashboard** — basic browse and search in the web UI; pin,
  correct, and forget are the remaining features. *User-editable memory is a
  trust feature no hosted assistant offers.*
- [x] **Pluggable vector backend** — abstract `VectorBackend` interface with
  `NumpyMemoryBackend` and `SQLiteVssBackend` implementations; `build_vector_backend`
  factory with ordered preference list (`src/viki/core/vector_backend.py`).
  Qdrant/Chroma adapters are straightforward additions via the interface.
- [~] **Dream consolidation v2** — `DreamModule` runs at idle and
  consolidates narrative episodes; semantic fact summarization is the next
  stage.
- [x] **Contradiction detection** — heuristic + optional LLM-based detection
  when new lessons conflict with existing ones (`src/viki/core/contradiction.py`).
  Integrated into `LearningModule.save_lesson`; conflicts are logged and
  surfaced.

**Trust & safety**
- [~] **Consistent action previews** — `_should_checkpoint` + `/confirm`
  exist in CLI; extend to dashboard and bridges; show diffs for file writes
  and exact command lines for shell.
- [x] **Skill sandboxing** — subprocess jail (CPU/time/filesystem scope) for
  `shell` and `python_interpreter` (`src/viki/skills/sandbox.py`). Integrated
  into `ShellSkill.execute` with fallback to direct subprocess.
- [x] **Secrets redaction everywhere** — `secrets_redact` reused on all logs,
  telemetry, and lesson storage paths via `security_guard.py`.

### Wave 2 — Autonomy & self-improvement (the differentiators)

**Self-training loop (close it fully)**
- [~] **Forge auto-evaluation gate** — `ModelABTest` and
  `IntelligenceScorecard` exist; the automated A/B-and-promote pipeline
  after `viki-forge` bakes a candidate is the remaining work.
  *This makes self-improvement safe and measurable — the whole thesis rests
  on this loop being closed.*
- [x] **Preference capture in the loop** — every `/confirm`-`/reject`,
  regeneration, and correction becomes a DPO pair automatically via
  `PreferenceForge` (`src/viki/core/preference_forge.py`).
- [~] **Curriculum builder** — `KnowledgeGapDetector` findings exist and
  feed `ingest_web_topics` watchlists; the automated pipeline gap →
  research → lesson → weights is partially wired.
- [~] **Skill synthesis with tests** — dynamic-skill creator exists
  (`src/viki/skills/creation/forge.py`); test generation and sandbox
  verification before registration is the next step.
- [~] **Nightly self-eval** — eval harness exists and scorecard persists
  trends; scheduled CI runs and regression-triggered missions are the
  remaining work.

**Autonomy**
- [~] **Missions v2** — `MissionControl` persists missions with status and
  progress events on the event bus; a dashboard board for queued/active/done
  missions with pause/cancel/inspect is the remaining work.
- [~] **Watchers** — `autonomous_monitor`/`WatchdogModule` infrastructure
  exists; user-defined triggers (file/folder changes, calendar proximity,
  inbox arrival, RSS/webhooks) each firing a budgeted mission is the next
  step. *This is the "works while you sleep" feature.*
- [x] **Task scheduler** — cron-like recurring missions with interval, cron
  expression, and one-shot support; per-task token/time budgets and hard kill
  switch (`src/viki/core/task_scheduler.py`). Wired into `MissionControl`.
- [x] **Proactive suggestions with a politeness budget** — VIKI may surface
  at most N proactive items per day, learned from acceptance rate; overlay
  badge delivery (`src/viki/core/proactive_suggestions.py`).
- [~] **Swarm contracts** — `SwarmOrchestrator` exists with basic typed task
  decomposition and sub-agent delegation; per-agent budgets and merge/review
  steps are the remaining work before scaling to parallel sub-agents for
  research and repo-wide edits.

**Computer-native mastery**
- [~] **Workspace world-model v2** — `WorldModel` + `SemanticFS` exist with
  project landmarks and safety zones; the live map and ambient context
  resolution ("my thesis" → path) for every skill is the remaining work.
- [~] **Screen understanding loop** — vision skill + `computer_use_grounding`
  + perceive-act-verify loop exist with the overlay skill drawing click
  targets; a global abort hotkey is the next step.
- [~] **Repo-native engineering mode** — `code_search` (persistent index),
  `git_context`, LSP bridge, `plan_edit_skill`, and `worktree_runner` all
  exist; integration into a coherent "work on this repo" mode with
  test-gated commits is ongoing.
- [~] **Cross-app automation macros** — window management, clipboard, and
  shell skills exist for recording flows; generalization into parameterized
  skills with sandbox verification is the next step — *learn-by-demonstration,
  which hosted agents structurally cannot do.*

### Wave 3 — Ecosystem & reach

**Extensibility**
- [x] **Entry-point plugin system** — third-party skills via Python entry
  points (`viki.skills` group in `pyproject.toml`) with safety-tier vetting
  at load (`SkillRegistry.discover_entry_point_skills`).
- [x] **MCP both ways** — MCP client exists (`mcp_client.py`); MCP *server*
  mode added so other agents/IDEs can call VIKI's skills and query its memory
  (`src/viki/integrations/mcp_server.py`, `viki-mcp` entry point).
- [ ] **Skill/playbook registry** — a curated, signed index for community
  skills and playbook packs; `viki install <skill>` with hash pinning.
- [~] **Persona packs** — the personas directory and forge pipeline exist;
  packaging as shareable, diffable profiles (engineer, researcher, writer)
  that bundle playbooks, watchers, and routing preferences is the next
  step.

**Interfaces**
- [~] **Dashboard v2** — streaming chat, memory browser, and scorecard
  trends exist in the aiohttp dashboard (`dashboard.py` + `dashboard.html`);
  mission board, router telemetry charts, and PWA manifest are the remaining
  work.
- [~] **Voice loop polish** — `audio_gateway`/`VoiceModule` exists with VAD
  and TTS (behind `[ml]`); wake word, push-to-talk, and barge-in via the
  interrupt signal are the next steps.
- [~] **Messaging bridges** — `MessagingNexus` supports Telegram, Discord,
  Slack, and WhatsApp with endpoint-guard auth (`central_nexus.py`);
  production hardening is ongoing. Your VIKI answers you anywhere, but runs
  at home.
- [~] **Remote pairing mode** — tenant machinery exists (`tenant_ops.py`)
  as the seed; an end-to-end-encrypted tunnel to your own instance (no relay
  storage) is the remaining work.

**Multi-node (stretch)**
- [~] **Federation between owned devices** — desktop (big model) + laptop
  (reflex only) sharing one memory via CRDT sync; tenant machinery
  (`tenant_ops.py`) exists as the seed.
- [ ] **Heterogeneous inference pool** — route heavy deliberation to the
  desktop GPU from any device on the LAN.

---

## What we deliberately will NOT build

Scope discipline is a feature. VIKI does not compete on:

- **Training foundation models** — we fine-tune and route; we don't pretrain.
- **Being a hosted multi-tenant SaaS** — single-owner sovereignty is the
  product. (Remote pairing ≠ hosting.)
- **A model marketplace** — Ollama/HF already exist; we integrate.
- **Beating frontier models on open-domain benchmarks** — we beat them on
  *the owner's* benchmark: their tasks, their context, their machine.

---

## Metrics backbone (how every wave is judged)

1. **Nightly scorecard** (Phase E) — reflex latency, deliberation first-token,
   task-suite pass rate, memory precision/recall probes, regression alarms.
2. **A/B against frontier baseline** — a monthly harness run of the owner's
   task suite against a hosted frontier model (where network policy allows);
   the gap over time *is* the product's report card.
3. **Autonomy ledger** — missions completed, watcher firings that produced
   accepted work, forge promotions; visible on the dashboard.
4. **Trust ledger** — confirmations requested vs. actions taken, sandbox
   violations caught, secrets redacted; safety is measured, not asserted.

---

*Maintainers: keep this honest — delete items that ship, prune ideas that
stop making sense, and never let the thesis table drift from what the
scorecard actually shows.*
