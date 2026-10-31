# eu-reg-tracker

Read the `regtracker-conventions` skill before any task, and the stage skill that matches the work
(`regtracker-ingest-parse-diff`, `regtracker-enrichment-groq`, `regtracker-rag-eval`, `regtracker-dashboard-deploy`).
The roadmap is `docs/execution-plan.md`. Current focus: **shipping v1** (push, deploy, LLM-budget tasks, polish).
When resuming, start from the "Status" section at the top of `docs/execution-plan.md`.

## Always
- Diffing is deterministic. The LLM only explains changes the diff found.
- Every stage is idempotent. Raw files are immutable.
- Never write secrets anywhere (code, tests, docs, logs). Config comes from env / `.env` (gitignored).
- No network or real LLM calls in tests; use fixtures and a mock LLM.
- Synthetic data is flagged `is_synthetic` and badged in the UI.
- Verify external facts (Cellar endpoints, CELEX numbers, article counts, Groq models and limits)
  against current official sources; do not trust memory.

## Before saying a task is done
`make check` (ruff, mypy, pytest). For pipeline changes, also `dbt build --project-dir dbt`.

## Commands
`make setup` | `make check` | `regtracker init-db` | `regtracker sources` | `regtracker ingest --doc gdpr`
