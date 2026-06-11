import asyncio
import os
from typing import Any

from viki.config.logger import viki_logger

_np = None
_sd = None


def _get_np():
    global _np
    if _np is None:
        try:
            import numpy as np_mod

            _np = np_mod
        except Exception as e:
            viki_logger.warning(f"NumPy unavailable ({e}). Voice sonar disabled.")
    return _np


def _get_sd():
    global _sd
    if _sd is None:
        voice_enabled = os.getenv("VIKI_VOICE_ENABLED", "1").lower() in ("1", "true", "yes")
        if not voice_enabled:
            return None
        try:
            import sounddevice as sd_mod

            _sd = sd_mod
        except Exception as e:
            viki_logger.warning(f"sounddevice unavailable ({e}). Voice sonar disabled.")
    return _sd


class VoiceModule:
    """
    Handles Voice Activity Detection (VAD) and Ambient Sonar.
    Detects room "vibe" (typing vs silence vs noise).
    """

    def __init__(self, sampling_rate=16000):
        self.sampling_rate = sampling_rate
        self.silent_mode = False
        self.volume_boost = 1.0
        self.model = None
        self.utils = None

        # We start VAD loading in a non-blocking way or lazy load it
        # For now, let's lazy load it on first use or in a background task
        # But to keep latency low, we should load it at start but handle failures gracefully
        # To fix the immediate "heavy import" issue, we remove the top-level import

    async def initialize(self):
        """Async initialization to load heavy models."""
        try:
            viki_logger.info("VoiceModule: Loading Silero VAD model...")
            # We run this in a thread to avoid blocking the event loop
            await asyncio.to_thread(self._load_model)
        except Exception as e:
            viki_logger.error(f"Failed to load VAD model: {e}")
            self.model = None

    def _load_model(self):
        import torch

        # Use CPU by default to avoid GPU usage; set VIKI_VAD_GPU=1 to use GPU
        device = (
            "cuda"
            if (__import__("os").getenv("VIKI_VAD_GPU", "").lower() in ("1", "true", "yes"))
            else "cpu"
        )
        self.model, self.utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
        self.model = self.model.to(device)
        (self.get_speech_timestamps, _, self.read_audio, _, _) = self.utils
        self._vad_device = device
        viki_logger.info("Silero VAD model loaded successfully (device=%s).", device)

    async def start_sonar(self):
        """
        Background loop to detect ambient environment and tune VAD.
        Logic: threshold = base_noise_floor + 0.2
        Goal: No false positives from air conditioning.
        """
        sd_mod = _get_sd()
        np_mod = _get_np()
        if np_mod is None or sd_mod is None:
            viki_logger.warning(
                "VoiceModule: Ambient sonar disabled because NumPy or sounddevice is unavailable."
            )
            return
        if not self.model:
            await self.initialize()

        viki_logger.info("VoiceModule: Ambient Sonar engaged. Calibrating noise floor...")

        while True:
            try:
                # Sample 0.5s of audio to gauge noise floor
                # We do this in a thread to avoid blocking the loop
                duration = 0.5
                recording = await asyncio.to_thread(
                    lambda dur=duration: sd_mod.rec(
                        int(dur * self.sampling_rate),
                        samplerate=self.sampling_rate,
                        channels=1,
                        blocking=True,
                    )
                )
                sd_mod.wait()

                # Calculate RMS (Root Mean Square) Amplitude
                rms = np_mod.sqrt(np_mod.mean(recording**2))
                self.base_noise_floor = float(rms)

                # Dynamic Thresholding Formula
                # Clamp between 0.4 and 0.95 to be safe
                raw_threshold = self.base_noise_floor + 0.2
                self.vad_threshold = max(0.4, min(raw_threshold, 0.95))

                # viki_logger.debug(f"Sonar: Noise Floor={self.base_noise_floor:.4f} | VAD Threshold={self.vad_threshold:.2f}")

            except Exception as e:
                viki_logger.warning(f"Sonar glitch: {e}")

            await asyncio.sleep(10)  # Re-calibrate every 10 seconds

    def is_speech(self, audio_chunk: Any) -> bool:
        if self.model is None:
            return False
        if _get_np() is None:
            return False

        threshold = getattr(self, "vad_threshold", 0.5)

        import torch

        device = getattr(self, "_vad_device", "cpu")
        tensor_audio = torch.from_numpy(audio_chunk).float().to(device)
        with torch.no_grad():
            speech_prob = self.model(tensor_audio, self.sampling_rate).item()

        return speech_prob > threshold

    async def listen_for_interruption(self, stop_event: asyncio.Event):
        sd_mod = _get_sd()
        np_mod = _get_np()
        if np_mod is None or sd_mod is None:
            viki_logger.warning(
                "VoiceModule: Interruption listener disabled because NumPy or sounddevice is unavailable."
            )
            return
        if not self.model:
            await self.initialize()

        viki_logger.info("VoiceModule: Ears open for interruption...")

        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status):
            if status:
                viki_logger.warning(f"Audio status: {status}")

            if stop_event.is_set():
                raise sd_mod.CallbackStop()

            if self.is_speech(indata[:, 0]):
                loop.call_soon_threadsafe(stop_event.set)

        try:
            with sd_mod.InputStream(
                samplerate=self.sampling_rate, channels=1, callback=callback, blocksize=512
            ):
                await stop_event.wait()
        except Exception as e:
            viki_logger.error(f"Interruption listener died: {e}")

    async def speak(self, text: str, interruption_event: asyncio.Event = None):
        """
        Streaming TTS Output with Instant Brake.
        """
        viki_logger.info(f"Speaking: {text[:30]}...")

        # Simulate processing chunks (words/sentences)
        words = text.split()
        for word in words:
            if interruption_event and interruption_event.is_set():
                viki_logger.warning("VoiceModule: Speech Aborted (Brake Active)!")
                # Here we would kill the TTS subprocess:
                # subprocess.kill(self.tts_process)
                break

            # Simulate TTS generated chunk duration
            await asyncio.sleep(0.1 + (len(word) * 0.02))
            # In real impl, we would play audio chunk here


class AudioVisualizer:
    """Helper to visualize audio intensity (ASCII)"""

    @staticmethod
    def render(rms: float, width: int = 20):
        bars = int(min(rms * 100, 1.0) * width)
        return "[" + "|" * bars + " " * (width - bars) + "]"
