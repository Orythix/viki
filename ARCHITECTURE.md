# VIKI Architecture (v7.2.0 Cortex)

## Core Philosophy
Following the **Cortex Upgrade**, VIKI follows a "Professional Intelligence" design pattern:
1.  **Priority-Based Ingress (The One True Event Loop)**: All IO (Terminal, Discord, Telegram, Voice) is funneled into a single `asyncio.PriorityQueue`. Urgent user inputs are prioritized over background proactive suggestions.
2.  **Polymorphic Intelligence**: Cognition is split into three tiers:
    *   **Reflex**: High-speed intent detection (Regex + Phi-3).
    *   **Chatter**: Natural conversational flow (Llama 3).
    *   **Planning**: Multi-step task solving and tool use (DeepSeek R1).
3.  **Model Routing**: `get_model()` uses config priority, latency penalty for fast responses, and error-rate penalty; all LLM calls record performance for adaptive routing.
4.  **Autonomous Safety**: All actions pass through a **Safety Envelope** that enforces tiered authorization (Safe/Medium/Destructive). Reflex path runs the full security pipeline.
5.  **Mistake Prevention**: A **Failure Memory** layer records unsuccessful attempts; **relevant failures** are injected into deliberation context. Reflex failures call `reflex.report_failure()`.
6.  **Continuous Learning**: Session analysis on shutdown, knowledge-gap–driven dream research, optional continuous training cycles, and LoRA/export for external training.

## Module Breakdown

### 1. The Controller (`viki/core/controller.py`)
*   **Role**: Central Processing Unit.
*   **Function**: Manages the "Think-Action-Learn" loop with integrated **Latency Budgeting** to maintain system responsiveness during high-complexity tasks.

### 2. The Nexus (`viki/api/nexus.py`)
*   **Role**: Priority Dispatcher.
*   **Function**: Aggregates inputs into a single `PriorityQueue`. Implements explicit task cancellation and lifecycle management for background processes.

### 3. Safety Layer (`viki/core/safety.py`)
*   **Role**: Executive Constraint.
*   **Function**: Classifies tool calls based on risk. Intercepts "Medium" and "Destructive" actions for mandatory user confirmation (`/confirm`).

### 4. Learning & Failure Memory (`viki/core/learning.py`)
*   **Role**: Long-Term Stability (SQLite v3).
*   **Function**: Houses both **Semantic Lessons** (facts) and **Failure Logs** in a unified SQLite database. Uses semantic search to retrieve relevant past errors before planning new actions. Exposes `export_training_dataset()` and supports session analysis and user-correction lessons.

### 5. Model Enhancement & Observability
*   **Knowledge Gaps** (`viki/core/knowledge_gaps.py`): Records low-confidence responses; dream research uses `get_research_topics()`.
*   **Pattern Tracker**: Persists patterns to disk; survives restarts.
*   **Performance API**: `GET /api/models/performance` (trust score, latency, error rate per model).
*   **Continuous Learner** (`viki/core/continuous_learning.py`): Optional periodic training cycles with validation.

See [viki/MODEL_ENHANCEMENT_SUMMARY.md](viki/MODEL_ENHANCEMENT_SUMMARY.md) and [viki/OBSERVABILITY.md](viki/OBSERVABILITY.md) for details.

## Cognitive Data Flow
```mermaid
graph TD
    User[User Input] --> Nexus{Priority Nexus}
    Nexus -->|P10: Urgent| Controller
    Nexus -->|P30: Proactive| Controller
    
    Controller --> SafetyCheck{Safety Envelope}
    SafetyCheck -->|Safe| Executor[Skill Executor]
    SafetyCheck -->|Risky| Confirm[Awaiting /confirm]
    
    Controller --> Memory[RAG + Failure Memory]
    Controller --> Router{Model Router}
    
    Router -->|Reflex| Phi3(Local)
    Router -->|Chat| Llama3(Local)
    Router -->|Plan| DeepSeek(Cloud/Local)
    
    Executor -->|Success| UI[Update CLI/Bridge]
    Executor -->|Fail| Record[Record Failure]
    Record --> Memory
```
