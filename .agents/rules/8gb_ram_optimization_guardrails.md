# 🛡️ 8GB RAM Optimization Guardrails

This rule defines hardware protection boundaries and memory management policies for running VIKI on 8GB and 16GB RAM devices.

## Rules & Constraints
1. **Context Window Cap**:
   - For 8GB RAM local model profiles, set `max_context_tokens: 4096`.
   - For 16GB RAM local model profiles, set `max_context_tokens: 8192`.
   - Never exceed 8,192 tokens on local inference engines to prevent KV cache RAM bloat.

2. **Lazy Package Loading**:
   - Keep heavy packages (`torch`, `transformers`, `sentence_transformers`, `whisper`, `pytesseract`) lazily loaded on first explicit invocation.
   - Maintain an idle process memory footprint under 200 MB RAM.

3. **Active Garbage Collection**:
   - Trigger `RAMBudgetOptimizer.optimize_memory()` during active reasoning turns to run Python garbage collection (`gc.collect()`).

4. **Quantization Recommendation**:
   - Prefer GGUF `Q3_K_M` or `Q4_K_M` quantized models (e.g. `google/gemma-4-e4b`, `deepseek-r1-distill-qwen-14b`) for 100% local execution without swap thrashing.
