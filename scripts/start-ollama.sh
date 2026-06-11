#!/usr/bin/env bash
# Starts Ollama for Docker access and launches VIKI.
# Sets OLLAMA_HOST=0.0.0.0:11434 (required for Docker container access),
# starts Ollama if not running, waits for it to be ready, then runs
# `docker compose run --rm -it viki`.

set -euo pipefail

OLLAMA_PORT=11434
OLLAMA_URL="http://127.0.0.1:$OLLAMA_PORT"

# Check if Ollama is already running
if curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    echo "Ollama is already running."
else
    echo "Starting Ollama on 0.0.0.0:$OLLAMA_PORT ..."
    export OLLAMA_HOST="0.0.0.0:$OLLAMA_PORT"
    export OLLAMA_CUDA="0"
    ollama serve &
    OLLAMA_PID=$!

    # Wait for Ollama to become ready
    MAX_WAIT=15
    WAITED=0
    while [ "$WAITED" -lt "$MAX_WAIT" ]; do
        sleep 1
        WAITED=$((WAITED + 1))
        if curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
            echo "Ollama is ready."
            break
        fi
        if [ "$WAITED" -eq "$MAX_WAIT" ]; then
            echo "ERROR: Ollama did not start within ${MAX_WAIT}s." >&2
            exit 1
        fi
    done
fi

# Navigate to project root and launch VIKI
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
exec docker compose run --rm -it viki
