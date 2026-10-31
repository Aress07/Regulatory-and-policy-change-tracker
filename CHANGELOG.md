# Changelog

## Unreleased (candidate for v1.0.0)

Release blockers: public deployment (Streamlit Cloud + Hugging Face snapshot), demo video,
human verification of the draft evaluation labels.

### Added
- Ingestion from Cellar: SPARQL version discovery, polite HTTP client (rate limit, retries,
  cache), immutable SHA-256-deduplicated raw storage, run logging.
- Parser for modern and legacy consolidated-text markup; amendment markers recorded per article;
  repeal notices recognised.
- Deterministic article-level diff with renumbering detection and word-level diff HTML.
- dbt models and tests (staging, core, marts) with source freshness; CI on a fixture warehouse.
- LLM enrichment via Groq: strict JSON schema, validation retry and failure rows, disk cache,
  token throttle, daily budget, shadow cost.
- Hybrid retrieval (BM25 + E5, RRF), cited answers with citation validator and refusal gate,
  FastAPI service with rate-limited `/ask`.
- Streamlit dashboard (7 pages), RSS feed, snapshot export/upload, Dagster assets and checks,
  weekly GitHub Actions ingest.
- Evaluation harness, draft gold datasets, evaluation report.

### Corpus
- 14 instruments, 27 consolidated versions, 107 real changes (ADR-002).
