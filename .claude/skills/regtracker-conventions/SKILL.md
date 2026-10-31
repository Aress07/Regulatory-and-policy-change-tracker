---
name: regtracker-conventions
description: Project rules and architecture for the EU Regulation Change Tracker (a free-to-build GenAI portfolio project covering ingestion, versioning, article-level diff, LLM enrichment, cited RAG, Streamlit dashboard). Use this skill at the start of ANY coding, refactoring, review, or planning task in this repo, and whenever the user mentions regtracker, the regulation tracker, CELEX, section_key, change tracker, or asks where code should live, how to name things, or what the project's rules are, even if they do not mention conventions explicitly.
---

# regtracker conventions

Read this first for any task in the repo. It defines the non-negotiable rules.

## Stack (all free)
Python 3.11+, uv, DuckDB, dbt-duckdb, Dagster OSS, FastAPI, Streamlit, sentence-transformers (`intfloat/multilingual-e5-small`), Groq via the `openai` SDK (OpenAI-compatible), Ollama for local dev, GitHub Actions, Hugging Face Hub for the data snapshot.

## Repo layout
```
src/regtracker/{common,ingest,parse,diff,enrich,index,rag,api}/
dbt/  orchestration/  dashboard/  eval/{datasets,reports}/  tests/  docs/  configs/sources.yml
data/   # gitignored: raw/, warehouse.duckdb
```
Put code in the package that matches its pipeline stage. No business logic in `dashboard/` or `api/`; they call into `src/regtracker`.

## Hard rules
1. **Diffing is deterministic.** Never use an LLM to decide what changed. The LLM only explains changes that the diff already found.
2. **Idempotency.** Every stage can be rerun without duplicating rows or overwriting raw files. Raw files are immutable and named by version date; dedupe by SHA-256.
3. **Normalize before hashing.** Unicode NFC, collapsed whitespace, normalized quotes and NBSP. `text_hash` is computed on normalized text only.
4. **Stable keys.** `section_key` is `art_N`, `rct_N`, `annex_X`. `section_id = version_id + '#' + section_key`.
5. **Secrets.** Never write API keys, tokens, or `.env` contents into code, tests, docs, logs, or chat. Read config via pydantic-settings from the environment.
6. **No network in CI.** Tests use saved fixtures and a mock LLM. Real LLM and real-data runs are manual or in the eval scripts.
7. **Label synthetic data.** Synthetic changes carry `is_synthetic = true` and a visible badge in the UI. Never present them as real.
8. **Every AI output is traceable.** Store model, prompt_version, tokens, latency, and shadow cost with each enrichment.
9. **Disclaimers.** "Not legal advice" in the README and in the dashboard footer. AI-generated text is visibly labeled and links to the official source.
10. **Be polite to sources.** Descriptive User-Agent with contact email, ~1 request/second, cached responses, retries with backoff.

## Quality gates (run before saying a task is done)
`ruff check . && ruff format --check . && mypy src && pytest -q`
For pipeline changes also run `dbt build --project-dir dbt` against the fixture DB.

## Style
Type hints everywhere; pydantic models at boundaries; small pure functions for parsing and diffing; typer CLI commands named after stages (`ingest`, `parse`, `diff`, `enrich`, `index`). Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`). Record significant decisions as ADRs in `docs/decisions/`.

## Working method
Build vertically: get one document through every stage before scaling to all instruments. Add a test with each new behavior. When a requirement is ambiguous, state the assumption in the PR description instead of silently choosing.
