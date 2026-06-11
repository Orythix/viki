import time
from typing import Any

from pydantic import BaseModel, Field


class ActionCall(BaseModel):
    """Represents a single skill execution."""

    skill_name: str = Field(
        "", description="The name of the skill to execute (e.g., 'research', 'system_control')"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Parameters to pass to the skill"
    )


class ThoughtObject(BaseModel):
    """v9: The fundamental unit of cognition, replacing raw text reasoning."""

    intent_vector: list[float] | None = Field(
        default_factory=list, description="Semantic direction of the task"
    )
    intent_summary: str = Field(..., description="Abstract human-readable intent")
    assumptions: list[str] = Field(
        default_factory=list, description="Explicit base beliefs for this task"
    )
    constraints: list[str] = Field(
        default_factory=list, description="Logical and safety constraints"
    )
    risk_score: float = Field(0.0, ge=0.0, le=1.0, description="Estimated danger (0-1)")
    primary_strategy: str = Field(..., description="The chosen path of action")
    rejected_strategies: list[str] = Field(
        default_factory=list, description="Alternatives considered and discarded"
    )
    symbolic_graph: dict[str, Any] | None = None  # v13 Internal Language (Nodes/Edges)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    provenance: Any | None = Field(None, description="Source of the knowledge used")


class ThoughtObjectLite(BaseModel):
    """Lightweight thought for SHALLOW reasoning — 3 fields instead of 10.
    Local models can reliably produce this without heuristic patching."""

    intent_summary: str = Field("Processing request", description="What the user wants")
    primary_strategy: str = Field("Direct response", description="How to address it")
    confidence: float = Field(0.7, ge=0.0, le=1.0, description="How confident (0-1)")


class SolverOutput(BaseModel):
    """v9: Output from an internal Solver (Optimistic, conservative, etc)."""

    persona: str = Field(..., description="The solver's bias (e.g., Conservative)")
    thought: ThoughtObject
    suggested_action: ActionCall | None = None


class VIKIResponse(BaseModel):
    """Final integrated response — simplified for local model reliability."""

    final_thought: ThoughtObject
    action: ActionCall | None = Field(None)
    final_response: str | None = Field(None)
    internal_metacognition: str | None = Field(None)
    ensemble_trace: dict[str, str] | None = Field(None)
    sentiment: str | None = Field(None)
    intent_type: str | None = Field(None)
    needs_escalation: bool = Field(False)


class VIKIResponseLite(BaseModel):
    """Lightweight response for SHALLOW reasoning.
    Only 3 fields — local models produce this reliably with zero heuristic fixes."""

    final_response: str | None = Field(None, description="The actual textual answer to the user.")
    action: ActionCall | None = Field(
        None,
        description="Action to execute. MANDATORY if user asks for research, search, or system control.",
    )
    confidence: float = Field(0.7, ge=0.0, le=1.0, description="Confidence in response (0-1)")

    def to_full_response(self) -> "VIKIResponse":
        """Convert lite response to full VIKIResponse for pipeline compatibility."""
        return VIKIResponse(
            final_thought=ThoughtObject(
                intent_summary="Shallow reasoning",
                primary_strategy=self.final_response[:100]
                if self.final_response
                else "Direct response",
                confidence=self.confidence,
            ),
            action=self.action,
            final_response=self.final_response,
            internal_metacognition="Shallow path — lite schema used.",
        )


class LayerState(BaseModel):
    """v9: Telemetry for a single consciousness layer."""

    name: str
    status: str = "Idle"
    load: float = 0.0
    active_thought: ThoughtObject | None = None


class WorldState(BaseModel):
    """v10: Long-term persistent world model."""

    apps: dict[str, Any] = Field(default_factory=dict)
    workflows: dict[str, Any] = Field(default_factory=dict)
    user_habits: list[dict[str, Any]] = Field(default_factory=list)
    safety_zones: dict[str, str] = Field(default_factory=dict)
    semantic_paths: dict[str, str] = Field(default_factory=dict)  # Path -> Purpose/Label
    codebase_graph: dict[str, dict[str, Any]] = Field(
        default_factory=dict
    )  # v25: File -> {dependencies, signature_hash}
    active_context: list[str] = Field(default_factory=list)  # v25: List of recently hot files
    last_updated: float = Field(default_factory=time.time)

    # v26: Autonomous Execution Context
    active_goal: str | None = None
    active_project: str | None = None
    current_phase: str | None = (
        "IDLE"  # e.g., 'IDLE', 'PLANNING', 'EXECUTING', 'TESTING', 'COMPLETE'
    )
    execution_started: bool = False
    planning_depth: int = 0  # Track consecutive planning calls for the same goal
    retry_count: int = 0
    last_phase: str | None = None


class TaskProgress(BaseModel):
    """Status updates during processing."""

    status: str
    message: str
