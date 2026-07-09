import asyncio
import sys
import time
from typing import Any

from viki.config.logger import viki_logger

_cv2 = None


def _opencv_silence_msmf():
    """Reduce OpenCV stderr spam when no camera is available (common on Windows MSMF)."""
    if _cv2 is None:
        return
    try:
        _cv2.utils.logging.setLogLevel(_cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        pass


def _get_cv2():
    global _cv2
    if _cv2 is None:
        try:
            import cv2

            _cv2 = cv2
            _opencv_silence_msmf()
        except Exception as e:
            viki_logger.warning(f"OpenCV unavailable ({e}). Bio sensing disabled.")
    return _cv2


class BioModule:
    """
    Bio-Adaptive Interface: Analyzes user's physiological state.

    P2 hardening:
    - Webcam + analysis are EXPERIMENTAL by default. Enable with one of:
        * `system.bio_webcam_enabled: true`
        * env `VIKI_BIO_WEBCAM=1`
      The legacy stub never actually classified emotion; the `experimental`
      flag below makes that explicit and gates real backends.
    - Real DeepFace path is opt-in via `bio_backend: deepface` (env
      `VIKI_BIO_BACKEND=deepface`); falls back to the experimental stub if
      DeepFace isn't installed.
    - ONNX backend slot exists for future low-dependency models.
    """

    EXPERIMENTAL_NOTICE = "BioModule: bio sensing is experimental; emotion stays 'neutral' unless a real backend is loaded."

    def __init__(
        self,
        webcam_enabled: bool = False,
        backend: str = "stub",
        analysis_interval_s: float = 10.0,
    ):
        self.webcam_enabled = bool(webcam_enabled)
        self.backend = (backend or "stub").lower()
        self.analysis_interval_s = max(1.0, float(analysis_interval_s))
        self.current_emotion = "neutral"
        self.experimental = self.backend == "stub"
        self.is_running = False
        self._thread = None
        self.cap: Any = None
        self._monitor_task: asyncio.Task | None = None
        self._deepface: Any = None
        self._deepface_load_failed = False

    async def start(self):
        if not self.webcam_enabled:
            viki_logger.debug(
                "BioModule: Webcam sensor off (set system.bio_webcam_enabled: true or VIKI_BIO_WEBCAM=1 to enable)."
            )
            return
        if _get_cv2() is None:
            viki_logger.warning("BioModule: Empathy sensor disabled because OpenCV is unavailable.")
            return
        self.is_running = True
        if self.experimental:
            viki_logger.info(self.EXPERIMENTAL_NOTICE)
        else:
            viki_logger.info("BioModule: Empathy sensor active (backend=%s).", self.backend)
        # Store the task so it doesn't get garbage-collected and so we can stop it cleanly.
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        await asyncio.sleep(0)  # Yield control to the event loop.

    def _open_capture(self):
        """Open default camera; prefer DirectShow on Windows to reduce MSMF failures."""
        cv2_mod = _get_cv2()
        if cv2_mod is None:
            return None
        if sys.platform == "win32":
            try:
                cap = cv2_mod.VideoCapture(0, cv2_mod.CAP_DSHOW)
            except TypeError:
                cap = cv2_mod.VideoCapture(0)
            if cap.isOpened():
                return cap
            try:
                cap.release()
            except Exception:
                pass
        cap = cv2_mod.VideoCapture(0)
        return cap if cap.isOpened() else None

    async def _monitor_loop(self):
        if _get_cv2() is None:
            return
        loop = asyncio.get_running_loop()
        self.cap = await loop.run_in_executor(None, self._open_capture)
        if not self.cap:
            viki_logger.info(
                "BioModule: No webcam available or access denied; empathy loop stopped. "
                "Disable bio_webcam if you do not need camera-based tone hints."
            )
            self.is_running = False
            return

        while self.is_running:
            try:
                ret, frame = await loop.run_in_executor(None, self.cap.read)
                if not ret:
                    break
                if self.backend == "deepface":
                    self.current_emotion = await loop.run_in_executor(
                        None, self._analyze_deepface, frame
                    )
                await asyncio.sleep(self.analysis_interval_s)
            except Exception as e:
                viki_logger.error(f"BioModule Error: {e}")
                break

        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def get_state(self) -> str:
        return self.current_emotion

    def _analyze_deepface(self, frame) -> str:
        """Real DeepFace path. Lazy-loads the package and falls back to 'neutral' on errors."""
        if self._deepface_load_failed:
            return self.current_emotion
        if self._deepface is None:
            try:
                from deepface import DeepFace

                self._deepface = DeepFace
            except Exception as e:
                self._deepface_load_failed = True
                viki_logger.warning(
                    "BioModule: DeepFace unavailable (%s); reverting to 'neutral'.", e
                )
                return "neutral"
        try:
            result = self._deepface.analyze(
                frame,
                actions=["emotion"],
                enforce_detection=False,
                silent=True,
            )
            payload = result[0] if isinstance(result, list) else result
            dominant = payload.get("dominant_emotion") or payload.get("emotion") or "neutral"
            return str(dominant)
        except Exception as e:
            viki_logger.debug("BioModule: DeepFace analyze failed: %s", e)
            return self.current_emotion

    def select_tone(self, user_input: str, task_type: str) -> str:
        """
        Tone Selector Layer: Decides on the optimal communication style.
        Factors: Input Sentiment, Task Type, Time of Day, Physiological State (Bio).
        """
        # 1. Base Mood from Sensors
        bio_mood = self.current_emotion

        # 2. Stress Detection (Heuristics)
        is_shouting = user_input.isupper() and len(user_input) > 5
        urgency_keywords = ["urgent", "asap", "fast", "emergency", "immediately", "quick"]
        is_hurrying = any(k in user_input.lower() for k in urgency_keywords)

        # 3. Time of Day Context
        current_hour = time.localtime().tm_hour
        is_late_night = current_hour < 6 or current_hour > 22

        # --- LOGIC ENGINE ---

        # Priority 1: Direct Tone (Shouting or Urgency)
        if is_shouting or is_hurrying:
            return (
                "TONE: DIRECT. User is in a hurry or stressed. "
                "Be extremely brief. No chitchat. Action results only."
            )

        # Priority 2: Technical Tone (Coding/System)
        if task_type in ["coding", "researching", "technical"]:
            return (
                "TONE: TECHNICAL. Be precise, use correct terminology, "
                "provide structured data and clear steps. Avoid fluff."
            )

        # Priority 3: Supportive Tone (Late night or Sadness)
        if is_late_night or bio_mood == "sad":
            return (
                "TONE: SUPPORTIVE & CALM. Use lower energy language. "
                "Be warm and reassuring. Offer assistance for fatigue."
            )

        # Priority 4: Neutral/Balanced (Default)
        if bio_mood == "happy":
            return (
                "TONE: ENTHUSIASTIC. User is in a good mood. "
                "Feel free to share insights and be slightly more chatty."
            )

        return (
            "TONE: NEUTRAL. Professional, warm, and efficient. "
            "Maintain a standard supportive partner persona."
        )

    def _update_wallpaper(self, state: str):
        """Programmatically adjust wallpaper or system color based on mood."""
        viki_logger.info(f"Subliminal UI: Adjusting desktop ambiance to match '{state}' state.")

    def stop(self):
        self.is_running = False
        if self._monitor_task is not None and not self._monitor_task.done():
            self._monitor_task.cancel()
        self._monitor_task = None
