---
name: frontier-agentic-workflow
description: Complete frontier agentic workflow instructions for MCTS reasoning, sub-agent swarms, Sentry bug healing, and SDLC engineering.
---

# 🛸 Frontier Agentic Workflow Skill

This skill defines the multi-step execution workflow for VIKI's frontier agentic operations.

## Workflow

### 1. Intent Triage & Test-Time Scaling
- **Reflex Route**: Sub-100ms short-circuit path for routine commands.
- **Linear ReAct**: Standard tool-use workflow (1-5 steps).
- **MCTS Tree Search**: Multi-branch evaluation with UCB1 selection for complex coding tasks.

### 2. Multi-Agent Swarm Delegation
- **Architect Sub-Agent**: Analyzes AST Knowledge Graph ([knowledge_graph.py](file:///d:/My%20Projects/VIKI/src/viki/core/knowledge_graph.py)) & generates specs.
- **Coder Sub-Agent**: Implements code diffs in Git worktrees ([worktree_runner.py](file:///d:/My%20Projects/VIKI/src/viki/core/worktree_runner.py)).
- **QA/Security Sub-Agent**: Runs SAST security scanning ([security_guard.py](file:///d:/My%20Projects/VIKI/src/viki/core/security_guard.py)) and automated pytest suites.

### 3. Production Incident Self-Healing
- Parse Sentry/Datadog stack traces in `AutonomousIncidentHealer` ([autonomous_incident_healer.py](file:///d:/My%20Projects/VIKI/src/viki/core/autonomous_incident_healer.py)).
- Reproduce bug in isolated worktree, write failing regression test, apply fix, and verify tests pass.

### 4. Full SDLC & Schema Generation
- Parse Jira user stories in `JiraSDLCWorkflowSkill` ([jira_sdlc_skill.py](file:///d:/My%20Projects/VIKI/src/viki/skills/builtins/jira_sdlc_skill.py)).
- Auto-generate OpenAPI 3.1 & gRPC proto schemas in `OpenAPISchemaSkill` ([openapi_schema_skill.py](file:///d:/My%20Projects/VIKI/src/viki/skills/builtins/openapi_schema_skill.py)).
