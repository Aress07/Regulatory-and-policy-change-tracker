---
name: regtracker-dashboard-deploy
description: How to build and deploy the React web app and FastAPI service, Dagster orchestration, GitHub Actions scheduled ingestion, Hugging Face snapshot hosting, RSS or email alerts, and the README and demo for the EU Regulation Change Tracker, all on free infrastructure. Use this skill whenever working on dashboard pages, charts, diff viewer, Docker / Hugging Face Spaces deployment, secrets, cron workflows, snapshots, alerts, CI, README, architecture diagram, or the demo video, even if the user just says "deploy", "UI", or "make it look good".
---

# Dashboard, orchestration, deployment

Follow `regtracker-conventions`. Everything must remain free.

## Web app (`frontend/`, served by `src/regtracker/api/main.py`)
React + TypeScript (Vite) single-page app; FastAPI serves the API under `/api` and the built app
from `frontend/dist` (unknown paths fall back to `index.html`). See ADR-004.
Pages: Overview (KPIs, freshness banner) | Change timeline (filters in the URL: instrument, topic,
sector, impact, change type, dates) | Change detail (word-level diff, AI summary, impact +
rationale, official link, "AI-generated" badge, "How was this generated?") | Topic trends
(stacked bars, instrument x topic heatmap) | Since I last looked | Ask (cited Q&A) | Pipeline
health (runs, failures, LLM usage and shadow cost).
Rules: no business logic or SQL in the frontend or API routes (queries live in
`regtracker.app.queries`); persistent disclaimer on every page; synthetic data badged; empty,
loading and error states handled; Vitest tests mock `fetch`; charts are lazy-loaded.

## Orchestration
Dagster assets: `raw_versions -> sections -> changes -> enrichments -> chunks -> dbt models`, with asset checks for freshness and "no failed enrichments". Local weekly schedule; the lineage graph is the interview demo.

## Free production run
- `.github/workflows/ingest.yml`: weekly `cron` plus `workflow_dispatch`; steps: checkout, install, ingest/parse/diff, dbt build, export snapshot (DuckDB file or Parquet + embeddings), upload to a Hugging Face dataset repo with `HF_TOKEN` from GitHub Secrets.
- Heavy LLM enrichment runs locally (Groq/Ollama), then the snapshot is pushed. Do not assume CPU runners can run models; test first.
- `ci.yml`: lint, types, tests, dbt build on the fixture DB, app boot smoke test. No network or real LLM calls in CI.

## Hugging Face Spaces (Docker)
One image (`Dockerfile`): Node builds `frontend/`, Python serves API + static app on port 7860.
Secrets in the Space settings, never in the repo: `HF_DATASET_REPO` (+ `HF_TOKEN` if private),
optional `LLM_API_KEY`. The app downloads the snapshot at startup. `/ask` has a per-IP rate limit
and a global daily cap; beyond it, Ask returns retrieved passages only, never an error.

## Alerts
Generate `feed.xml` (RSS) with the newest medium/high-impact changes (validate it). Optional SMTP email digest with credentials in secrets.

## Security basics
Secret scanning on, no secrets in git history, pinned dependencies, max input length and rate limit on `/ask`.

## Polish
README order: one-line pitch, screenshot/GIF, architecture diagram (Mermaid), features, quickstart (`make setup && make demo`), design decisions (deterministic diff, DuckDB, hybrid search), evaluation summary table, limitations, disclaimer. Tag `v1.0.0`. Demo video 2-3 minutes: problem, pipeline run, a diff with summary, a cited question, lineage graph, eval results.
