"""V2 Core modules."""

from __future__ import annotations

from .agent import AgentResponse, CoreAgent
from .context_builder import ContextBuilder
from .context_manager import ContextManager
from .execution_engine import EngineReport, ExecutionEngine
from .intent_analyzer import IntentAnalyzer, IntentResult
from .permission_manager import PermissionCheck, PermissionManager, PermissionTier
from .repo_analyzer import RepoAnalyzer, RepositoryProfile
from .response_generator import ResponseGenerator
from .self_critique import CritiqueIssue, CritiqueLevel, CritiqueResult, SelfCritique
from .session_manager import Session, SessionManager, Turn
from .task_planner import ExecutionReport, StepResult, TaskPlan, TaskPlanner, TaskStep
from .tool_selector import ToolSelector

__all__ = [
    "CoreAgent",
    "AgentResponse",
    "ContextBuilder",
    "ContextManager",
    "EngineReport",
    "ExecutionEngine",
    "ExecutionReport",
    "IntentAnalyzer",
    "IntentResult",
    "PermissionManager",
    "PermissionTier",
    "PermissionCheck",
    "RepoAnalyzer",
    "RepositoryProfile",
    "ResponseGenerator",
    "SelfCritique",
    "CritiqueIssue",
    "CritiqueLevel",
    "CritiqueResult",
    "SessionManager",
    "Session",
    "StepResult",
    "Turn",
    "TaskPlanner",
    "TaskPlan",
    "TaskStep",
    "ToolSelector",
]
