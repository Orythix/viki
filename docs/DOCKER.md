# Running VIKI in Docker

Documentation index: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md).

This guide covers running the VIKI CLI in Docker.

## Prerequisites

- Docker (and Docker Compose if you use `docker compose`)
- Ollama running on the host (or in another container)
- A `.env` file (copy from `.env.example`)

## Quick start

```powershell
# Build the image
docker compose build

# Interactive CLI session
docker compose run --rm -it viki

# One-shot command
docker compose run --rm viki "list files in current directory"
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `VIKI_DATA_DIR` | Persistence directory. In Docker use `/app/data` (mounted by default). |
| `VIKI_WORKSPACE_DIR` | Workspace for agent files (`/app/workspace`). |
| `VIKI_CONFIG_DIR` | Config directory (`/app/config`). |
| `OLLAMA_HOST` | Ollama API URL. Set to `http://host.docker.internal:11434` when VIKI runs in Docker and Ollama is on the host (Windows/Mac). |

## Volumes

The `docker-compose.yml` mounts these directories from the host:

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `./data` | `/app/data` | SQLite databases, lessons, training data |
| `./workspace` | `/app/workspace` | Agent workspace files |
| `./logs` | `/app/logs` | Telemetry and log output |
| `./config` | `/app/config` | Settings, models, personas, soul |

## Running on low-end PCs

The Docker image is the same codebase. For low-RAM environments:

1. Use a small Ollama model (`phi3:mini` is ~2.2 GB).
2. Set `VIKI_LOW_RESOURCE=1` in `.env` or the `environment` section of `docker-compose.yml`.
3. The image already includes optimized defaults (see `config/settings.yaml`).

## Using Docker from the agent

VIKI can run Docker commands (e.g. `docker ps`, `docker run`) via the **shell skill**. To let the agent control Docker on the host from inside the container:

1. Mount the Docker socket: `-v /var/run/docker.sock:/var/run/docker.sock`
2. Install the Docker CLI in the image (extend the Dockerfile).

Then the agent can run `docker ps`, `docker images`, `docker run ...`, etc. through the shell skill (with confirmation when the command is classified as destructive).

---

*Runbook version: aligned with VIKI v8.2.0 (Sovereign). Update this file when default ports, flags, or critical architecture patterns change.*
