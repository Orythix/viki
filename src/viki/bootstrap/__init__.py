"""VIKI Bootstrap — self-installing local AI platform."""

from viki.bootstrap.dependency_manager import DependencyManager, DependencyResult
from viki.bootstrap.installer import FirstRunOrchestrator
from viki.bootstrap.model_manager import ModelManager, ModelRecommendation
from viki.bootstrap.system_detector import HardwareProfile, SystemDetector, SystemInfo
from viki.bootstrap.update_manager import UpdateManager

__all__ = [
    "SystemDetector",
    "SystemInfo",
    "HardwareProfile",
    "DependencyManager",
    "DependencyResult",
    "ModelManager",
    "ModelRecommendation",
    "FirstRunOrchestrator",
    "UpdateManager",
]
