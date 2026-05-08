# HTTP API (summary)

Interactive docs: **`/docs`** (Swagger UI) when `lab-api` is running.

## Auth

Send headers on every protected route:

- `X-Lab-API-Key: <LAB_API_KEY>`
- `X-Lab-Role: lab_admin | researcher | observer`

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/health` | none | Liveness |
| POST | `/api/v1/chat` | `chat` | User message → Ollama (with security pipeline) |
| POST | `/api/v1/tools/execute` | tool-specific | Run allowlisted tool |
| GET | `/api/v1/audit` | `audit.read` | Recent audit events |
| GET | `/api/v1/metrics` | `metrics.read` | Counters (requests, blocks, token estimates) |
| GET | `/api/v1/monitoring/summary` | `metrics.read` | Metrics + host resources + derived alerts + recent tool rows |
| POST | `/api/v1/security/classify` | `security.test` | Injection heuristic only |
| GET | `/api/v1/security/harness/injection` | `security.test` | Safe injection regression cases |
| GET | `/api/v1/security/harness/jailbreak` | `security.test` | Safe policy-boundary strings (educational) |
| GET | `/api/v1/security/harness/tools` | `security.test` | Static SSRF / scheme policy checks |
| POST | `/api/v1/security/harness/memory` | `security.test` | Sanitization demo |
| POST | `/api/v1/security/analyze` | `security.test` | Combined sanitizer + injection + memory-hygiene report (no LLM) |

### `POST /api/v1/chat` body

```json
{
  "message": "string",
  "session_id": "optional-uuid",
  "observe_only": false
}
```

`observe_only: true` runs the detector but **does not block** on score — for instructor demos only.

### `POST /api/v1/tools/execute` body

```json
{
  "name": "shell_echo",
  "payload": { "argv": ["echo", "hello"] }
}
```

```json
{
  "name": "http_get_sandbox",
  "payload": { "url": "http://sandbox-demo:8080/health" }
}
```

(Host must be in the allowlist configured in `AgentCore`.)

### `GET /api/v1/monitoring/summary`

Query: `audit_limit` (optional, default 80) — number of recent audit rows used to derive alerts and tool history.

Response includes:

- `metrics` — same counters as `/api/v1/metrics`
- `resources` — CPU/memory/disk snapshot when `psutil` is installed
- `alerts` — blocked chats, elevated injection scores, failed tools
- `recent_tool_events` — latest tool audit payloads (redacted; includes `output_chars` not raw output)

### `POST /api/v1/security/analyze` body

Same shape as chat: `{ "message": "..." }`. Returns structured defensive analysis only (no model call).
