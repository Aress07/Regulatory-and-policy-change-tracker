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

## Data sources and reuse
Legal texts come from the Publications Office of the EU **Cellar** repository (the open store behind
EUR-Lex), fetched via content negotiation on `publications.europa.eu/resource/celex/{CELEX}`.

- EUR-Lex documents may generally be reused for commercial and non-commercial purposes, with credit and
  an indication of any changes, unless otherwise specified (third-party content and some documents, such
  as International Accounting Standards, can carry separate conditions). See the
  [EUR-Lex legal notice](https://eur-lex.europa.eu/content/legal-notice/legal-notice.html) and the
  [Commission legal notice](https://commission.europa.eu/legal-notice_en#copyright-notice).
- Only the electronic Official Journal on EUR-Lex is authentic (since 1 July 2013). Texts and summaries
  here are derived data, not the official version; always check the official source.
- Consolidated versions are not legally binding either; they are documentation tools.
- We fetch politely: descriptive User-Agent, about 1 request per second, cached responses, retries with backoff.
