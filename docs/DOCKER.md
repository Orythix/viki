# Running VIKI in Docker

Documentation index: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md).

This guide covers running the VIKI CLI in Docker with LM Studio on the host.

## Prerequisites

- Docker (and Docker Compose if you use `docker compose`)
- LM Studio installed with a model loaded (default: `google/gemma-4-e4b`)
- A `.env` file (copy from `.env.example`)

## Step 1: Ensure LM Studio is running

LM Studio must have the local server enabled on port 1234:

1. Open LM Studio
2. Go to **Developer** tab
3. Load a model (e.g. `google/gemma-4-e4b`)
4. Start the server on `http://127.0.0.1:1234`

## Step 2: Copy config files (one-time)

The entrypoint script copies config from the host `./config/` directory into the container at startup. Make sure your config files are present:

```powershell
ls config/settings.yaml config/models.yaml
```

## Step 3: Build and run

```powershell
# Build the image
docker compose build

# Interactive CLI session
docker compose run --rm -it viki

# One-shot command
docker compose run --rm viki "list files in current directory"
```

## Environment variables

The `docker-compose.yml` sets these:

| Variable | Value | Description |
|----------|-------|-------------|
| `VIKI_DATA_DIR` | `/app/data` | Database and persistence directory |
| `VIKI_WORKSPACE_DIR` | `/app/workspace` | Agent workspace |
| `VIKI_CONFIG_DIR` | `/app/config` | Config directory |
| `VIKI_TRUST_WORKSPACE` | `true` | Auto-trust the workspace (skip prompt) |
| `VIKI_LOG_LEVEL` | `INFO` | Logging level |
| `LMSTUDIO_URL` | `http://host.docker.internal:1234/v1` | LM Studio endpoint from inside container |

## Volumes

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `./config` | `/host-config` (copied to `/app/src/viki/config/` at startup) | Settings, models, personas |
| `./data-docker` | `/app/data` | SQLite databases (separate from host data) |
| `./workspace` | `/app/workspace` | Agent workspace files |
| `./logs` | `/app/logs` | Telemetry and log output |

**Important:** The `./config` mount is read-only; files are copied at container startup. The host and container each have independent config directories to avoid SQLite locking issues.

## How networking works

The Docker container accesses the host LM Studio service via `host.docker.internal:1234`. This requires:

1. LM Studio running with the local server enabled
2. Docker Desktop with host networking support (Windows/Mac native)

## Running on low-end PCs

1. Use a small model in LM Studio (e.g. `google/gemma-4-e4b` at ~4B params).
2. The image includes optimized defaults (`VIKI_LOW_RESOURCE=1` can be set in `docker-compose.yml`).

## Using Docker from the agent

VIKI can run Docker commands (e.g. `docker ps`, `docker run`) via the **shell skill**. To let the agent control Docker on the host from inside the container:

1. Mount the Docker socket: `-v /var/run/docker.sock:/var/run/docker.sock`
2. Install the Docker CLI in the image (extend the Dockerfile).

Then the agent can run `docker ps`, `docker images`, `docker run ...`, etc. through the shell skill (with confirmation when the command is classified as destructive).

---

*Runbook version: aligned with VIKI v8.4.0 (The Code Eternal). Update this file when default ports, flags, or critical architecture patterns change.*
