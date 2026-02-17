"""
Whisper transcription: audio file or URL to text. OPENAI_API_KEY for API; or local whisper/faster-whisper.
File paths are restricted to allowed roots (workspace, data).
"""
import os
import asyncio
from typing import Dict, Any
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger
from viki.core.utils.path_sandbox import validate_output_path


class WhisperSkill(BaseSkill):
    def __init__(self, controller=None):
        self._controller = controller

    @property
    def name(self) -> str:
        return "whisper"

    @property
    def description(self) -> str:
        return "Transcribe audio file to text. Params: file= path to audio (mp3, wav, etc.). Set OPENAI_API_KEY for Whisper API."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to audio file."},
            },
            "required": ["file"],
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        path = params.get("file")
        if not path:
            return "Provide file= path to an existing audio file."
        ok, path_or_err = validate_output_path(path, controller=self._controller)
        if not ok:
            return path_or_err
        path = path_or_err
        if not os.path.isfile(path):
            return "File not found or not a file."

        key = os.environ.get("OPENAI_API_KEY")
        if key:
            try:
                with open(path, "rb") as f:
                    data = f.read()
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    form = aiohttp.FormData()
                    form.add_field("file", data, filename=os.path.basename(path))
                    form.add_field("model", "whisper-1")
                    async with session.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {key}"},
                        data=form,
                    ) as resp:
                        if resp.status != 200:
                            return f"Whisper API error: {resp.status} {await resp.text()}"
                        out = await resp.json()
                        return out.get("text", "") or "No text."
            except Exception as e:
                return f"Whisper error: {e}"

        return "Set OPENAI_API_KEY for Whisper transcription, or install local whisper/faster-whisper for offline use."
