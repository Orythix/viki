import numpy as np
import sounddevice as sd
import asyncio
from viki.config.logger import viki_logger

# Lazy import torch only when needed

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
            import torch
            viki_logger.info("VoiceModule: Loading Silero VAD model...")
            # We run this in a thread to avoid blocking the event loop
            await asyncio.to_thread(self._load_model)
        except Exception as e:
            viki_logger.error(f"Failed to load VAD model: {e}")
            self.model = None

    def _load_model(self):
        import torch
        self.model, self.utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                                model='silero_vad',
                                                force_reload=False)
        (self.get_speech_timestamps, _, self.read_audio, _, _) = self.utils
        viki_logger.info("Silero VAD model loaded successfully.")

    async def start_sonar(self):
        """
        Background loop to detect ambient environment and tune VAD.
        Logic: threshold = base_noise_floor + 0.2
        Goal: No false positives from air conditioning.
        """
        if not self.model: await self.initialize()
        
        viki_logger.info("VoiceModule: Ambient Sonar engaged. Calibrating noise floor...")
        
        while True:
            try:
                # Sample 0.5s of audio to gauge noise floor
                # We do this in a thread to avoid blocking the loop
                duration = 0.5
                recording = await asyncio.to_thread(
                    lambda: sd.rec(int(duration * self.sampling_rate), samplerate=self.sampling_rate, channels=1, blocking=True)
                )
                sd.wait() # Ensure recording is finished if not blocking? (blocking=True handles it)
                
                # Calculate RMS (Root Mean Square) Amplitude
                rms = np.sqrt(np.mean(recording**2))
                self.base_noise_floor = float(rms)
                
                # Dynamic Thresholding Formula
                # Clamp between 0.4 and 0.95 to be safe
                raw_threshold = self.base_noise_floor + 0.2
                self.vad_threshold = max(0.4, min(raw_threshold, 0.95))
                
                # viki_logger.debug(f"Sonar: Noise Floor={self.base_noise_floor:.4f} | VAD Threshold={self.vad_threshold:.2f}")
                
            except Exception as e:
                viki_logger.warning(f"Sonar glitch: {e}")
                
            await asyncio.sleep(10) # Re-calibrate every 10 seconds

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        if self.model is None: return False
        
        # Ensure we have a valid threshold
        threshold = getattr(self, 'vad_threshold', 0.5)
        
        import torch
        # Silero expects float32 tensor
        tensor_audio = torch.from_numpy(audio_chunk).float()
        
        with torch.no_grad():
            speech_prob = self.model(tensor_audio, self.sampling_rate).item()
            
        return speech_prob > threshold

    async def listen_for_interruption(self, stop_event: asyncio.Event):
        """
        Ultra-low latency listener.
        Runs concurrently with TTS. If speech detected -> stop_event.set()
        """
        if not self.model: await self.initialize()
        
        viki_logger.info("VoiceModule: Ears open for interruption...")

        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status):
            if status:
                viki_logger.warning(f"Audio status: {status}")
            
            if stop_event.is_set():
                raise sd.CallbackStop()

            # Check for speech
            # We use the dynamic threshold from is_speech
            if self.is_speech(indata[:, 0]):
                # viki_logger.info("INTERRUPTION DETECTED")
                loop.call_soon_threadsafe(stop_event.set)

        try:
            # Blocksize 512 samples (~30ms) is optimal for Silero
            # 256 might be too small for the model's window, 512 is standard
            with sd.InputStream(samplerate=self.sampling_rate, channels=1, callback=callback, blocksize=512):
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
