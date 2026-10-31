# Changelog

## Unreleased (candidate for v1.0.0)

Release blockers: public deployment (Hugging Face Space + dataset snapshot), demo video,
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
- Web app: React + TypeScript frontend (7 pages) served by FastAPI from one Docker image
  (replaced the first Streamlit dashboard, ADR-004).
- RSS feed, snapshot export/upload, Dagster assets and checks, weekly GitHub Actions ingest.
- Evaluation harness, draft gold datasets, evaluation report.
- Web app design pass: sidebar navigation, landing overview, light/dark theme, readable section
  labels; README screenshots.
- Deployment workflow for a Hugging Face Docker Space (runs after green CI); the weekly ingest
  restarts the Space so it loads the new snapshot.
- Prompt `v2` (sector convention, impact examples), not yet evaluated; `v1` stays the default.

### Fixed
- `numpy` is declared in the `app` extra (it reached CI only through Streamlit).
- `index.html` is served with `Cache-Control: no-cache`, so a redeploy cannot leave a blank page.

### Corpus
- 14 instruments, 27 consolidated versions, 107 real changes (ADR-002).
