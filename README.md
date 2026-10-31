# EU Regulation Change Tracker

Tracks EU digital and data regulation: ingests and versions legal texts, detects article-level
changes deterministically, explains them with an LLM, answers questions with cited sources, and
shows it all on a dashboard. Built entirely on free infrastructure.

> **Not legal advice.** AI-generated summaries can be wrong; always check the official text.

## Quickstart
```bash
cp .env.example .env        # fill in values; never commit .env
make setup
regtracker init-db
regtracker sources
make check
```

## Status
Scaffold complete. Roadmap: `docs/execution-plan.md` (Week 1: ingestion).

## Layout
`src/regtracker/` pipeline stages | `dbt/` models | `dashboard/` Streamlit | `eval/` datasets and reports | `docs/` plan and ADRs
