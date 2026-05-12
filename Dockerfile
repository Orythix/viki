# VIKI CLI — run the sovereign agent engine in Docker
# Note: Interactive TTY is recommended for CLI usage.

FROM python:3.11-slim

WORKDIR /app

# Copy project and install dependencies
COPY pyproject.toml ./
COPY viki/ ./viki/
RUN pip install --no-cache-dir -e .

# Create data and workspace dirs (volumes will override at runtime)
RUN mkdir -p /app/data /app/workspace

# Default: run the VIKI CLI.
CMD ["viki"]
