# Setting Up VIKI (v6.0.0 Sovereign)

## 📦 Prerequisites

1.  **Python 3.10+**: Ensure you have Python installed and added to PATH.
2.  **Ollama**: Install from [ollama.ai](https://ollama.ai) and pull the base models:
    ```bash
    ollama pull llama3
    ollama pull phi3
    ```
3.  **Visual Studio Build Tools** (Windows Only): Required for compiling `unsloth` dependencies if you plan to use `forge`.

## 🛠️ Environment Configuration

1.  **Clone the Repository**:
    ```powershell
    git clone https://github.com/yourusername/viki.git
    cd viki
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
    *Note: If you run into issues with `unsloth`, follow their [specific installation guide](https://github.com/unslothai/unsloth).*

4.  **Set Up Environment Variables**:
    Create a `.env` file in the root directory:
    ```env
    # Optional: For high-intelligence reasoning fallbacks
    OPENAI_API_KEY=your_key_here
    
    # Optional: For Nexus Connectivity
    DISCORD_TOKEN=your_discord_token
    TELEGRAM_TOKEN=your_telegram_token
    ```

## 🚀 Running VIKI

To start the **Sovereign Intelligence Core**:

```powershell
python viki/main.py
```

VIKI will initialize her **Nexus** and begin listening on all channels.

## 🧪 Testing

To verify key systems:

1.  **Status Check**: Type `/status` in the terminal.
2.  **Voice Test**: Ask "Can you hear me?" (if microphone is active).
3.  **Evolution Test**: Type `/evolve` to trigger a dry run of the Neural Forge.

---
**Enjoy your new digital partner.**
