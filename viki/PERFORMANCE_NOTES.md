# Performance Optimization Notes

**Last updated:** 2026-02-14

## GPU Usage (Default: CPU)

To keep GPU usage low, **embedding models** (sentence-transformers in learning and narrative memory) and **Silero VAD** (voice) run on **CPU by default**. This avoids heavy GPU load when running VIKI alongside other apps or on integrated graphics.

- **Embeddings:** Set `VIKI_EMBED_GPU=1` to use GPU for sentence-transformers (learning + narrative).
- **Voice VAD:** Set `VIKI_VAD_GPU=1` to use GPU for Silero VAD.

Only set these if you have a dedicated GPU and want faster embedding/VAD at the cost of GPU memory and power.

## Semantic Search Indexing (Future Enhancement)

### Current State
- Full-table scans in `viki/core/learning.py` lines 232-266
- Full-table scans in `viki/core/memory/narrative.py` lines 101-107
- All lessons/episodes loaded into memory for each semantic search

### Recommended Improvements
1. Add FAISS or Annoy index for approximate nearest-neighbor search
2. Implement SQLite FTS (Full-Text Search) for text-based queries
3. Cache frequently accessed embeddings
4. Implement pagination for large result sets

### Implementation Priority
- Medium priority (after critical bugs and security fixes)
- Estimated effort: 2-3 days
- Dependencies: `faiss-cpu` or `annoy` package

### References
- FAISS: https://github.com/facebookresearch/faiss
- Annoy: https://github.com/spotify/annoy
- SQLite FTS5: https://www.sqlite.org/fts5.html
