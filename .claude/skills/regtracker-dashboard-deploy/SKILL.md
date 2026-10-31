---
name: regtracker-dashboard-deploy
description: How to build and deploy the Streamlit dashboard, FastAPI service, Dagster orchestration, GitHub Actions scheduled ingestion, Hugging Face snapshot hosting, RSS or email alerts, and the README and demo for the EU Regulation Change Tracker, all on free infrastructure. Use this skill whenever working on dashboard pages, charts, diff viewer, Streamlit Cloud deployment, secrets, cron workflows, snapshots, alerts, CI, README, architecture diagram, or the demo video, even if the user just says "deploy", "UI", or "make it look good".
---

# Dashboard, orchestration, deployment

Follow `regtracker-conventions`. Everything must remain free.

## Streamlit pages (`dashboard/app.py`, `dashboard/pages/`)
Overview (KPIs, freshness banner) | Change timeline (filters: instrument, topic, sector, impact, date) | Change detail (side-by-side word-level diff, AI summary, impact + rationale, official link, "AI-generated" badge, expandable "How was this generated?" with model and prompt version) | Topic trends (Plotly, instrument x topic heatmap) | Since I last looked | Ask (cited Q&A) | Pipeline health (runs, failures, row counts, cost).
Rules: no business logic in pages; query through `src/regtracker`; `st.cache_data` for queries; persistent disclaimer; synthetic data visibly badged; empty and error states handled.

## Orchestration
Dagster assets: `raw_versions -> sections -> changes -> enrichments -> chunks -> dbt models`, with asset checks for freshness and "no failed enrichments". Local weekly schedule; the lineage graph is the interview demo.

## Free production run
- `.github/workflows/ingest.yml`: weekly `cron` plus `workflow_dispatch`; steps: checkout, install, ingest/parse/diff, dbt build, export snapshot (DuckDB file or Parquet + embeddings), upload to a Hugging Face dataset repo with `HF_TOKEN` from GitHub Secrets.
- Heavy LLM enrichment runs locally (Groq/Ollama), then the snapshot is pushed. Do not assume CPU runners can run models; test first.
- `ci.yml`: lint, types, tests, dbt build on the fixture DB, app boot smoke test. No network or real LLM calls in CI.

## Streamlit Community Cloud
Public GitHub repo; entry point `dashboard/app.py`; secrets in the app's secrets settings, never in the repo. At startup download the snapshot with `huggingface_hub` and cache it; keep it small. The shared LLM key needs a per-session question cap and a global daily counter; when exhausted, the Ask page shows retrieved passages only, never an error. Optional: FastAPI on Hugging Face Spaces (Docker).

## Alerts
Generate `feed.xml` (RSS) with the newest medium/high-impact changes (validate it). Optional SMTP email digest with credentials in secrets.

## Security basics
Secret scanning on, no secrets in git history, pinned dependencies, max input length and rate limit on `/ask`.

## Polish
README order: one-line pitch, screenshot/GIF, architecture diagram (Mermaid), features, quickstart (`make setup && make demo`), design decisions (deterministic diff, DuckDB, hybrid search), evaluation summary table, limitations, disclaimer. Tag `v1.0.0`. Demo video 2-3 minutes: problem, pipeline run, a diff with summary, a cited question, lineage graph, eval results.
