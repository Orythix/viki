import os
import warnings
from typing import Any

from dotenv import load_dotenv

# Aggressively suppress HuggingFace and Transformers noise
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", module="sentence_transformers")
warnings.filterwarnings("ignore", module="transformers")

load_dotenv()

# Lazy-loaded modules
_VIKIController: Any = None
_viki_logger: Any = None
_get_soul_path: Any = None
_Container: Any = None
_run_onboarding: Any = None


def _lazy_load_core():
    global _VIKIController, _viki_logger, _get_soul_path, _Container, _run_onboarding
    if _VIKIController is None:
        from viki.config.logger import viki_logger as _viki_logger
        from viki.config.resolve import get_soul_path as _get_soul_path
        from viki.core.orchestrator import VIKIController as _VIKIController
        from viki.core.utils.onboarding import run_onboarding as _run_onboarding
        from viki.service_registry import Container as _Container
