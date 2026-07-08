# VIKI Roadmap

The plan to make VIKI the most capable *personal* AI system available — and
the argument for why a local-first system can win against hosted assistants.

Baseline: the production-quality restructure (PR #20, merged July 2026).
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
- **Content extraction** — 545 playbooks moved to `playbooks/` (wheel:
  0.6 MB); sovereign skill library ships as package data (fixed a silent
  no-load bug).
- **Import canonicalization** — single `viki.*` namespace; dual-identity
  `sys.path` hack removed.
- **Orchestrator split** — `VIKIController` 2,335 → ~1,090 lines via five
  thematic mixins.
- **Tests** — `tests/unit/` + `tests/integration/`; two never-collected test
  files revived (372 → 375 tests).
- **CI** — whole-repo ruff + format gates, advisory mypy, coverage, build
  check, security-lab workflow.

---

## Remaining engineering phases

These make the codebase trustworthy enough to build the feature waves on.
Order matters: don't stack features on unstable ground.

### Phase A — Stabilize the restructure
- [ ] Manual smoke of interactive CLI (`viki --low-resource`) and dashboard
  (`viki --dashboard`) — full startup isn't covered by the suite.
- [ ] Watch first CI runs on the 3.10–3.12 matrix (verified so far on
  Windows/3.11 + a torch-free venv).

### Phase B — Type-safety ratchet
- [ ] Burn down mypy module-by-module: `viki.core.schema`, `viki.config`,
  the new mixins, then outward.
- [ ] Typed `ControllerProto` protocol for mixin `self` attributes.
- [ ] Flip CI mypy from advisory to blocking.

### Phase C — Finish the de-godification
- [ ] Collapse the two DI mechanisms (`service_registry` + the `cli.py`
  container) into one; move `__init__`'s ~320 lines of wiring into it.
- [ ] Extract `_process_request_impl` (~400 lines) into the
  `request_pipeline` stage model that already exists.
- [ ] Resolve the half-built clean-architecture layer: commit or fold into
  `core/`; delete `sqlalchemy_learning_repository` (cannot import — no
  SQLAlchemy dependency).

### Phase D — Scripts to first-class tools
- [ ] Console entry points: `viki-forge`, `viki-eval`, `viki-ingest`.
- [ ] Fold `scripts/verify_*.py` into `tests/integration/` (marked
  `slow`/`manual`) or delete duplicates.
- [ ] Move `scripts/evals/` under `src/viki/eval/` so its path insertion dies.

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
- [ ] **End-to-end token streaming** in CLI and dashboard (the cortex
  streaming path exists; surface it everywhere). First-token latency is the
  single most felt quality metric.
- [ ] **Telemetry-driven model routing** — route by task class *and* live
  latency/cost/success stats (`get_router_telemetry` already collects them),
  with automatic failover tiers: local Ollama → LM Studio → cloud API.
- [ ] **First-class OpenAI-compatible provider** — promote the `lmstudio`
  config entry to a documented, tested provider type (also covers vLLM,
  llama.cpp server, LiteLLM proxies).
- [ ] **Speculative reflex** — let `ReflexBrain` answer instantly while the
  deliberation path verifies in the background and interrupts with a
  correction only when it disagrees (`_process_reflex_outcome` is the hook).
- [ ] **Context engineering pass** — a budgeted context assembler that ranks
  memory, world-model state, and skill schemas per request instead of
  concatenating; measure tokens-per-request before/after.
- [ ] **Structured-output hardening** — grammar-constrained decoding for
  `VIKIResponse` where the backend supports it (Ollama JSON-schema mode)
  instead of parse-and-retry.

**Memory (the moat — overinvest here)**
- [ ] **Three-tier memory model** made explicit: episodic (conversations),
  semantic (lessons/facts), procedural (skills/playbooks) — with promotion
  rules between tiers. `HierarchicalMemory`, `LearningModule`, and the skill
  registry are the tiers; the promotion machinery is the new work.
- [ ] **Knowledge graph over lessons** — entity/relation extraction on save
  so recall can traverse ("what does my boss's project depend on?"), building
  on the `get_related_concepts` graph stub.
- [ ] **Memory dashboard** — browse, search, pin, correct, and forget
  memories from the web UI. *User-editable memory is a trust feature no
  hosted assistant offers.*
- [ ] **Pluggable vector backend** — interface with SQLite default and
  optional Qdrant/Chroma for 100k+ lesson libraries.
- [ ] **Dream consolidation v2** — `DreamModule` runs at idle: deduplicate
  lessons, resolve contradictions (keep provenance), summarize episodes into
  semantic facts, decay stale confidence.
- [ ] **Contradiction detection** — when a new lesson conflicts with an old
  one, surface it and ask (or use recency + source trust), rather than
  storing both.

**Trust & safety**
- [ ] **Consistent action previews** — `_should_checkpoint` + `/confirm`
  everywhere: CLI, dashboard, bridges; show diffs for file writes and exact
  command lines for shell.
- [ ] **Skill sandboxing** — subprocess jail (CPU/mem/time/filesystem scope)
  for `python_interpreter` and `shell`; the security lab's sandbox is the
  donor.
- [ ] **Secrets redaction everywhere** — reuse `secrets_redact` on all logs,
  telemetry, and lesson storage paths.

### Wave 2 — Autonomy & self-improvement (the differentiators)

**Self-training loop (close it fully)**
- [ ] **Forge auto-evaluation gate** — after `viki-forge` bakes a candidate,
  automatically A/B it against the incumbent with the eval harness
  (`ModelABTest`, `IntelligenceScorecard`) and promote only on a win.
  *This makes self-improvement safe and measurable — the whole thesis rests
  on this loop being closed.*
- [ ] **Preference capture in the loop** — every `/confirm`-`/reject`,
  regeneration, and correction becomes a DPO pair automatically
  (`preference_forge` exists; wire the capture points).
- [ ] **Curriculum builder** — `KnowledgeGapDetector` findings feed
  `ingest_web_topics` watchlists feed forge datasets: gap → research →
  lesson → weights, without human dispatch.
- [ ] **Skill synthesis with tests** — when the dynamic-skill creator writes
  a new skill, it must also generate a pytest file and pass it in the sandbox
  before registration (`skills/dynamic` + `TestHealerPipeline`).
- [ ] **Nightly self-eval** — scheduled scorecard run; regression on any
  north-star metric opens a mission to investigate.

**Autonomy**
- [ ] **Missions v2** — dashboard board for queued/active/done missions with
  pause/cancel/inspect (`MissionControl` persists them already); missions
  emit progress events on the existing event bus.
- [ ] **Watchers** — user-defined triggers: file/folder changes
  (`autonomous_monitor`), calendar proximity, inbox arrival, RSS/webhooks →
  each fires a mission with a budget. *This is the "works while you sleep"
  feature.*
- [ ] **Task scheduler** — cron-like recurring missions (daily digest, weekly
  repo triage, backup verification) with per-mission token/time budgets and
  a hard kill switch.
- [ ] **Proactive suggestions with a politeness budget** — VIKI may surface
  at most N proactive items per day, learned from acceptance rate; never
  interrupts flow (overlay badge, not modal).
- [ ] **Swarm contracts** — before scaling `SwarmOrchestrator`: typed task
  decomposition contracts, per-agent budgets, and merge/review steps; then
  parallel sub-agents for research and repo-wide edits.

**Computer-native mastery**
- [ ] **Workspace world-model v2** — `WorldModel` + `SemanticFS` maintain a
  live map of projects, landmark files, and safety zones; every skill gets
  this as ambient context ("my thesis" resolves to a path).
- [ ] **Screen understanding loop** — vision skill + `computer_use_grounding`
  into a perceive-act-verify loop with the overlay skill drawing what it's
  about to click, and a global abort hotkey.
- [ ] **Repo-native engineering mode** — combine `code_search` (persistent
  index), `git_context`, LSP bridge, `plan_edit_skill`, and worktree runner
  into a coherent "work on this repo" mode with test-gated commits.
- [ ] **Cross-app automation macros** — record a demonstrated flow (window
  manager + clipboard + shell events), generalize it into a parameterized
  skill, verify in sandbox — *learn-by-demonstration, which hosted agents
  structurally cannot do.*

### Wave 3 — Ecosystem & reach

**Extensibility**
- [ ] **Entry-point plugin system** — third-party skills via Python entry
  points (`viki.skills`) with safety-tier vetting at load; deprecate
  directory-scan discovery.
- [ ] **MCP both ways** — client exists; add MCP *server* mode so other
  agents/IDEs can call VIKI's skills and query its memory (with endpoint
  guard auth). VIKI becomes infrastructure, not just an app.
- [ ] **Skill/playbook registry** — a curated, signed index for community
  skills and playbook packs; `viki install <skill>` with hash pinning.
- [ ] **Persona packs** — the personas dir + forge pipeline packaged as
  shareable, diffable profiles (engineer, researcher, writer) that bundle
  playbooks, watchers, and routing preferences.

**Interfaces**
- [ ] **Dashboard v2** — streaming chat, memory browser, mission board,
  router telemetry charts, scorecard trends; PWA manifest so it installs on
  a phone against the home server.
- [ ] **Voice loop polish** — wake word + push-to-talk over `audio_gateway`
  (VAD/whisper behind `[ml]`), with barge-in via the interrupt signal.
- [ ] **Messaging bridges** — finish one production bridge (Telegram or
  Discord) through `MessagingNexus` with endpoint-guard auth; your VIKI
  answers you anywhere, but runs at home.
- [ ] **Remote pairing mode** — end-to-end-encrypted tunnel to your own
  instance (no relay storage), so "hosted convenience" stops being a reason
  to give data away.

**Multi-node (stretch)**
- [ ] **Federation between owned devices** — desktop (big model) + laptop
  (reflex only) sharing one memory via CRDT sync; tenant machinery
  (`tenant_ops`) is the seed.
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
