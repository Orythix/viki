from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time

class ActionCall(BaseModel):
    """Represents a single skill execution."""
    skill_name: str = Field(..., description="The name of the skill to execute (e.g., 'research', 'system_control')")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters to pass to the skill")

class ThoughtObject(BaseModel):
    """v9: The fundamental unit of cognition, replacing raw text reasoning."""
    intent_vector: Optional[List[float]] = Field(default_factory=list, description="Semantic direction of the task")
    intent_summary: str = Field(..., description="Abstract human-readable intent")
    assumptions: List[str] = Field(default_factory=list, description="Explicit base beliefs for this task")
    constraints: List[str] = Field(default_factory=list, description="Logical and safety constraints")
    risk_score: float = Field(0.0, ge=0.0, le=1.0, description="Estimated danger (0-1)")
    primary_strategy: str = Field(..., description="The chosen path of action")
    rejected_strategies: List[str] = Field(default_factory=list, description="Alternatives considered and discarded")
    symbolic_graph: Optional[Dict[str, Any]] = None # v13 Internal Language (Nodes/Edges)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    provenance: Optional[Any] = Field(None, description="Source of the knowledge used")

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
    suggested_action: Optional[ActionCall] = None

class VIKIResponse(BaseModel):
    """v9: Final integrated response containing the judge's decision."""
    final_thought: ThoughtObject
    action: Optional[ActionCall] = Field(None)
    final_response: Optional[str] = Field(None)
    internal_metacognition: Optional[str] = Field(None, description="Layer 5: Reflection on the process")

class VIKIResponseLite(BaseModel):
    """Lightweight response for SHALLOW reasoning.
    Only 3 fields — local models produce this reliably with zero heuristic fixes."""
    final_response: str = Field(..., description="The actual textual answer to the user. Do NOT use placeholders like 'Direct response'.")
    action: Optional[ActionCall] = Field(None, description="Action to execute. MANDATORY if user asks for research, search, or system control.")
    confidence: float = Field(0.7, description="Confidence in response (0-1)")

    def to_full_response(self) -> 'VIKIResponse':
        """Convert lite response to full VIKIResponse for pipeline compatibility."""
        return VIKIResponse(
            final_thought=ThoughtObject(
                intent_summary="Shallow reasoning",
                primary_strategy=self.final_response[:100] if self.final_response else "Direct response",
                confidence=self.confidence,
            ),
            action=self.action,
            final_response=self.final_response,
            internal_metacognition="Shallow path — lite schema used."
        )

class LayerState(BaseModel):
    """v9: Telemetry for a single consciousness layer."""
    name: str
    status: str = "Idle"
    load: float = 0.0
    active_thought: Optional[ThoughtObject] = None

class WorldState(BaseModel):
    """v10: Long-term persistent world model."""
    apps: Dict[str, Any] = Field(default_factory=dict)
    workflows: List[str] = Field(default_factory=list)
    user_habits: List[str] = Field(default_factory=list)
    safety_zones: Dict[str, str] = Field(default_factory=dict)
    last_updated: float = Field(default_factory=time.time)

class TaskProgress(BaseModel):
    """Status updates during processing."""
    status: str
    message: str
