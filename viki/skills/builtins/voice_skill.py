import pyttsx3
import asyncio
from typing import Dict, Any, Optional
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class VoiceSkill(BaseSkill):
    """
    Text-to-Speech capability for VIKI with Voice Activity Detection (VAD) interruption.
    """
    def __init__(self, voice_module=None):
        self._name = "voice"
        self._description = "Speak text out loud. Supports interruption by human speech."
        self.voice_module = voice_module
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 170)
            self.engine.setProperty('volume', 0.9)
        except Exception as e:
            viki_logger.error(f"TTS init error: {e}")
            self.engine = None

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

    async def execute(self, params: Dict[str, Any]) -> str:
        if not self.engine:
            return "Error: TTS engine not initialized."
        
        text = params.get('text')
        if not text:
            return "Error: No 'text' provided to speak."

        try:
            viki_logger.info(f"Speaking: {text}")
            
            # 1. Create Interruption Event
            stop_event = asyncio.Event()
            
            # 2. Run TTS and VAD in parallel
            # Since pyttsx3 is blocking, we run it in a thread.
            # We track the status to see if it was interrupted.
            
            tts_task = asyncio.to_thread(self._say_managed, text, stop_event)
            
            if self.voice_module:
                vad_task = asyncio.create_task(self.voice_module.listen_for_interruption(stop_event))
                
                # Wait for TTS to finish or VAD to trigger
                done, pending = await asyncio.wait(
                    [tts_task, vad_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                if stop_event.is_set():
                    viki_logger.info("Speech interrupted by user.")
                    self.engine.stop()
                    return f"Spoken (Interrupted): {text}"
                
                # Cleanup VAD if TTS finished first
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
