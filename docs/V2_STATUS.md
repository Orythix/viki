# V2 Migration Status (July 2026 assessment)

This note records the current state of the `viki.v2` package relative to the
migration plan in `ARCHITECTURE_V2.md` (§23).

## Current state

- `src/viki/v2/` contains ~70 files / ~7,900 lines: agents, tools, providers,
  memory, and core (intent analysis, permission manager, execution engine).
- Integration with V1 happens through a single seam:
  `viki.v2.bridge.create_v2_bridge()`, registered as a V1 skill by
  `VIKIController._register_default_skills` and gated behind `VIKI_V2_MODE=1`.
- `viki.skills.public_safety` also imports V2 components directly
  (`nl_bridge`, `orchestrator`).
- V2 has its own unit tests under `tests/unit/v2/` (all passing).

## Issues found and fixed during the July 2026 audit

- `BaseTool` used `dataclasses.field()` outside a dataclass, so subclasses
  inherited `Field` objects instead of lists/dicts (fixed in `tools/base.py`).
- `ContextManager` called four `ProjectMemory` methods that do not exist
  (`get_project`, `get_decisions`, `add_decision`, `add_context`); it was
  dead-on-arrival code. Rewritten against the real async API.
- `SystemProvider` ABC was missing `get_network_info`, which every concrete
  provider implements and the network tool requires.
- `MCPToolWrapper` overrode writable base attributes with read-only
  properties; converted to plain instance attributes.

## Recommendation

Keep the bridge-based gradual migration; do not fork more V1/V2 parallel
implementations. Before expanding V2 usage:

1. Wire `ContextManager` into the agent loop or delete it — it is currently
   instantiated but never called.
2. Add an integration test that exercises `VIKI_V2_MODE=1` end-to-end through
   the bridge (current tests only cover V2 units in isolation).
3. Track remaining mypy debt in `v2/` (roughly 25 errors as of this audit).
