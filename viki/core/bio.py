import cv2
import asyncio
import threading
import time
from viki.config.logger import viki_logger

class BioModule:
    """
    Bio-Adaptive Interface: Analyzes user's physiological state.
    Uses OpenCV for lightweight detection and placeholder for DeepFace.
    """
    def __init__(self):
        self.current_emotion = "neutral"
        self.is_running = False
        self._thread = None
        self.cap = None

    async def start(self):
        self.is_running = True
        viki_logger.info("BioModule: Empathy sensor active (Async Loop).")
        asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self):
        # We handle blocking cv2 calls in executor to keep one loop
        loop = asyncio.get_running_loop()
        self.cap = cv2.VideoCapture(0)
        
        while self.is_running:
            try:
                # Capture frame in executor
                ret, frame = await loop.run_in_executor(None, self.cap.read)
                if not ret: break
                
                # Placeholder for DeepFace/Analysis
                # In real use: result = await loop.run_in_executor(None, DeepFace.analyze, ...)
                
                await asyncio.sleep(10) # Heavy analysis every 10s
            except Exception as e:
                viki_logger.error(f"BioModule Error: {e}")
                break
        
        if self.cap: self.cap.release()

    def get_state(self) -> str:
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
            return ("TONE: DIRECT. User is in a hurry or stressed. "
                    "Be extremely brief. No chitchat. Action results only.")
        
        # Priority 2: Technical Tone (Coding/System)
        if task_type in ["coding", "researching", "technical"]:
            return ("TONE: TECHNICAL. Be precise, use correct terminology, "
                    "provide structured data and clear steps. Avoid fluff.")

        # Priority 3: Supportive Tone (Late night or Sadness)
        if is_late_night or bio_mood == "sad":
            return ("TONE: SUPPORTIVE & CALM. Use lower energy language. "
                    "Be warm and reassuring. Offer assistance for fatigue.")

        # Priority 4: Neutral/Balanced (Default)
        if bio_mood == "happy":
            return ("TONE: ENTHUSIASTIC. User is in a good mood. "
                    "Feel free to share insights and be slightly more chatty.")
            
        return ("TONE: NEUTRAL. Professional, warm, and efficient. "
                "Maintain a standard supportive partner persona.")

    def _update_wallpaper(self, state: str):
        """Programmatically adjust wallpaper or system color based on mood."""
        viki_logger.info(f"Subliminal UI: Adjusting desktop ambiance to match '{state}' state.")

    def stop(self):
        self.is_running = False
