# Running VIKI in Docker

Documentation index: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md).

This guide covers running the VIKI API in Docker and using Docker from the agent (e.g. listing containers, running images).

## Prerequisites

- Docker (and Docker Compose if you use `docker compose up`)
- Ollama running on the host (or in another container)
- A `.env` file with at least `VIKI_API_KEY` set (copy from `.env.example`)

## Using Docker from the agent

## Using Docker from the agent

VIKI can run Docker commands (e.g. `docker ps`, `docker run`) via the **shell skill**. Ask VIKI to run a command; she will use the shell skill and may ask for confirmation for higher-risk commands.

- **VIKI on the host**: If Docker CLI is installed and the daemon is reachable, you can say e.g. “run docker ps” or “list Docker containers” and VIKI will run the appropriate command.
- **VIKI in Docker**: To let the agent control Docker on the host from inside the container:
  1. Mount the Docker socket: `-v /var/run/docker.sock:/var/run/docker.sock`
  2. Install the Docker CLI in the image (extend the Dockerfile with a step that installs the `docker` CLI for your platform), or use an image that already includes it.

Then the agent can run `docker ps`, `docker images`, `docker run ...`, etc. through the shell skill (with confirmation when the command is classified as destructive).

| Variable | Description |
|----------|-------------|
| `VIKI_API_KEY` | Required for messaging gateway authentication. |
| `VIKI_DATA_DIR` | Persistence directory (default `./data`). In Docker use `/app/data` and mount a volume. |
| `VIKI_WORKSPACE_DIR` | Workspace for agent files (default `./workspace`). In Docker use `/app/workspace` and mount a volume. |
| `OLLAMA_HOST` | Ollama API URL. Set to `http://host.docker.internal:11434` when VIKI runs in Docker and Ollama is on the host (Windows/Mac). |

See `.env.example` for more options.

---

*Runbook version: aligned with VIKI v8.2.0 (Sovereign). Update this file when default ports, flags, or critical architecture patterns change.*
