# Setting Up VIKI (v8.2.0 Sovereign)

## 📦 Prerequisites

1.  **Python 3.11+**: Ensure you have Python installed and added to PATH.
2.  **Ollama**: Install from [ollama.ai](https://ollama.ai) and pull the core models:
    ```bash
    ollama pull phi3
    ollama pull deepseek-r1
    ```
3.  **Visual Studio Build Tools** (Windows Only): Required for compiling `unsloth` dependencies if you plan to use `forge` for LoRA training.
4.  **rank_bm25**: Required for Hybrid Memory Search. Automatically installed via `pip install -e .`.

## 🛠️ Environment Configuration

1.  **Clone the Repository**:
    ```powershell
    git clone https://github.com/Orythix/viki.git
    cd viki   # or your clone folder name (e.g. VIKI)
    ```

2.  **Create Virtual Environment**:
    ```powershell
    python -m venv .venv
    ./.venv/Scripts/Activate.ps1
    ```

3.  **Install Dependencies**:
    ```powershell
    pip install -r requirements.txt
    ```

4.  **Set Up Environment Variables**:
    Create a `.env` file in the root directory (or set in your shell):
    ```env
    # Required for API security: all gateway endpoints (Discord, etc.) require this key
    VIKI_API_KEY=your_api_key_here

    # Required for super-admin / admin commands
    VIKI_ADMIN_SECRET=your_admin_secret_here

    # Optional: For high-intelligence reasoning fallbacks
    OPENAI_API_KEY=your_key_here

    # Optional: For Nexus Connectivity
    DISCORD_TOKEN=your_discord_token
    TELEGRAM_TOKEN=your_telegram_token
    ```
    **Security**: Generate strong values; never commit them. See [viki/SECURITY_docs/SETUP.md](viki/SECURITY_docs/SETUP.md) for details.

## 🚀 Running VIKI

To start the **Sovereign Intelligence Core** (CLI):

```powershell
python -m viki
```

VIKI will initialize her **Nexus** and begin listening on all channels.

### Troubleshooting (Windows)

- **`videoio(MSMF): can't grab frame` after each message**: The BioModule webcam sensor is **off by default** (`system.bio_webcam_enabled: false` in `viki/config/settings.yaml`). If you still see this on an older build, upgrade to the current tree or set `VIKI_BIO_WEBCAM=0` in `.env`. Enable only with a working camera: `VIKI_BIO_WEBCAM=1` or `bio_webcam_enabled: true`.
- **Hugging Face `HF_TOKEN` / rate limits**: Optional; set `HF_TOKEN` in the environment if you download many models from the Hub.

## 🧪 Testing

To verify key systems:

1.  **Status Check**: Type `/status` in the terminal.
2.  **Memory Recall**: Ask "What do you remember about our last session?"
3.  **Visual Test**: Ask "What's on my screen right now?"
4.  **Evolution Test**: Type `/evolve` to trigger a dry run of the Neural Forge.

### Baking lessons into a local Ollama model (Neural Forge)

After you have **lessons** in `data/` and a **base** model pulled (`ollama pull …`), run from repo root: `python scripts/build_viki_model.py`. That creates an Ollama image whose default tag is **`viki-neural-forge`** (set `system.forge_output_ollama_tag` or `VIKI_FORGE_OUTPUT_OLLAMA_MODEL` to change it). Wire it up via profile **`viki-evolved`** in `viki/config/models.yaml` (`model_name` must match `ollama list`). Full steps: [README.md — Build your VIKI model](README.md#build-your-viki-model).

## Related folders in this repo

These ship beside `viki/` but are separate entry points:

- **`viki/`** — Core system including the Nexus and Cognitive Kernel.
- **`labs/security-lab/`** — Standalone FastAPI defensive lab; see [labs/security-lab/README.md](labs/security-lab/README.md).
- **`labs/qa-automation/`** — Test-framework examples (pytest, Java, Playwright, k6); see [labs/qa-automation/README.md](labs/qa-automation/README.md).

Full map: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md).

---

*Runbook version: aligned with VIKI v8.2.0 (Sovereign). Update this file when default ports, flags, or critical architecture patterns change.*
