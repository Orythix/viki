#!/bin/sh
# Entrypoint script for VIKI Docker container
# Copies host config YAML files to container config directory if mounted

set -e

# If host config is mounted at /host-config, copy YAML files to container config
if [ -d "/host-config" ]; then
    echo "Copying host config YAML files to container config..."
    cp /host-config/*.yaml /app/src/viki/config/ 2>/dev/null || true
    cp /host-config/*.yml /app/src/viki/config/ 2>/dev/null || true
    if [ ! -f "/app/src/viki/config/settings.yaml" ]; then
        echo "WARNING: /app/src/viki/config/settings.yaml not found after copy."
        echo "Config at /app/src/viki/config/ contains:"
        ls /app/src/viki/config/ 2>/dev/null || echo "  (empty)"
    else
        echo "Config copy verified: settings.yaml present."
    fi
fi

# Check if Ollama is reachable
OLLAMA_URL="${OLLAMA_HOST:-http://host.docker.internal:11434}"
echo "Checking Ollama connectivity at $OLLAMA_URL..."
if curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    echo "Ollama is reachable."
else
    echo "WARNING: Cannot reach Ollama at $OLLAMA_URL."
    echo "Ensure Ollama is running on the host with OLLAMA_HOST=0.0.0.0:11434"
fi

# Execute the main command
exec "$@"
