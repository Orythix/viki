# Documentation index

Central map of **first-party** docs in this monorepo (engineering playbooks under `viki/skills/playbooks/` are listed in that folder’s README).

## Core VIKI

| Document | Description |
|----------|-------------|
| [README.md](../README.md) | Product overview, quick start, Neural Forge bake (`viki-neural-forge` default Ollama tag), architecture summary |
| [SETUP.md](../SETUP.md) | Install, env, first run |
| [VIKI_RUNBOOK.md](../VIKI_RUNBOOK.md) | Operations, troubleshooting, RAG eval, boot evolution |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | System design, data flow, frontier wiring |
| [DOCKER.md](../DOCKER.md) | Container run |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](../CHANGELOG.md) | Version history |
| [REPOSITORY_VISIBILITY_AND_BRANCHES.md](REPOSITORY_VISIBILITY_AND_BRANCHES.md) | Public vs private repos; why “secret” branches on a public remote are not secret |
| [README_VIKI_PUBLIC.md](README_VIKI_PUBLIC.md) | Root README for **VIKI-public** mirrors (`readme_override` in export manifest) |
| [SECURITY.md](../SECURITY.md) | Security policy |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Community standards |
| [viki/SECURITY_SETUP.md](../viki/SECURITY_SETUP.md) | API keys, UI auth, capabilities |
| [viki/ARCHITECTURE_REFACTOR.md](../viki/ARCHITECTURE_REFACTOR.md) | Controller / pipeline refactor notes |

## UI

| Document | Description |
|----------|-------------|
| [ui/.env.example](../ui/.env.example) | Vite env template (`VITE_VIKI_API_KEY`, …) |

## Security lab (standalone)

| Document | Description |
|----------|-------------|
| [security-lab/README.md](../security-lab/README.md) | Lab overview |
| [security-lab/docs/DEPLOYMENT.md](../security-lab/docs/DEPLOYMENT.md) | Docker / local run |
| [security-lab/docs/API.md](../security-lab/docs/API.md) | REST API |
| [security-lab/docs/THREAT_MODEL.md](../security-lab/docs/THREAT_MODEL.md) | Threat model |
| [security-lab/docs/SECURITY_CHECKLIST.md](../security-lab/docs/SECURITY_CHECKLIST.md) | Pre-flight checklist |
| [security-lab/docs/EXAMPLE_ATTACKS_AND_DEFENSES.md](../security-lab/docs/EXAMPLE_ATTACKS_AND_DEFENSES.md) | Educational scenarios |

## QA automation (learning track)

| Document | Description |
|----------|-------------|
| [qa-automation/README.md](../qa-automation/README.md) | Multi-stack test tracks |
| [qa-automation/docs/SYLLABUS.md](../qa-automation/docs/SYLLABUS.md) | Curriculum |
| [qa-automation/docs/STACK_INDEX.md](../qa-automation/docs/STACK_INDEX.md) | Tool → path map |

## Evaluation

| Document | Description |
|----------|-------------|
| [viki/eval/README.md](../viki/eval/README.md) | RAG gold format, metrics, `run_rag_eval.py` |

## Engineering playbooks

See [viki/skills/playbooks/README.md](../viki/skills/playbooks/README.md) (upstream import + in-house waves + `megatron_lm/`).
