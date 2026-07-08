# VIKI Roadmap

Status of the production-quality restructuring and the improvement work that
remains. Dates use the restructure branch (`restructure/phase-1`, PR #20) as
the baseline. Update this file as items land.

---

## Done (restructure, July 2026)

For detail see PR #20 and `CHANGELOG.md`.

- **Packaging** — `viki` console entry point, optional `[ml]` extra
  (torch/transformers stack), committed `uv.lock`, single pytest config.
- **Content extraction** — 545 vendored playbooks moved out of the package to
  `playbooks/` (wheel: 0.6 MB); sovereign skill library ships as package data
  (fixes the silent no-load bug at runtime).
- **Import canonicalization** — everything imports as `viki.*`; the dual
  import identity (`core.x` vs `viki.core.x`) and its `sys.path` hack are gone.
- **Orchestrator split** — `VIKIController` reduced from 2,335 to ~1,090 lines
  via five thematic mixins (config / evolution / skills / telemetry / lifecycle).
- **Tests** — organized into `tests/unit/` and `tests/integration/`; two
  never-collected test files revived (suite: 372 → 375).
- **CI** — whole-repo ruff + format gates, advisory mypy, coverage, package
  build check, `labs/security-lab` workflow.

---

## Remaining phases (engineering)

### Phase A — Merge and stabilize
- [ ] Manual smoke of the interactive CLI (`viki --low-resource`) and the
  dashboard (`viki --dashboard`) on top of PR #20 — full startup (Ollama,
  background loops) is not exercised by the test suite.
- [ ] Merge PR #20; watch the first CI runs on `main` across the 3.10–3.12 matrix
  (the suite has so far been verified on Windows/3.11 plus a torch-free venv).

### Phase B — Type safety ratchet
- [ ] Run mypy locally (`pip install -e ".[dev]"` now includes it) and burn
  down errors module by module, starting with `viki.core.schema`,
  `viki.config`, and the new mixin modules.
- [ ] Give the controller mixins a typed protocol (a `ControllerProto` with the
  shared attributes) so `self.settings`, `self.skill_registry`, etc. type-check.
- [ ] Flip the CI mypy job from advisory (`continue-on-error`) to blocking.

### Phase C — Finish the de-godification
The mixin split made `orchestrator.py` navigable; the deeper refactor is to
turn mixins into collaborating objects:
- [ ] `__init__` is still ~320 lines of subsystem wiring — move construction
  into the existing DI container and collapse the **two** DI mechanisms
  (`viki.service_registry` and the container built in `cli.py`) into one.
- [ ] Extract `_process_request_impl` (~400 lines) into the request-pipeline
  stage model that `viki.core.request_pipeline` already defines.
- [ ] Decide the fate of the half-built clean-architecture layer:
  `domain/` + `application/` + `infrastructure/` hold ~20 files;
  `sqlalchemy_learning_repository` cannot even import (SQLAlchemy is not a
  dependency). Either commit to the layering or fold it into `core/` and
  delete the dead repository.

### Phase D — Scripts to first-class tools
- [ ] Promote the maintenance scripts people actually run into console
  entry points: `viki-forge` (build_viki_model), `viki-eval` (evals/run_all),
  `viki-ingest` (ingest_web_topics, seed_knowledge).
- [ ] Fold the one-off `scripts/verify_*.py` scenario checks into
  `tests/integration/` (marked `slow`/`manual`) or delete the ones the suite
  already covers.
- [ ] Give `scripts/evals/` a package `__init__` or move it under
  `src/viki/eval/` so its `sys.path` insertion can go away too.

### Phase E — Quality gates ratchet
- [ ] Raise the coverage floor from 20% stepwise (25 → 35 → 50) as tests grow;
  fail on *decrease* rather than a fixed floor if churn makes that noisy.
- [ ] Add `pip-audit` (or Dependabot/Renovate) for dependency vulnerabilities.
- [ ] Add a Docker build job to CI (the image is currently only built by hand);
  publish a slim (no-`[ml]`) image variant alongside the full one.
- [ ] Nightly scheduled CI run of the eval harness (`scripts/evals/run_all.py`)
  against a pinned local model, publishing the scorecard as an artifact.

### Phase F — Release engineering
- [ ] Version from git tags (`setuptools-scm`) instead of hand-edited
  `pyproject.toml`; keep `CHANGELOG.md` per release.
- [ ] Publish wheels to PyPI from `release.yml` on tag (build + `twine check`
  already run in CI).
- [ ] Decide whether `labs/` stays in-repo (path-filtered CI, as now) or moves
  to separate repositories; they are self-contained by policy already.

---

## Future features (product)

Grounded in subsystems that already exist in the codebase; roughly ordered by
value-to-effort.

### Model & inference
- **Streaming responses in CLI and dashboard** — the cortex already has a
  streaming path (`test_streaming_cortex`); surface token streaming end to end.
- **Smarter model routing** — extend `ModelRouter`/`CognitiveRouter` to route
  by task class *and* live latency/cost telemetry (data already collected in
  `get_router_telemetry`), with automatic failover tiers (local → LM Studio →
  cloud API).
- **First-class LM Studio / OpenAI-compatible provider profile** — the
  `lmstudio` provider entry in `config/models.yaml` should become a documented,
  tested provider type.

### Memory & knowledge
- **Pluggable vector backend** — `HierarchicalMemory` + `vector_memory` are
  SQLite-bound; add an interface with optional Qdrant/Chroma backends for
  large libraries while keeping SQLite the zero-config default.
- **Memory inspection UI** — expose recall, lesson reinforcement, and
  forget/pin operations in the dashboard (the `memory` skill already has the
  primitives).
- **Scheduled knowledge refresh** — periodic `ingest_web_topics` runs against
  a watchlist, gated by the existing air-gap setting.

### Skills & extensibility
- **Entry-point plugin system** — third-party skills discovered via Python
  entry points (`viki.skills`), replacing directory-scan `discover_skills`;
  keeps the safety-tier vetting hooks.
- **MCP maturation** — MCP client exists (`viki.integrations.mcp_client`);
  add server-side MCP so other agents can drive VIKI's skills, plus a curated
  `mcp_servers.yaml` gallery.
- **Skill sandboxing** — run `python_interpreter`/`shell` skill executions in
  a subprocess jail (resource + filesystem limits) rather than in-process;
  the security lab's sandbox work is a good donor.

### Autonomy & self-improvement
- **Forge evaluation loop** — after `build_viki_model.py` bakes a candidate,
  automatically run the eval harness against the previous default and only
  promote on a scorecard win (pieces exist: `IntelligenceScorecard`,
  `ModelABTest`, `--set-default`).
- **Mission Control UX** — missions persist (`mission_control.py`) but are
  opaque; add dashboard views for queued/active missions with pause/cancel.
- **Swarm hardening** — `SwarmOrchestrator`/`LocalAgentPool` are wired but
  thin; define task decomposition contracts and per-agent budgets before
  scaling out.

### Interfaces
- **Dashboard v2** — session usage and health endpoints exist; add streaming
  chat, memory browser, mission board, and router telemetry charts.
- **Voice loop polish** — `audio_gateway` (VAD/whisper) exists behind the
  `[ml]` extra; document and test push-to-talk and wake-word flows.
- **Messaging bridges** — `MessagingNexus` supports request processing;
  finish at least one production bridge (Discord or Telegram) with the
  endpoint guard enforcing auth.

### Trust & safety
- **Permission prompt UX** — `_should_checkpoint` + `/confirm`/`/reject`
  tokens exist; make destructive-action previews (diffs, commands) consistent
  across CLI, dashboard, and bridges.
- **Local telemetry dashboard** — everything in `TelemetryStore` stays local;
  add a redaction pass (reuse the security lab's `secrets_redact`) before any
  log export.

---

*Maintainers: keep this list honest — delete items that ship, and prune ideas
that stop making sense rather than letting them rot.*
