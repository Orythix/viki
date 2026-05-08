# RAG evaluation kit (VIKI lessons)

## Purpose

Measure whether **retrieval** (`LearningModule.get_relevant_lessons`) surfaces expected evidence for labeled queries **before** you evaluate full RAG generation quality.

This is the highest-leverage offline check for grounded systems: wrong chunks → wrong or hallucinated answers even with a strong LLM.

## Gold file format (JSONL)

One JSON object per line:

```json
{"id": "unique_id", "query": "natural language user query", "must_contain_any": ["phrase1", "phrase2"]}
```

Optional fields:

- `must_contain_all`: every phrase must appear somewhere in the **union** of top-K results (stricter).
- `must_not_contain`: if any phrase appears in top-K union, count as a **violation** (poisoning / leakage checks).

Matching is **case-insensitive substring** on retrieved lesson text (pragmatic for internal corpora).

## Metrics

| Metric | Meaning |
|--------|---------|
| `success_any_at_k` | Fraction of queries where ≥1 `must_contain_any` phrase appears in top-K union |
| `success_all_at_k` | Fraction where all `must_contain_all` appear in union |
| `mrr_any` / `mrr_all` | Mean reciprocal rank of first qualifying hit |
| `must_not_contain_violation_rate` | Fraction of queries with forbidden substring hits |
| `judge_mean_relevance` | (if `--judge`) Mean Ollama relevance score 0–1 |
| `judge_covers_expected_rate` | (if `--judge`) Fraction where model says gold concepts are covered |

## Run

From repo root:

```bash
python scripts/run_rag_eval.py --gold viki/eval/fixtures/rag_gold.example.jsonl --k 5 --out reports/rag_eval.json
```

### Optional: LLM judge (local Ollama)

After retrieval metrics, score semantic relevance with a **local** model (off by default so CI stays fast):

```bash
python scripts/run_rag_eval.py --gold viki/eval/fixtures/rag_gold.example.jsonl --out reports/rag_eval.json --judge \
  --ollama-url http://127.0.0.1:11434 --judge-model llama3.2:latest
```

The judge receives the query, gold hints (`must_contain_*`), and retrieved passages; it returns `relevance` (0–1) and `covers_expected` in structured JSON. Set `OLLAMA_URL` / `OLLAMA_MODEL` if you prefer env vars.

Use `VIKI_DATA_DIR` or `--data-dir` to point at the DB that holds your lessons.

Operational notes and lesson-import pointers: [VIKI_RUNBOOK.md](../../VIKI_RUNBOOK.md) (§11).

## Practices

- **Curate gold from real user failures** (support tickets, bad answers) — highest ROI.
- **Version gold files** in git; include the manifest path in experiment reports.
- **Pair with** prompt-bake / LoRA export thresholds (`lesson_export_min_access_count`) so training data and retrieval corpus stay aligned.
- **Limitations**: substring labels don’t prove semantic correctness; add LLM-as-judge or human spot checks for production gates.
