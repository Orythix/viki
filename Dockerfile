# VIKI CLI — run the sovereign agent engine in Docker
# Note: Interactive TTY is recommended for CLI usage (docker run -it viki).

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Prevent pip from complaining about running as root outside a venv
ENV PIP_REQUIRE_VIRTUALENV=0

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Copy project files
COPY pyproject.toml ./
COPY src/       ./src/
COPY playbooks/ ./playbooks/
# Config goes where the code expects it: ../config/ relative to src/viki/
COPY config/  ./src/viki/config/

# Install dependencies and the package itself.
# The [ml] extra (torch/transformers) keeps forge/embedding features available;
# drop it for a much slimmer image if you only need the core agent.
RUN pip install --no-cache-dir -e ".[ml]" 2>&1 || pip install --no-cache-dir --break-system-packages -e ".[ml]"

# Copy scripts (useful for forge workflows)
COPY scripts/  ./scripts/

# Runtime directories (volumes override these at runtime)
RUN mkdir -p /app/data /app/workspace /app/logs

# Entrypoint to copy host config at runtime
ENTRYPOINT ["/docker-entrypoint.sh"]

# Default: run the VIKI CLI.
CMD ["viki"]
