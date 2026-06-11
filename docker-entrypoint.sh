#!/bin/sh
# Entrypoint script for VIKI Docker container
# Copies host config YAML files to container config directory if mounted

set -e

# If host config is mounted at /host-config, copy YAML files to container config
if [ -d "/host-config" ]; then
    echo "Copying host config YAML files to container config..."
    cp /host-config/*.yaml /app/src/viki/config/ 2>/dev/null || true
    cp /host-config/*.yml /app/src/viki/config/ 2>/dev/null || true
fi

# Execute the main command
exec "$@"