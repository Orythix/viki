# Docker for QA

## Goals

- **Reproducible** toolchain (Python/Java/Node/k6 versions).
- **Ephemeral** SUT: `docker compose` for `security-lab` + run tests from host or sidecar.

## Pattern A — tests on host, API in Docker

```bash
cd security-lab/docker && docker compose up -d
cd qa-automation && set QA_LIVE_API=1 && pytest tests/live -m smoke
```

## Pattern B — CI runner image (optional)

Build an image that contains `python3`, `maven`, `k6`, `node` — only if your org forbids installing tools on hosted runners (rare on GitHub-hosted).

## Security

- Do not bake **secrets** into images; inject at runtime (`-e QA_API_KEY`).
- Pull images from trusted registries; pin digests for enterprise.
