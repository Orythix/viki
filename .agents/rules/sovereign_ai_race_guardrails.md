# 🏆 Sovereign AI Race Guardrails

This rule defines the core architectural invariants for VIKI's sovereign AI leadership.

## Invariants
1. **Local-First Sovereignty**:
   - Default inference stays 100% local on LM Studio / Ollama (`http://localhost:1234/v1` / `http://localhost:11434/v1`).
2. **Zero-Leakage Anonymization**:
   - Outbound prompt payloads to external APIs must pass through `PrivacySanitizer.sanitize()` to redact secrets, keys, emails, and IPs.
3. **Hardware & RAM Safety**:
   - Cap context window at 4,096 tokens on 8GB RAM systems to protect KV cache allocation.
   - Defer heavy machine learning packages (`torch`, `whisper`, `vision`) to lazy imports.
   - Trigger `RAMBudgetOptimizer.optimize_memory()` after completing agent tasks.
