import os
import pyttsx3
import asyncio
from typing import Dict, Any, Optional
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class VoiceSkill(BaseSkill):
    """
    Text-to-Speech: pyttsx3 (default) or ElevenLabs when voice.backend=elevenlabs and API key set.
    """
    def __init__(self, voice_module=None, controller=None):
        self._name = "voice"
        self._description = "Speak text out loud (pyttsx3 or ElevenLabs when configured)."
        self.voice_module = voice_module
        self._controller = controller
        self.engine = None
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 170)
            self.engine.setProperty('volume', 0.9)
        except Exception as e:
            viki_logger.debug(f"TTS pyttsx3 init: {e}")

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to speak out loud."
                }
            },
            "required": ["text"]
        }

    def _use_elevenlabs(self) -> bool:
        if not self._controller:
            return False
        backend = (self._controller.settings.get("voice") or {}).get("backend", "pyttsx3")
        if backend != "elevenlabs":
            return False
        return bool(os.environ.get("VIKI_ELEVENLABS_API_KEY"))

    async def execute(self, params: Dict[str, Any]) -> str:
        text = params.get('text')
        if not text:
            return "Error: No 'text' provided to speak."

        if self._use_elevenlabs():
            api_key = os.environ.get("VIKI_ELEVENLABS_API_KEY")
            voice_id = (self._controller.settings.get("voice") or {}).get("voice_id") or os.environ.get("VIKI_ELEVENLABS_VOICE_ID")
            try:
                from viki.core.tts_backends import speak_elevenlabs
                result = await asyncio.to_thread(speak_elevenlabs, text, api_key, voice_id)
                if result == "OK":
                    return f"Spoken (ElevenLabs): {text}"
                return f"Voice Error: {result}"
            except Exception as e:
                return f"Voice Error: {e}"

        if not self.engine:
            return "Error: TTS engine not initialized (install pyttsx3 or set voice.backend=elevenlabs and VIKI_ELEVENLABS_API_KEY)."

        try:
            viki_logger.info(f"Speaking: {text}")
            stop_event = asyncio.Event()
            tts_task = asyncio.to_thread(self._say_managed, text, stop_event)
            if self.voice_module:
                vad_task = asyncio.create_task(self.voice_module.listen_for_interruption(stop_event))
                done, pending = await asyncio.wait([tts_task, vad_task], return_when=asyncio.FIRST_COMPLETED)
                if stop_event.is_set():
                    self.engine.stop()
                    return f"Spoken (Interrupted): {text}"
                stop_event.set()
                await vad_task
            else:
                await tts_task
            return f"Spoken: {text}"
        except Exception as e:
            viki_logger.error(f"Voice execution error: {e}")
            return f"Voice Error: {str(e)}"

    def _say_managed(self, text: str, stop_event: asyncio.Event):
        # pyttsx3 check for stop is not great inside runAndWait,
        # but we can try to call self.engine.stop() from outside.
        self.engine.say(text)
        self.engine.runAndWait()
