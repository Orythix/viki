---
name: mcts-swarm-engineering
description: Execute complex engineering workflows using Monte Carlo Tree Search (MCTS) reasoning and leader-worker sub-agent swarms.
---

# 🐝 MCTS Swarm Engineering Skill

This skill defines the multi-step workflow for executing high-agency coding and architectural tasks using MCTS tree search and specialized sub-agent swarms.

## Workflow

### 1. MCTS Branch Evaluation
- Evaluate candidate action branches using UCB1 selection:
  $$\text{UCB1} = \bar{X}_i + C \sqrt{\frac{\ln N}{n_i}}$$
- Score intermediate state nodes using `IntelligenceScorecard` heuristics.
- Automatically backtrack when an execution branch fails or generates errors.

### 2. Multi-Agent Swarm Topology
- **Architect Agent**: Scopes architectural specs, dependencies, and file relationships using AST Knowledge Graph ([knowledge_graph.py](file:///d:/My%20Projects/VIKI/src/viki/core/knowledge_graph.py)).
- **Coder Agent**: Implements modular code diffs in isolated scratchpads or Git worktrees ([worktree_runner.py](file:///d:/My%20Projects/VIKI/src/viki/core/worktree_runner.py)).
- **QA / Security Agent**: Runs security scanning ([security_guard.py](file:///d:/My%20Projects/VIKI/src/viki/core/security_guard.py)) and automated pytest verification.

### 3. Real-Time DAG Streaming
- Stream execution progress over `/api/v2/swarm/dag` endpoints to the Web Dashboard UI.
