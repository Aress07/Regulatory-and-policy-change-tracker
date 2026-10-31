# ADR-003: BM25 in Python instead of DuckDB's FTS extension

**Status:** accepted (2026-10-31)

## Context
The plan called for DuckDB's full-text-search extension for the BM25 half of hybrid retrieval.
The extension is not bundled with the Python package: it is downloaded on first `INSTALL fts`.
That breaks two constraints: tests must run without network access, and the hosted demo
should not depend on downloading binaries at startup.

## Decision
Implement Okapi BM25 (k1 = 1.5, b = 0.75) in `src/regtracker/index/search.py` over the chunk
texts, in memory. Cosine similarity over the stored E5 embeddings is computed with NumPy, and
the two rankings are fused with Reciprocal Rank Fusion (k = 60).

## Consequences
+ Offline, deterministic and fully unit-tested; no runtime downloads.
+ The corpus is a few thousand chunks, so scoring every chunk per query is fast enough.
- Index is rebuilt in memory when the API or app starts (seconds at this size).
- At a much larger scale, move to DuckDB FTS (pre-installed in the image) or a search engine.
