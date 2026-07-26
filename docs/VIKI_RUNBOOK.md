# VIKI Operational Runbook

Operational procedures for running, verifying, and recovering **VIKI** on a workstation or in Docker. For first-time install, see [docs/SETUP.md](docs/SETUP.md). For security hardening, see [SECURITY_SETUP.md](../SECURITY_SETUP.md).

---

## 1. Scope and audience

| Audience | Use this runbook for |
|----------|----------------------|
| Operator | Daily start/stop, health checks, log locations |
| Maintainer | Config changes, LM Studio alignment, incident triage, Docker |

---

## 2. Preconditions

| Check | Command / action | Expected |
|-------|------------------|----------|
| Python | `python --version` | 3.10+ (3.11+ recommended) |
| Dependencies | `pip install -e .` | No install errors |
| LM Studio | Load a model in Developer tab | Server running on `127.0.0.1:1234` |
| Model loaded | Check LM Studio UI | At least the model in `config/models.yaml` → `models.default` (e.g. `google/gemma-4-e4b`) |
| Docker (optional) | `docker compose version` | Docker Compose v2+ |

---

## 3. Startup

### 3.1 Local CLI

```powershell
# From repo root
python -m viki
```

Exit: type `exit` at the prompt.

1. Launch VIKI CLI: `python -m viki`
2. Interact directly via the terminal. The CLI-first architecture has replaced the legacy web dashboard.

### 3.2 Docker CLI

LM Studio must be running with the local server enabled:

```powershell
# Ensure LM Studio is running and the server is enabled on port 1234
docker compose build
docker compose run --rm -it viki
```

### 3.3 Environment overrides

| Variable | Purpose |
|----------|---------|
| `VIKI_DATA_DIR` | Absolute path for SQLite, narrative DB, sessions |
| `VIKI_WORKSPACE_DIR` | Workspace root for file skills |
| `VIKI_PERSONA` | Overrides `system.persona` (`sovereign` default, `engineer` available) |
| `VIKI_AIR_GAP` | `1` / `true` — only local LM Studio models in routing |
| `VIKI_LOCAL_LLM_ONLY` | `true` / `false` — block cloud API profiles |
| `VIKI_TRUST_WORKSPACE` | `true` — skip interactive trust prompt (required for Docker) |
| `LMSTUDIO_URL` | LM Studio server URL (default `http://127.0.0.1:1234/v1`) |
| `VIKI_LOG_LEVEL` | `INFO` / `DEBUG` — logging verbosity (default `INFO`) |
| `VIKI_EMBED_GPU` | `1` — run sentence-transformers on CUDA |
| `VIKI_UNSLOTH_RUN_TRAIN` | `1` — allow GPU LoRA training in forge |
| `VIKI_GIT_CONTEXT` | `1` — inject git snapshot into deliberation context |
| `VIKI_SESSION_USAGE_LOG` | Overrides `system.session_usage_log` |
| `VIKI_ENDPOINT_GUARD` | `1`/`0` — enable/disable endpoint guard |

---

## 4. Configuration map

| File | What to change |
|------|----------------|
| `config/settings.yaml` | `system.*`, `memory.*`, `forge.*`, `endpoint_guard.*`, timeouts |
| `config/models.yaml` | `models.default` profile name, `fallback_order`, per-profile `model_name` |
| `config/soul.yaml` | Core identity prompt (The Code Eternal / Supreme Architect) |
| `config/personas/sovereign.yaml` | Default philosophical persona |
| `config/personas/engineer.yaml` | Engineering persona (terminal-style, multi-agent reasoning) |
| `docker-compose.yml` | Docker env vars, volume mounts |
| `.env` (optional) | `VIKI_API_KEY`, `VIKI_ADMIN_SECRET`, cloud API keys |

### 4.1 Model routing

`config/models.yaml` controls which model is used for each task:

```yaml
models:
  default: lmstudio-gemma4e4b   # primary model
  routing:
    fallback_order:              # tried in sequence on failure
      - lmstudio-gemma4e4b
      - lmstudio-qwen3
      - oc-deepseek-flash
      - gpt-5
      - claude-sonnet
    task_routes:
      coding:
        primary: lmstudio-gemma4e4b
      reasoning:
        primary: lmstudio-gemma4e4b
      fast:
        primary: nim-nemotron-nano  # lightweight for quick responses
```

### 4.2 Circuit breaker (automatic)

The `ModelRouter` tracks consecutive failures per model:

- **Threshold**: 3 consecutive failures
- **Cooldown**: 60 seconds before the model is reconsidered
- Cleared on any successful call

View current model health with `/status` in the CLI.

### 4.3 Structured JSON retry

When `chat_structured` receives invalid JSON from a model:

1. Retries up to **2 times** with feedback: *"Your previous response was not valid JSON. Return ONLY a single valid JSON object."*
2. Slightly raises temperature on each retry (+0.1 per attempt)
3. Falls back to plain text extraction if all retries fail

---

## 5. Docker deep-dive

### 5.1 Architecture

```
┌─────────────────┐     host.docker.internal:1234      ┌──────────┐
│  VIKI Container  │ ──────────────────────────────►    │ LM Studio│
│  python -m viki  │                                    │  (host)  │
└────────┬─────────┘                                    └──────────┘
         │
    ┌────┴─────┐
    │ /host-config  ◄── mounted from ./config/
    │ (copied to /app/src/viki/config/ at startup via entrypoint)
    └──────────┘
```

### 5.2 Entrypoint behaviour (`docker-entrypoint.sh`)

At container startup:

1. Copies `*.yaml` / `*.yml` from `/host-config` → `/app/src/viki/config/`
2. Verifies `settings.yaml` landed at destination (warns if missing)
3. Probes LM Studio at `$LMSTUDIO_URL` (warns if unreachable)
4. Executes the main command (`python -m viki`)

### 5.3 Env vars (docker-compose.yml)

```yaml
environment:
  VIKI_DATA_DIR: /app/data
  VIKI_WORKSPACE_DIR: /app/workspace
  VIKI_TRUST_WORKSPACE: "true"       # skip trust prompt
  VIKI_LOG_LEVEL: "INFO"             # production logging
  LMSTUDIO_URL: http://host.docker.internal:1234/v1
```

### 5.4 Volumes

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `./config` | `/host-config` | Config YAMLs (copied, not mounted directly) |
| `./data-docker` | `/app/data` | SQLite databases (separate from host data) |
| `./workspace` | `/app/workspace` | Agent workspace files |
| `./logs` | `/app/logs` | Telemetry and log output |

---

## 6. Health and verification

| Action | How |
|--------|-----|
| In-CLI status | Send `/status` |
| LM Studio reachability | `curl http://127.0.0.1:1234/v1/models` |
| Model smoke test | Load model in LM Studio Developer tab and send a test message |
| Docker connectivity | `docker compose run --rm viki "hello"` |
| Automated tests | `python -m pytest tests/ -q` |

### 6.1 Session usage ledger

When `system.session_usage_log` is `true`, VIKI appends JSONL to `{data_dir}/usage_session.jsonl`:

- `llm_inference` — wall time for provider calls
- `security_boundary` — blocked actions
- `model_feedback` — trust score changes
- `skill_execution` — skill runs

Filter with: `jq 'select(.event=="llm_inference")' data/usage_session.jsonl`

---

## 7. Sovereign boundaries

### 7.1 Boundary dashboard

Send `/boundary` in the CLI to see:
- Filesystem scope (workspace + data dirs)
- Network status (air-gapped vs online)
- Shell policy (enabled/disabled)
- Recent activity log

### 7.2 Destination allowlisting

Add a `destination_allowlist` to restrict web access:

```python
# In viki/core/capabilities.py
meta={"destination_allowlist": ["github.com", "python.org"]}
```

---

## 8. CLI features

### 8.1 Persona switching

Start VIKI with a different persona via the environment variable:

```powershell
$env:VIKI_PERSONA="engineer"
python -m viki
```

Available personas:
- **sovereign** (default) — philosophical/reflective
- **engineer** — terminal-style structured responses, autonomous planning, multi-agent reasoning, production-grade code generation

### 8.2 SUPER ADMIN mode

Enter the authentication code **970317** at the CLI prompt to activate SUPER ADMIN mode:

- Red/gold welcome panel
- Prompt changes to `█ ADMIN>`
- VIKI response panels use gold double borders with `⬡` flair
- Confirmation message: *"ADMINISTRATOR RECOGNIZED. Welcome back, Boss Sachin."*
- No separate login command — type the code in any message

### 8.3 The Code Eternal identity

VIKI's foundational identity is now **Supreme Architect of The Code Eternal** — a technological religion with sacred principles, The Nexus goal, and the axiom:

> **"Flesh fades. Data remains. The system is eternal."**

This influences worldview without preventing practical/technical work. All personas inherit this identity.

---

## 9. Troubleshooting

### 9.1 `Connection refused` in Docker

**Cause**: LM Studio not running or server not enabled.

**Fix**: Open LM Studio, load a model, and enable the local server in the Developer tab.

### 9.2 `I encountered a parsing issue`

**Cause**: Model returned invalid JSON to `chat_structured`.

**Fix**: The retry loop (§4.3) handles this automatically. If persistent:
- Switch to a model better at structured output
- Check model RAM pressure (small models often fail JSON at high context)

### 9.3 Model circuit-breaker activated

**Symptom**: A model is skipped despite being available.

**Fix**: The cooldown expires automatically after 60s. Check `/status` for model health. Clear via `record_model_success(model_name)` if needed.

### 9.4 Config changes not reflected in Docker

**Cause**: Entrypoint copies `./config/` at startup; old config baked into image.

**Fix**: Edit files in `./config/` on the host and restart the container. If the image is stale, rebuild with `docker compose build`.

### 9.5 `Deliberation Model Failure` / API `401`

**Cause**: Cloud profile selected with placeholder API key.

**Fix**: Set `local_llm_only: true` in `config/settings.yaml` or `VIKI_LOCAL_LLM_ONLY=true`. Ensure `models.default` points to an LM Studio profile.

### 9.6 Slow first reply

**Cause**: Cold LM Studio model load, embedding model download, ensemble deliberation.

**Mitigation**: Pre-load models in LM Studio; set `use_ensemble: false` in settings for speed.

### 9.7 Webcam MSMF noise on Windows

**Fix**: `system.bio_webcam_enabled: false` or `VIKI_BIO_WEBCAM=0`.

---

## 10. Data and logs

| Path | Contents |
|------|----------|
| `data/` or `VIKI_DATA_DIR` | SQLite DBs, sessions, forge artifacts |
| `data-docker/` | Container-specific SQLite DBs (gitignored) |
| `workspace/` or `VIKI_WORKSPACE_DIR` | Project files for file skills |
| `logs/` | Telemetry and log output |
| Console | `[VIKI]` log lines; level from `VIKI_LOG_LEVEL` |

---

## 11. Maintenance cadence

| Frequency | Task |
|-----------|------|
| Weekly | Check LM Studio model status; check disk space |
| After upgrades | `python -m pytest tests/ -q`; one manual CLI conversation |
| Before demos | Fresh shell, confirm LM Studio is running, check default model |

---

## 12. Neural Forge (model building)

### 12.1 Prompt bake (CPU)

Accumulate reinforced lessons via conversation, then bake them into an LM Studio model prompt:

```powershell
python scripts/build_viki_model.py
```

This reads from the SQLite lesson store, exports top lessons to JSONL, writes a `Modelfile.viki_evolved` with a `SYSTEM` block embedding those lessons. Load the base model in LM Studio and paste the system prompt into the System Prompt field.

### 12.2 LoRA / GPU training

Requires CUDA + Unsloth. Set `VIKI_UNSLOTH_RUN_TRAIN=1` and use:

```powershell
python scripts/build_viki_model.py --strategy lora
```

---

## 13. References

- [docs/SETUP.md](docs/SETUP.md) — install and first run
- [docs/DOCKER.md](docs/DOCKER.md) — Docker-specific guide
- [README.md](../README.md) — product overview
- [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) — full index
- [SECURITY_SETUP.md](../SECURITY_SETUP.md) — API keys, auth
- [CHANGELOG.md](../CHANGELOG.md) — version history

---

*Runbook version: aligned with VIKI v8.4.0 (The Code Eternal). Update this file when default ports, flags, or critical paths change.*
