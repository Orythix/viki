"""
Shared embedding model for semantic memory and narrative.
Loads SentenceTransformer once on first use and reuses across LearningModule and NarrativeMemory.
"""
import os
from typing import Any, Optional

from viki.config.logger import viki_logger

_encoder: Any = None


def get_encoder():
    """Return the shared SentenceTransformer encoder, lazily loaded on first use."""
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        from sentence_transformers import SentenceTransformer
        _device = "cuda" if (os.getenv("VIKI_EMBED_GPU", "").lower() in ("1", "true", "yes")) else "cpu"
        _encoder = SentenceTransformer("all-MiniLM-L6-v2", device=_device)
        return _encoder
    except Exception as e:
        viki_logger.warning(f"Shared embedding model unavailable ({e}). Semantic features will use keyword fallback.")
        return None
