# Architecture Refactoring Plan

**Last updated:** 2026-02-17

## Overview
The VIKI controller currently exhibits a "God Object" anti-pattern with 30+ responsibilities and tight coupling through service locator pattern. This document outlines the refactoring strategy (roadmap; implementation is incremental).

## Current Issues

### 1. God Object Pattern
**File:** `viki/core/controller.py` (800+ lines)

**Problems:**
- Single class instantiates 30+ subsystems
- Registers 25+ skills
- 380-line `process_request()` method
- Hard to test, modify, or understand
- Changes ripple unpredictably

### 2. Service Locator Pattern
**Problem:** 12+ modules receive full `controller` and access internals:
```python
# Current (BAD)
MessagingNexus(controller)  # Has access to everything
ResearchSkill(controller)   # Can reach into any attribute

# Desired (GOOD)
MessagingNexus(request_processor=processor)
ResearchSkill(learning=learning, model_router=router)
```

**Affected Modules:**
- MessagingNexus
- MissionControl
- DreamModule
- WatchdogModule, WellnessPulse
- ReflectorModule
- ResearchSkill, SwarmSkill, RecallSkill, SfsSkill, ShortVideoSkill, ModelForgeSkill

## Proposed Solution

### Phase 1: Request Pipeline (2-3 days)

Extract `process_request()` into a pipeline of focused stages:

```python
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass
class RequestContext:
    """Encapsulates all context for a request."""
    raw_input: str
    safe_input: str
    narrative_wisdom: List[Dict]
    memory_context: Dict[str, Any]
    world_context: str
    signals_context: str
    evolution_log: str
    action_results: List[Dict]
    use_lite: bool = False

class RequestPipeline:
    """Orchestrates request processing through stages."""
    
    def __init__(self, stages: List[Stage]):
        self.stages = stages
    
    async def process(self, user_input: str) -> str:
        context = RequestContext(raw_input=user_input)
        
        for stage in self.stages:
            context = await stage.execute(context)
            if stage.should_halt(context):
                return stage.get_response(context)
        
        return context.final_response

# Stages
class GovernorStage(Stage):
    """Ethical veto check."""
    pass

class SafetyStage(Stage):
    """Input validation and sanitization."""
    pass

class ReflexStage(Stage):
    """Fast path for cached/learned patterns."""
    pass

class MemoryStage(Stage):
    """Fetch relevant context."""
    pass

class JudgmentStage(Stage):
    """Route to SHALLOW vs DEEP."""
    pass

class CortexStage(Stage):
    """LLM deliberation."""
    pass

class ActionStage(Stage):
    """Execute skills with safety checks."""
    pass

class RecordStage(Stage):
    """Memory reinforcement."""
    pass
```

### Phase 2: Dependency Injection (2-3 days)

Replace controller injection with narrow interfaces:

```python
from abc import ABC, abstractmethod

class LLMClient(ABC):
    """Narrow interface for LLM operations."""
    @abstractmethod
    async def chat(self, messages: List[Dict], model: str = None) -> str:
        pass
    
    @abstractmethod
    async def chat_structured(self, messages: List[Dict], schema: Type[T]) -> T:
        pass

class LearningProvider(ABC):
    """Interface for learning operations."""
    @abstractmethod
    def save_lesson(self, trigger: str, fact: str, source: str):
        pass
    
    @abstractmethod
    def get_relevant_lessons(self, query: str) -> List[Dict]:
        pass

# Updated skill signature
class ResearchSkill(BaseSkill):
    def __init__(self, learning: LearningProvider, llm: LLMClient):
        self.learning = learning
        self.llm = llm
```

### Phase 3: Skill Registration (1 day)

Move skill registration out of controller:

```python
# viki/core/skill_bootstrap.py
from dataclasses import dataclass

@dataclass
class SkillDependencies:
    """Container for common skill dependencies."""
    learning: LearningProvider
    llm_client: LLMClient
    voice_module: VoiceModule
    settings: Dict[str, Any]

def register_default_skills(registry: SkillRegistry, deps: SkillDependencies):
    """Register all built-in skills."""
    registry.register_skill(TimeSkill())
    registry.register_skill(MathSkill())
    registry.register_skill(ResearchSkill(deps.learning, deps.llm_client))
    registry.register_skill(VoiceSkill(deps.voice_module))
    # ... etc
    
    # Aliases
    registry.alias('search', 'research')
    registry.alias('google', 'research')
```

### Phase 4: Controller Cleanup (1 day)

Slim down controller to orchestration only:

```python
class VIKIController:
    """Lightweight orchestration layer."""
    
    def __init__(self, settings_path: str, soul_path: str):
        # Load configs
        self.settings = self._load_yaml(settings_path)
        self.soul = Soul(soul_path)
        
        # Core services
        self.model_router = ModelRouter(...)
        self.safety = SafetyLayer(...)
        self.memory = HierarchicalMemory(...)
        
        # Build pipeline
        self.pipeline = self._build_pipeline()
    
    def _build_pipeline(self) -> RequestPipeline:
        """Construct the request processing pipeline."""
        return RequestPipeline([
            GovernorStage(self.governor),
            SafetyStage(self.safety),
            ReflexStage(self.reflex),
            MemoryStage(self.memory),
            JudgmentStage(self.judgment),
            CortexStage(self.cortex),
            ActionStage(self.skill_registry, self.capabilities, self.safety),
            RecordStage(self.memory, self.evolution),
        ])
    
    async def process_request(self, user_input: str) -> str:
        """Process a user request through the pipeline."""
        return await self.pipeline.process(user_input)
```

## Implementation Priority

1. **Week 1:** Create RequestContext and Stage abstractions
2. **Week 2:** Extract GovernorStage, SafetyStage, ReflexStage
3. **Week 3:** Extract remaining stages, test integration
4. **Week 4:** Define interfaces (LLMClient, LearningProvider, etc.)
5. **Week 5:** Update skills to use interfaces instead of controller
6. **Week 6:** Move skill registration to bootstrap module
7. **Week 7:** Clean up controller, remove dead code

## Migration Strategy

- **Incremental:** Refactor one stage at a time
- **Backward Compatible:** Keep old code paths working during transition
- **Test Coverage:** Write integration tests for each stage
- **Feature Flags:** Use flags to toggle between old/new implementations

## Success Metrics

- Controller reduced from 800+ lines to <200 lines
- Each stage is <100 lines, single responsibility
- Skills have explicit dependencies (no controller injection)
- Test coverage >60%
- No regression in functionality

## Notes

- This is a LARGE refactoring (4-6 weeks)
- Benefits: Testability, maintainability, clarity
- Risk: Breaking existing functionality
- Recommendation: Do after critical bugs are fixed (DONE!)
