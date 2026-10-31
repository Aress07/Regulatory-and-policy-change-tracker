# ADR-001: DuckDB instead of Postgres

**Status:** accepted

## Context
The project must be free to build and host, run on a laptop, and deploy as a read-only demo.

## Decision
Use a single DuckDB file as the warehouse (dbt-duckdb for transforms, DuckDB FTS + cosine similarity for hybrid search).

## Consequences
+ No server to run or pay for; the snapshot is one file that can live on Hugging Face Hub.
+ Fast analytics, easy fixtures for CI.
- Single-writer; no concurrent ingestion jobs.
- Foreign keys are documented but not enforced (DuckDB upsert limitations).
- If the corpus or concurrency grows, migrate to Postgres + pgvector (listed as a stretch goal).
