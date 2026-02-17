# Running VIKI in Docker

This guide covers running the VIKI API in Docker and using Docker from the agent (e.g. listing containers, running images).

## Prerequisites

- Docker (and Docker Compose if you use `docker compose up`)
- Ollama running on the host (or in another container)
- A `.env` file with at least `VIKI_API_KEY` set (copy from `.env.example`)

## Build and run the API

From the repo root:

```bash
docker compose up --build
```

The API will be available at `http://localhost:5000`. The compose file:

- Sets `FLASK_HOST=0.0.0.0` so the server accepts connections from outside the container
- Mounts `./data` and `./workspace` so state and files persist
- Sets `OLLAMA_HOST=http://host.docker.internal:11434` so the container can reach Ollama on the host (Windows/Mac)

### Run without Compose

```bash
docker build -t viki-api .
docker run --rm -p 5000:5000 \
  -e FLASK_HOST=0.0.0.0 \
  -e VIKI_API_KEY=your-key \
  -e VIKI_DATA_DIR=/app/data \
  -e VIKI_WORKSPACE_DIR=/app/workspace \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/workspace:/app/workspace" \
  viki-api
```

### Ollama connectivity

- **Windows / Mac**: `OLLAMA_HOST=http://host.docker.internal:11434` lets the container reach Ollama on the host. Use this in `docker run` or in `docker-compose.yml` (already set).
- **Linux**: Either run the container with `network_mode: host` so it shares the host network (then `localhost:11434` works), or set `OLLAMA_HOST` to your host’s IP (e.g. `http://172.17.0.1:11434`). You can also run Ollama in another container on the same Docker network and set `OLLAMA_HOST=http://ollama:11434`.

## UI

Run the React UI on the host so it can talk to the API:

```bash
cd ui
npm run dev
```

In `ui/.env` set:

- `VITE_VIKI_API_BASE=http://localhost:5000/api`
- `VITE_VIKI_API_KEY` to the same value as `VIKI_API_KEY`

Then open `http://localhost:5173`.

## Using Docker from the agent

VIKI can run Docker commands (e.g. `docker ps`, `docker run`) via the **shell skill**. Ask VIKI to run a command; she will use the shell skill and may ask for confirmation for higher-risk commands.

- **VIKI on the host**: If Docker CLI is installed and the daemon is reachable, you can say e.g. “run docker ps” or “list Docker containers” and VIKI will run the appropriate command.
- **VIKI in Docker**: To let the agent control Docker on the host from inside the container:
  1. Mount the Docker socket: `-v /var/run/docker.sock:/var/run/docker.sock`
  2. Install the Docker CLI in the image (extend the Dockerfile with a step that installs the `docker` CLI for your platform), or use an image that already includes it.

Then the agent can run `docker ps`, `docker images`, `docker run ...`, etc. through the shell skill (with confirmation when the command is classified as destructive).

## Environment variables

| Variable | Description |
|----------|-------------|
| `FLASK_HOST` | Bind address. Use `0.0.0.0` in Docker so the API is reachable (compose sets this). |
| `VIKI_API_KEY` | Required for API authentication. |
| `VIKI_DATA_DIR` | Persistence directory (default `./data`). In Docker use `/app/data` and mount a volume. |
| `VIKI_WORKSPACE_DIR` | Workspace for agent files (default `./workspace`). In Docker use `/app/workspace` and mount a volume. |
| `OLLAMA_HOST` | Ollama API URL. Set to `http://host.docker.internal:11434` when VIKI runs in Docker and Ollama is on the host (Windows/Mac). |

See `.env.example` for more options.
