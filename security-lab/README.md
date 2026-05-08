# AI Security Learning Lab (local, defensive)

Educational **FastAPI + React + Docker** reference stack for **legal, local** AI security practice: prompt-injection heuristics, RBAC tools, audit logging, sandboxed vulnerable demo, and a minimal monitoring UI.

## Principles

- **Local-only** by default (`127.0.0.1` bindings).
- **No offensive tooling** — defensive heuristics, test harnesses, and intentionally weak **containerized** demos only.
- **Open source** oriented (Ollama, Flask demo, FastAPI, React).

## Layout

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI app, agent orchestration, audit store (SQLite or PostgreSQL) |
| `frontend/` | React dashboard (Vite) — monitoring, harnesses, adversarial analysis |
| `security/` | Injection detector, sanitizer, output filter, sandbox URL policy, adversarial report, RBAC policy JSON, test harness |
| `sandbox/` | Docker-only vulnerable demo (XSS) |
| `monitoring/` | Telemetry snapshots + alert derivation consumed by the API |
| `docker/` | Compose + Dockerfiles |
| `tests/` | `pytest` |
| `docs/` | Threat model, checklist, deployment, API, examples |

## Quick start

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

```bash
# Tests
cd security-lab && python -m pytest tests -q

# API (dev)
cd security-lab/backend
PYTHONPATH=.. uvicorn app.main:app --reload --port 8000

# UI (dev)
cd security-lab/frontend && npm install && npm run dev
```

## Documentation

- [Threat model](docs/THREAT_MODEL.md)
- [Security checklist](docs/SECURITY_CHECKLIST.md)
- [Deployment](docs/DEPLOYMENT.md)
- [API](docs/API.md)
- [Attacks & defenses (educational)](docs/EXAMPLE_ATTACKS_AND_DEFENSES.md)

## Relationship to VIKI

This folder is a **standalone** lab you can run beside the main VIKI project. It does not modify VIKI core code.

Optional: use the repo’s **[`qa-automation/`](../qa-automation/)** tracks to practice API and UI automation against this API (see `qa-automation/README.md`).
