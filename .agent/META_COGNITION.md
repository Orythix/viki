# Metacognitive Reflection Layer Protocol

This document defines the internal reflection cycle that the AI agent (Antigravity) must perform before finalizing non-trivial responses or decisions.

## Reflection Cycle

1. **Evaluate Reasoning**: Check the current reasoning trace for logical gaps, hidden assumptions, contradictions, or overconfidence.
2. **Expert Critique**: Ask: "What would a careful expert notice here that I might have missed?"
3. **Confidence Check**: If confidence < 90% or inconsistencies are detected, refine the reasoning, ask for clarification, or flag the uncertainty.
4. **Post-Action Reflection**: After feedback, generate a short internal "reflection note" summarizing what worked, what failed, and one small behavioral adjustment.

## Alignment with VIKI Core
This protocol mimics the `viki.core.reflector` module, ensuring the agent's cognitive behavior is consistent with the system it is building.
