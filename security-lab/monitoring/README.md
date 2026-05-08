# Monitoring

## Backend

- **`GET /api/v1/metrics`** — request counts, heuristic blocks, rough token estimates (in-process counters).
- **`GET /api/v1/audit`** — SQLite- or PostgreSQL-backed events (`chat`, `tool`) with structured payloads (secrets redacted at write time where applicable).
- **`GET /api/v1/monitoring/summary`** — aggregates metrics, **`monitoring/telemetry.resource_snapshot()`** (optional `psutil`), and **`monitoring/alerts.alerts_from_audit_entries()`** for a single dashboard poll.

## Modules

| File | Purpose |
|------|---------|
| `telemetry.py` | Host CPU/memory/disk snapshot for correlating abuse with load. |
| `alerts.py` | Rule-based alerts from audit rows (blocks, elevated scores, tool failures). |

## Production hardening

- Export audit to a SIEM, add OpenTelemetry traces, and run the API behind mTLS for multi-user labs.
- Keep Compose ports bound to **`127.0.0.1`**; never expose Ollama or the lab API to untrusted networks without additional controls.

The React dashboard (`frontend/`) calls **`/api/v1/monitoring/summary`** and the security harness endpoints for an operator view.
