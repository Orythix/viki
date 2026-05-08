# VIKI Operational Runbook

Operational procedures for running, verifying, and recovering **VIKI** on a workstation. For first-time install, see [SETUP.md](SETUP.md). For credentials and API hardening, see [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md).

---

## 1. Scope and audience

| Audience | Use this runbook for |
|----------|----------------------|
| Operator | Daily start/stop, health checks, log locations |
| Maintainer | Config changes, Ollama alignment, incident triage |

---

## 2. Preconditions (before every run)

Check all items before starting the core or UI.

| Check | Command / action | Expected |
|-------|------------------|----------|
| Python | `python --version` | 3.10+ (3.11+ recommended per [SETUP.md](SETUP.md)) |
| Dependencies | `pip install -r requirements.txt` (from repo root) | No install errors |
| Ollama daemon | Ollama app running or `ollama serve` | Process listening (default `127.0.0.1:11434`) |
| Model tags | `ollama list` | At least the tag configured in `viki/config/models.yaml` for `models.default` (e.g. `qwen3.5:latest` for profile `qwen35`) |
| Optional HF | `HF_TOKEN` in env | Reduces Hub rate limits for sentence-transformers loads |

---

## 3. Standard startup

### 3.1 CLI (interactive terminal)

From the **repository root** (directory that contains `viki/`):

```powershell
python viki/main.py
```

- Exit: type `exit` at the prompt.
- If you use a venv, activate it first (see [SETUP.md](SETUP.md)).

### 3.2 CLI + hologram / web UI

1. Terminal A — UI dev server: `cd ui` then `npm run dev`
2. Terminal B — VIKI with API for UI: `python viki/main.py --ui`

Browser: typically `http://localhost:5173`. The UI must authenticate: set `VITE_VIKI_API_KEY` in `ui/.env` to match `VIKI_API_KEY` (see [SETUP.md](SETUP.md)).

### 3.3 Environment overrides (common)

| Variable | Purpose |
|----------|---------|
| `VIKI_DATA_DIR` | Absolute path for SQLite, narrative DB, sessions, etc. |
| `VIKI_WORKSPACE_DIR` | Workspace root for file skills |
| `VIKI_PERSONA` | Overrides `system.persona` in settings (e.g. `dev`, `research`) |
| `VIKI_AIR_GAP` | `1` / `true` / `yes` — only **local** Ollama models in routing |
| `VIKI_LOCAL_LLM_ONLY` | `true` / `false` — when `true`, OpenAI/Anthropic profiles are never selected |
| `VIKI_FORGE_BASE_OLLAMA_MODEL` | Base Ollama tag for Neural Forge Modelfile `FROM` line |
| `VIKI_FORGE_OUTPUT_OLLAMA_MODEL` | Output Ollama tag for prompt-bake / `internal_forge` (`ollama create`; default **`viki-neural-forge`** if unset) |
| `VIKI_EMBED_GPU` | `1` / `true` — run sentence-transformers encoder on CUDA when available |
| `VIKI_UNSLOTH_RUN_TRAIN` | `1` / `true` — allow GPU LoRA training inside `internal_forge` (requires Unsloth stack) |
| `VIKI_GIT_CONTEXT` | `1` / `true` — append **git snapshot** (branch, status, recent commits) from `workspace_dir` to deliberation context |
| `VIKI_SESSION_USAGE_LOG` | `true` / `false` — when set, overrides `system.session_usage_log` (append JSONL usage under `data_dir`) |
| `VIKI_ENDPOINT_GUARD` | `1` / `true` / `yes` enables, `0` / `false` / `no` disables `endpoint_guard` (local heuristic watcher; not a full AV replacement) |

### 3.4 Local endpoint guard (antivirus companion)

`endpoint_guard` in `viki/config/settings.yaml` watches **download folders** (XDG on Linux, `~/Downloads`, plus **workspace_dir**; non-recursive by default) for new files, applies **heuristic** risk scoring (e.g. double extensions, ransomware-like names), logs warnings, can record a lesson, and on **high** severity may invoke **Microsoft Defender** on Windows or **ClamAV** (`clamscan` / `clamdscan` on `PATH`) when `use_clamav_cli` is true on Linux/macOS/BSD. **Keep your normal antivirus enabled** — this layer is an assistant, not a substitute for a full AV product.

---

## 4. Configuration map

| File | What to change |
|------|----------------|
| `viki/config/settings.yaml` | `system.*`, `memory.short_term_limit` (10–50), `system.use_ensemble`, `system.session_usage_log`, `system.forge_base_ollama_model`, `system.forge_output_ollama_tag`, `endpoint_guard.*`, timeouts |
| `viki/config/models.yaml` | `models.default` profile name; profile `model_name` must match `ollama list` exactly |
| `.env` (optional) | `VIKI_API_KEY`, `VIKI_ADMIN_SECRET`, cloud keys if `local_llm_only: false` |

**Local-only default:** `system.local_llm_only: true` skips cloud API profiles. Use real `sk-…` / `sk-ant-…` keys only when you set `local_llm_only: false` and intend to use GPT/Claude profiles.

**Do not** set `OPENAI_API_KEY=ollama` — that is not a valid OpenAI secret and will disable or mis-route official OpenAI profiles.

---

## 5. Health and verification

| Action | How |
|--------|-----|
| In-CLI status | Send `/status` (if supported in your build) |
| Ollama reachability | `curl http://127.0.0.1:11434/api/tags` or `ollama list` |
| Model smoke | `ollama run <tag>` with the same tag as in `models.yaml` |
| Automated tests | From repo root: `python -m pytest viki/tests/ -q` |

### 5.1 Session usage ledger (`usage_session.jsonl`)

When `system.session_usage_log` is true (default), VIKI appends one JSON object per line to `{data_dir}/usage_session.jsonl`:

- **`llm_inference`** — wall time for a provider `chat` / `chat_structured` / `chat_with_tools` call (Ollama or cloud).
- **`model_feedback`** — updates from `LLMProvider.record_performance` (trust score bookkeeping; may reflect tool outcomes, not only raw LLM time).
- **`skill_execution`** — skill runs from the controller (success, latency, optional short error).

Filter with `jq`: `jq 'select(.event=="llm_inference")' data/usage_session.jsonl`. Set `VIKI_SESSION_USAGE_LOG=false` to disable without editing YAML.

---

## 6. Shutdown and restart

| Scenario | Procedure |
|----------|-----------|
| Clean exit (CLI) | `exit` at `USER >` / `VIKI >` |
| Hung process | Stop the terminal job or end the Python process in Task Manager / `Stop-Process` |
| After config change | Restart `python viki/main.py` (or `--ui` stack). Restart UI dev server if you changed `ui/.env` |

---

## 7. Troubleshooting playbooks

### 7.1 `Context Retrieval Failed: expected sequence of length 384 at dim 1 (got 0)`

**Cause:** Episodic DB rows with empty or invalid embedding vectors mixed into semantic search.

**Fix:** Current code filters invalid vectors; restart VIKI after upgrade. If it persists, inspect `orythix_narrative.db` under your `data_dir` or reset that DB only (backup first).

### 7.2 `Deliberation Model Failure` / OpenAI `401` / `Incorrect API key provided: ollama`

**Cause:** Cloud profile selected with a placeholder or wrong `OPENAI_API_KEY`.

**Fix:**

1. Prefer local routing: `local_llm_only: true` in `viki/config/settings.yaml` (default) or `VIKI_LOCAL_LLM_ONLY=true`.
2. Unset bogus keys or use a real `sk-…` key only when using official OpenAI.
3. Ensure `models.default` points to an **Ollama** profile and the model is pulled.

### 7.3 `Internal Error: The local model echoed the schema…`

**Cause:** Local LLM returned JSON Schema text instead of a `VIKIResponse` payload.

**Fix:** Upgrade to the current `LocalLLM.chat_structured` behavior (compact JSON guide + recovery). Restart VIKI. If a model is consistently bad at JSON, switch `models.default` to another tag in `models.yaml`.

### 7.4 Very slow first reply after startup

**Cause:** Embedding model download/load (sentence-transformers), cold Ollama load, or ensemble deliberation.

**Mitigation:** Pre-pull Ollama models; optional `HF_TOKEN`; reduce `use_ensemble` in settings if latency dominates.

### 7.5 Webcam / MSMF noise on Windows

**Cause:** Bio webcam enabled without a usable camera.

**Fix:** Keep `system.bio_webcam_enabled: false` or `VIKI_BIO_WEBCAM=0` unless you need webcam (see [SETUP.md](SETUP.md)).

---

## 8. Data and logs

| Path (typical) | Contents |
|----------------|----------|
| `./data` or `VIKI_DATA_DIR` | SQLite DBs, sessions, forge artifacts, `orythix_narrative.db` |
| `./workspace` or `VIKI_WORKSPACE_DIR` | Project files for file skills |
| Console / terminal | `[VIKI]` log lines; level from `system.log_level` in settings |

---

## 9. Maintenance cadence (suggested)

| Frequency | Task |
|-----------|------|
| Weekly | `ollama list` vs `models.yaml`; disk space on `data_dir` |
| After upgrades | `python -m pytest viki/tests/ -q`; one manual CLI conversation |
| Before demos | Fresh shell, confirm `local_llm_only` and default model tag |

---

## 10. Strengthening cognition (quality vs speed)

Use these levers together; they trade **latency** for **depth** where noted.

| Goal | What to do |
|------|------------|
| Stronger reasoning | In `viki/config/models.yaml`, set `models.default` to your **best** pulled Ollama tag; add cloud profiles only with real keys and `local_llm_only: false` if appropriate. |
| Deeper multi-step “debate” | Keep `system.use_ensemble: true` in `viki/config/settings.yaml`. For **maximum speed**, set `use_ensemble: false`. |
| Longer conversational context | Raise `memory.short_term_limit` (allowed range **10–50** after load). |
| Baked-in lesson knowledge | Accumulate reinforced lessons, then run skill **`internal_forge`** (builds Ollama `viki-neural-forge` from `Modelfile.viki_evolved` by default; override via `forge_output_ollama_tag` / `VIKI_FORGE_OUTPUT_OLLAMA_MODEL`). See [SETUP.md](SETUP.md) evolution notes. |
| GPU LoRA (optional) | CUDA + Unsloth stack; set `VIKI_UNSLOTH_RUN_TRAIN=1` and use forge `strategy: lora` or `auto` when Unsloth is available. |
| Faster embeddings | Set `VIKI_EMBED_GPU=true` if CUDA is available (shared MiniLM encoder). |
| Right tool surface | Set `VIKI_PERSONA` / `system.persona` (`dev`, `research`, etc.) so the skill registry matches the workload. |
| Fewer startup surprises | Keep `startup_research: false` unless you want the first minutes competing with user traffic. |
| Repo-aware answers (coding) | Set `system.git_workspace_context: true` or `VIKI_GIT_CONTEXT=1` so `workspace_dir` git branch/status is injected (cached ~45s). Requires `git` on PATH and a `.git` repo at the workspace root. |

---

## 11. Internet-sourced training (lessons → Neural Forge)

VIKI does not scrape the whole web for pretraining. **Internet → SQLite lessons → export JSONL → Ollama bake / LoRA** is the supported path.

| Step | What to do |
|------|------------|
| Grow lessons from the web | Use the **research** skill in chat (persona must allow `research`: sovereign, research, coding, dev, …), paste URLs, or run **`python scripts/ingest_web_topics.py --file topics.txt`** (one DuckDuckGo query per line). Requires `duckduckgo-search` or `ddgs` (see `pyproject.toml`). |
| Auto-lookup on uncertainty | With `system.auto_web_research_when_uncertain: true` (and not air-gap/shadow), uncertain replies trigger search; snippets can still feed lessons via the research path. |
| Export threshold | `export_training_dataset` includes lessons with `access_count >= N`. Set **`system.lesson_export_min_access_count`** (default **2**), **`VIKI_LESSON_EXPORT_MIN_ACCESS`**, or **`python scripts/build_viki_model.py --min-count`** so JSONL and prompt-bake stay aligned. |
| Import curated JSONL | From Python or a small harness: `LearningModule.import_lessons_from_jsonl(path, reinforce=True)` to load `trigger`/`fact` (or Alpaca / chat) lines; optional per-line **`source_task`**, **`author`**, **`reliability`**. **`python scripts/seed_knowledge.py`** loads `viki/config/knowledge_seed.jsonl` (operator + reference facts); add `--reinforce` for export-ready `access_count`. |
| Bake a model | From repo root: **`python scripts/build_viki_model.py`** (CPU prompt-bake) or **`--strategy lora`** with **`VIKI_UNSLOTH_RUN_TRAIN=1`** and CUDA. See script docstring and §10 above. |
| **RAG retrieval eval** | Curate JSONL gold (`must_contain_any` / `must_contain_all`) and run **`python scripts/run_rag_eval.py --gold viki/eval/fixtures/rag_gold.example.jsonl --out reports/rag_eval.json`**. Add **`--judge`** for optional local Ollama relevance scoring. See [viki/eval/README.md](viki/eval/README.md). |

Disable internet training by **`VIKI_AIR_GAP=1`** (no outbound search).

### Model size vs “growing like a human”

The **base Ollama GGUF** for a given tag has an essentially **fixed on-disk size** (for example ~9 GiB for a quantised 7B-class model). VIKI does **not** automatically swell that blob. What grows is:

- the **SQLite lesson store** (facts, including web snippets), and  
- the **Modelfile `SYSTEM` block** when you **prompt-bake** (`internal_forge` / `build_viki_model.py`), which re-embeds consolidated lessons into the derived image (default tag `viki-neural-forge`).

Optional **LoRA adapters** add a separate small adapter directory; moving to a **larger base model** (new `ollama pull`) is a manual upgrade.

### Boot-time background evolution (optional)

| Goal | Action |
|------|--------|
| Evolve while the main UI runs | Set **`forge.background_evolution_at_boot: true`** in `viki/config/settings.yaml` (or **`VIKI_BACKGROUND_EVOLUTION_AT_BOOT=1`**). After **`boot_evolution_delay_s`**, VIKI runs a few DuckDuckGo queries (from **`boot_topics_file`** and/or **`boot_research_queries`**) then **`internal_forge`** with **`prompt_bake`** by default (CPU). |
| Evolve at Windows logon without opening the CLI | Run **`scripts\Register-VikiBootTask.ps1`** once, or schedule **`python scripts/viki_headless_boot_evolve.py`** with **`VIKI_SKIP_STARTUP_PULSE=1`** implied. Use **`VIKI_BOOT_EVOLVE_FORCE=1`** in the task environment to run even if YAML keeps `background_evolution_at_boot` false. |
| Topic list | Copy [`viki/config/boot_topics.txt.example`](viki/config/boot_topics.txt.example) to **`data/boot_topics.txt`** (under your `VIKI_DATA_DIR`). |

Keep **`low_resource_mode`** or **`air_gap`** on hosts that must not do this work at boot.

---

## 12. References

- [SETUP.md](SETUP.md) — install and first run  
- [README.md](README.md) — product overview and architecture pointers  
- [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) — full documentation index  
- [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md) — API keys, UI auth, integrations  
- [security-lab/README.md](security-lab/README.md) — optional local defensive AI security lab  
- [qa-automation/README.md](qa-automation/README.md) — optional QA automation learning tracks  

---

*Runbook version: aligned with VIKI v7.x tree. Update this file when default ports, flags, or critical paths change.*
