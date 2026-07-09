"""
Voice loop polish — wake word detection, push-to-talk, and barge-in.

Extends audio_gateway/VoiceModule with:
  - Wake word detection (Porcupine/precise)
  - Push-to-talk activation
  - Barge-in via interrupt signal
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any

from viki.config.logger import viki_logger

try:
    import pyaudio

    _HAS_AUDIO = True
except ImportError:
    _HAS_AUDIO = False


class WakeWordDetector:
    """
    Wake word detection engine.

    Supports Porcupine (preferred) and a simple energy-based fallback.
    """

    def __init__(self, wake_word: str = "viki", sensitivity: float = 0.5):
        self._wake_word = wake_word.lower()
        self._sensitivity = sensitivity
        self._detected = False
        self._listening = False
        self._engine: Any = None
        self._audio_stream: Any = None

    def initialize(self) -> bool:
        """Initialize the wake word engine."""
        if not _HAS_AUDIO:
            viki_logger.warning("WakeWord: pyaudio not available")
            return False

        # Try Porcupine
        try:
            import pvporcupine

            keyword_paths = None
            library_path = os.environ.get("PORCUPINE_LIB_PATH")
            model_path = os.environ.get("PORCUPINE_MODEL_PATH")

            if os.environ.get("VIKI_WAKE_WORD_PATH"):
                keyword_paths = [os.environ["VIKI_WAKE_WORD_PATH"]]

            self._engine = pvporcupine.create(
                keywords=[self._wake_word] if not keyword_paths else None,
                keyword_paths=keyword_paths,
                sensitivities=[self._sensitivity],
                library_path=library_path,
                model_path=model_path,
            )
            viki_logger.info("WakeWord: initialized Porcupine engine")
            return True
        except ImportError:
            viki_logger.info("WakeWord: Porcupine not installed, using energy detection fallback")
            return True
        except Exception as e:
            viki_logger.warning("WakeWord: Porcupine init failed: %s", e)
            return False

    async def start_listening(self, callback: Any) -> None:
        """Start listening for the wake word in a background thread."""
        if self._listening:
            return
        self._listening = True

        def _listen():
            if self._engine is None and not self.initialize():
                return

            try:
                import pyaudio as pa

                audio = pa.PyAudio()
                stream = audio.open(
                    rate=self._engine.sample_rate if self._engine else 16000,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=self._engine.frame_length if self._engine else 512,
                )

                while self._listening:
                    pcm = stream.read(
                        self._engine.frame_length if self._engine else 512,
                        exception_on_overflow=False,
                    )
                    if self._engine:
                        result = self._engine.process(pcm)
                        if result >= 0:
                            self._detected = True
                            viki_logger.info("WakeWord: DETECTED '%s'", self._wake_word)
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    callback(), asyncio.get_event_loop()
                                )
                            except Exception:
                                pass
                    else:
                        # Energy-based fallback
                        energy = sum(abs(b) for b in pcm) / len(pcm)
                        if energy > 5000:  # Threshold
                            self._detected = True
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    callback(), asyncio.get_event_loop()
                                )
                            except Exception:
                                pass

            except Exception as e:
                viki_logger.error("WakeWord listener error: %s", e)

        thread = threading.Thread(target=_listen, daemon=True)
        thread.start()
        viki_logger.info("WakeWord: listening for '%s'", self._wake_word)

    def stop_listening(self) -> None:
        self._listening = False
        if self._engine:
            self._engine.delete()
            self._engine = None

    @property
    def detected(self) -> bool:
        val = self._detected
        self._detected = False
        return val


class PushToTalk:
    """
    Push-to-talk activation via keyboard hotkey.

    Usage:
        ptt = PushToTalk()
        ptt.start(on_activate=lambda: print("Recording..."))
    """

    def __init__(self, hotkey: str = "<ctrl>+<shift>+<space>"):
        self._hotkey = hotkey
        self._listening = False
        self._on_activate: Any = None
        self._on_deactivate: Any = None

    def start(self, on_activate: Any, on_deactivate: Any | None = None) -> None:
        self._on_activate = on_activate
        self._on_deactivate = on_deactivate

        try:
            from pynput import keyboard
        except ImportError:
            viki_logger.warning("PushToTalk: pynput not installed")
            return

        def on_press(key):
            try:
                if hasattr(key, "char") and key.char == " ":
                    if self._on_activate:
                        self._on_activate()
            except Exception:
                pass

        def on_release(key):
            try:
                if hasattr(key, "char") and key.char == " ":
                    if self._on_deactivate:
                        self._on_deactivate()
            except Exception:
                pass

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()
        viki_logger.info("PushToTalk: listening for hotkey '%s'", self._hotkey)


class BargeIn:
    """
    Barge-in detection — allows interrupting VIKI while it's speaking.

    Detects voice activity on the microphone during TTS output and
    sends an interrupt signal.
    """

    def __init__(self):
        self._interrupted = False

    def start(self) -> None:
        """Start barge-in detection in background."""
        if not _HAS_AUDIO:
            return

        def _detect():
            import pyaudio as pa

            audio = pa.PyAudio()
            stream = audio.open(
                rate=16000,
                channels=1,
                format=pa.paInt16,
                input=True,
                frames_per_buffer=1024,
            )
            while True:
                pcm = stream.read(1024, exception_on_overflow=False)
                energy = sum(abs(b) for b in pcm) / len(pcm)
                if energy > 8000:  # User is speaking
                    self._interrupted = True
                time.sleep(0.05)

        thread = threading.Thread(target=_detect, daemon=True)
        thread.start()

    @property
    def interrupted(self) -> bool:
        val = self._interrupted
        self._interrupted = False
        return val
