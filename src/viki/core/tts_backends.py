"""
TTS backends: pyttsx3 (default) and ElevenLabs (optional).
VoiceSkill selects backend from settings voice.backend and voice.voice_id.
"""
import os
import asyncio
from typing import Optional
from viki.config.logger import viki_logger

def speak_elevenlabs(text: str, api_key: str, voice_id: Optional[str] = None) -> str:
    """Synthesize speech via ElevenLabs API and play (blocking). Returns error message or 'OK'."""
    try:
        import requests
        voice_id = voice_id or os.environ.get("VIKI_ELEVENLABS_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        data = {"text": text[:5000]}
        r = requests.post(url, json=data, headers=headers, timeout=30)
        if r.status_code != 200:
            return f"ElevenLabs API error: {r.status_code} {r.text[:200]}"
        # Play audio: write to temp file and play (platform-dependent)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(r.content)
            path = f.name
        try:
            import subprocess
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.run(["mpv", path, "--no-video"], capture_output=True, timeout=60)
        except Exception as e:
            viki_logger.debug("TTS play audio: %s", e)
        try:
            os.unlink(path)
        except Exception as e:
            viki_logger.debug("TTS unlink temp file: %s", e)
        return "OK"
    except Exception as e:
        return f"ElevenLabs error: {e}"
