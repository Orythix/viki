# VIKI API — run the agent backend in Docker
# Use FLASK_HOST=0.0.0.0 when running in Docker so the API is reachable.

FROM python:3.11-slim

WORKDIR /app

# Copy project and install dependencies
COPY pyproject.toml ./
COPY viki/ ./viki/
RUN pip install --no-cache-dir -e .

# Create data and workspace dirs (volumes will override at runtime)
RUN mkdir -p /app/data /app/workspace

EXPOSE 5000

# Default: run the API server. Set FLASK_HOST=0.0.0.0 in docker run or compose.
CMD ["python", "-m", "viki.api.server"]
