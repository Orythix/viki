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

# Check if LM Studio is reachable
LMSTUDIO_URL="${LMSTUDIO_HOST:-http://host.docker.internal:1234}"
echo "Checking LM Studio connectivity at $LMSTUDIO_URL..."
if curl -sf "$LMSTUDIO_URL/api/v1/models" > /dev/null 2>&1; then # Using a common API endpoint check for LLM services
    echo "LM Studio is reachable."
else
    echo "WARNING: Cannot reach LM Studio at $LMSTUDIO_URL."
    echo "Ensure LM Studio is running on the host and accessible via the configured environment variable (e.g., LMSTUDIO_HOST)."
fi

# Execute the main command
exec "$@"
