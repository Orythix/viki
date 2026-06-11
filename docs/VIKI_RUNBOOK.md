# VIKI Operational Runbook

Operational procedures for running, verifying, and recovering **VIKI** on a workstation or in Docker. For first-time install, see [docs/SETUP.md](docs/SETUP.md). For security hardening, see [SECURITY_SETUP.md](../SECURITY_SETUP.md).

---

## 1. Scope and audience

| Audience | Use this runbook for |
|----------|----------------------|
| Operator | Daily start/stop, health checks, log locations |
| Maintainer | Config changes, Ollama alignment, incident triage, Docker |

---

## 2. Preconditions

| Check | Command / action | Expected |
|-------|------------------|----------|
| Python | `python --version` | 3.10+ (3.11+ recommended) |
| Dependencies | `pip install -e .` | No install errors |
| Ollama daemon | `ollama serve` (see §3) | Process listening (default `127.0.0.1:11434`) |
| Model pulled | `ollama list` | At least the tag in `config/models.yaml` → `models.default` (e.g. `gemma4:12b`) |
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

Ollama must listen on **all interfaces** for the container to reach it:

```powershell
# Option A — manual
$env:OLLAMA_HOST = "0.0.0.0:11434"
$env:OLLAMA_CUDA = "0"
Start-Process "ollama.exe" -ArgumentList "serve" -WindowStyle Hidden
docker compose build
docker compose run --rm -it viki

# Option B — startup script (recommended)
.\scripts\start-ollama.ps1
```

```bash
# Linux/Mac
chmod +x scripts/start-ollama.sh
./scripts/start-ollama.sh
```

### 3.3 Custom Modelfiles

Two Modelfiles ship with the project:

| File | Base model | Temperature | Context | Use case |
|------|-----------|-------------|---------|----------|
| `Modelfile` | `gemma4:latest` | 0.6 | default | Conversational / general purpose with persona immersion |
| `Modelfile.engineer` | `gemma3:12b` | 0.2 | 32768 | Technical data engineering / Azure / AI expert |

Build a custom Ollama model from either:

```powershell
ollama create viki-engineer -f Modelfile.engineer
```

Then reference it in `config/models.yaml` under a new profile.

### 3.4 Environment overrides

| Variable | Purpose |
|----------|---------|
| `VIKI_DATA_DIR` | Absolute path for SQLite, narrative DB, sessions |
| `VIKI_WORKSPACE_DIR` | Workspace root for file skills |
| `VIKI_PERSONA` | Overrides `system.persona` (`sovereign` default, `engineer` available) |
| `VIKI_AIR_GAP` | `1` / `true` — only local Ollama models in routing |
| `VIKI_LOCAL_LLM_ONLY` | `true` / `false` — block cloud API profiles |
| `VIKI_TRUST_WORKSPACE` | `true` — skip interactive trust prompt (required for Docker) |
| `VIKI_OLLAMA_THINK` | `false` — disable chain-of-thought for all local models |
| `VIKI_LOG_LEVEL` | `INFO` / `DEBUG` — logging verbosity (default `INFO`) |
| `VIKI_FORGE_BASE_OLLAMA_MODEL` | Base tag for Neural Forge Modelfile `FROM` line |
| `VIKI_FORGE_OUTPUT_OLLAMA_MODEL` | Output tag for prompt-bake (default `viki-neural-forge`) |
| `VIKI_EMBED_GPU` | `1` — run sentence-transformers on CUDA |
| `VIKI_UNSLOTH_RUN_TRAIN` | `1` — allow GPU LoRA training in forge |
| `VIKI_GIT_CONTEXT` | `1` — inject git snapshot into deliberation context |
| `VIKI_SESSION_USAGE_LOG` | Overrides `system.session_usage_log` |
| `VIKI_ENDPOINT_GUARD` | `1`/`0` — enable/disable endpoint guard |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` — auto-set in Docker |

---

## 4. Configuration map

| File | What to change |
|------|----------------|
| `config/settings.yaml` | `system.*`, `memory.*`, `forge.*`, `endpoint_guard.*`, timeouts |
| `config/models.yaml` | `models.default` profile name, `fallback_order`, per-profile `model_name`, `ollama_options` |
| `config/soul.yaml` | Core identity prompt (The Code Eternal / Supreme Architect) |
| `config/personas/sovereign.yaml` | Default philosophical persona |
| `config/personas/engineer.yaml` | Engineering persona (terminal-style, multi-agent reasoning) |
| `Modelfile` | Ollama system prompt for `ollama create` (general persona) |
| `Modelfile.engineer` | Ollama system prompt for engineering-focussed variant |
| `docker-compose.yml` | Docker env vars, volume mounts |
| `.env` (optional) | `VIKI_API_KEY`, `VIKI_ADMIN_SECRET`, cloud API keys |

### 4.1 Model routing

`config/models.yaml` controls which model is used for each task:

```yaml
models:
  default: gemma4            # primary model
  routing:
    fallback_order:          # tried in sequence on failure
      - gemma4
      - viki-evolved
      - phi3-mini
      - gpt-5
      - claude-sonnet
    task_routes:
      coding:
        primary: gemma4
      reasoning:
        primary: viki-evolved
      fast:
        primary: phi3-mini   # lightweight for quick responses
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
┌─────────────────┐     host.docker.internal:11434     ┌──────────┐
│  VIKI Container  │ ──────────────────────────────►   │  Ollama   │
│  python -m viki  │                                   │  (host)   │
└────────┬─────────┘                                   └──────────┘
         │
    ┌────┴─────┐
    │ /host-config  ◄── mounted from ./config/
    │ (copied to /app/src/viki/config/ at startup via entrypoint)
    └──────────┘
```

**Critical**: Ollama must listen on `0.0.0.0` (not `127.0.0.1`). Set `OLLAMA_HOST=0.0.0.0:11434` before starting.

### 5.2 Entrypoint behaviour (`docker-entrypoint.sh`)

At container startup:

1. Copies `*.yaml` / `*.yml` from `/host-config` → `/app/src/viki/config/`
2. Verifies `settings.yaml` landed at destination (warns if missing)
3. Probes Ollama at `$OLLAMA_HOST/api/tags` (warns if unreachable)
4. Executes the main command (`python -m viki`)

### 5.3 Env vars (docker-compose.yml)

```yaml
environment:
  VIKI_DATA_DIR: /app/data
  VIKI_WORKSPACE_DIR: /app/workspace
  VIKI_TRUST_WORKSPACE: "true"       # skip trust prompt
  VIKI_OLLAMA_THINK: "false"         # disable thinking
  VIKI_LOG_LEVEL: "INFO"             # production logging
  OLLAMA_HOST: http://host.docker.internal:11434
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
| Ollama reachability | `curl http://127.0.0.1:11434/api/tags` |
| Model smoke test | `ollama run <tag>` |
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

**Cause**: Ollama bound to `127.0.0.1` only — unreachable from container.

**Fix**: Restart Ollama with `OLLAMA_HOST=0.0.0.0:11434`.

### 9.2 `I encountered a parsing issue`

**Cause**: Model returned invalid JSON to `chat_structured`.

**Fix**: The retry loop (§4.3) handles this automatically. If persistent:
- Switch to a model better at structured output (gemma4 > phi3-mini)
- Ensure `ollama_enable_thinking: false` for the profile
- Check model RAM pressure (small models often fail JSON at high context)

### 9.3 Model circuit-breaker activated

**Symptom**: A model is skipped despite being available.

**Fix**: The cooldown expires automatically after 60s. Check `/status` for model health. Clear via `record_model_success(model_name)` if needed.

### 9.4 Config changes not reflected in Docker

**Cause**: Entrypoint copies `./config/` at startup; old config baked into image.

**Fix**: Edit files in `./config/` on the host and restart the container. If the image is stale, rebuild with `docker compose build`.

### 9.5 `Deliberation Model Failure` / API `401`

**Cause**: Cloud profile selected with placeholder API key.

**Fix**: Set `local_llm_only: true` in `config/settings.yaml` or `VIKI_LOCAL_LLM_ONLY=true`. Ensure `models.default` points to an Ollama profile.

### 9.6 Slow first reply

**Cause**: Cold Ollama load, embedding model download, ensemble deliberation.

**Mitigation**: Pre-pull models with `ollama pull`; set `use_ensemble: false` in settings for speed.

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
| Weekly | `ollama list` vs `config/models.yaml`; check disk space |
| After upgrades | `python -m pytest tests/ -q`; one manual CLI conversation |
| Before demos | Fresh shell, confirm Ollama is running, check default model tag |

---

## 12. Neural Forge (model building)

### 12.1 Prompt bake (CPU)

Accumulate reinforced lessons via conversation, then bake them into an Ollama model:

```powershell
python scripts/build_viki_model.py
```

This reads from the SQLite lesson store, exports top lessons to JSONL, writes a `Modelfile.viki_evolved` with a `SYSTEM` block embedding those lessons, and runs `ollama create viki-neural-forge`.

### 12.2 Custom Modelfiles

Build from a custom personality:

```powershell
ollama create viki-engineer -f Modelfile.engineer
```

Then add a profile to `config/models.yaml`:

```yaml
profiles:
  viki-engineer:
    provider: ollama
    model_name: viki-engineer
    priority: 95
    capabilities: [chat, reasoning, coding]
```

### 12.3 LoRA / GPU training

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

*Runbook version: aligned with VIKI v8.3.0 (The Code Eternal). Update this file when default ports, flags, or critical paths change.
