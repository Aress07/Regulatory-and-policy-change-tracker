---
name: regtracker-ingest-parse-diff
description: How to build the ingestion, version discovery, XHTML parsing, normalization, article-level diff, and dbt modeling stages of the EU Regulation Change Tracker. Use this skill whenever working on fetching EUR-Lex or Cellar documents, discovering consolidated versions, parsing articles, recitals, or annexes, computing diffs or renumbering detection, DuckDB schemas, or dbt models and tests for this project, even if the user only says "the parser", "the diff", "ingest", or "versions".
---

# Ingest, parse, diff

Follow `regtracker-conventions` for global rules. This skill covers stages 1-3 plus dbt.

## Ingestion
- Source: the Publications Office **Cellar** (open EUR-Lex repository). Prefer content negotiation on `publications.europa.eu/resource/celex/{CELEX}` with `Accept` and `Accept-Language` headers, and the SPARQL endpoint for discovery. Do not scrape rendered EUR-Lex pages aggressively. Verify endpoints and headers against current Publications Office documentation before coding; do not rely on memory.
- Config lives in `configs/sources.yml` (doc_id, CELEX base, type). Version-specific CELEX for consolidated texts follows `0` + year + type + number + `-` + date; confirm against real responses.
- HTTP client: `httpx`, descriptive User-Agent, ~1 req/s, `tenacity` retries on 5xx/timeouts, request cache keyed by URL + headers.
- Store raw bytes at `data/raw/{doc_id}/{version_date}.xhtml`, SHA-256 in `document_versions.content_hash`. If the hash exists, skip. Log each run in `pipeline_runs` (stage, status, rows_in/out, error).
- Save at least one real SPARQL response and one real XHTML document in `tests/fixtures/` and test against them.

## Parsing
- Inspect the real markup first. Article and recital containers often have ids such as `art_N` / `rct_N`, but verify per instrument and per version; markup can differ. Use one small adapter per markup variant.
- Extract: recitals, articles (number, title, paragraphs), annexes. Strip footnote and amendment markers from the text but keep which amendment touched each article if the markup exposes it.
- Normalize (NFC, whitespace, quotes, NBSP) before computing `text_hash`.
- Golden tests: assert article and recital counts per instrument against the official counts (verify the counts against the official text; do not hardcode from memory).

## Diff
Compare consecutive versions of the same document by `section_key`:
- key only in new -> `added`; only in old -> `removed`
- same key, different `text_hash` -> `modified` (store similarity via `rapidfuzz`/`difflib` and a word-level `diff_html`)
- removed + added with similarity above ~0.9 -> `renumbered`, not two unrelated changes
Tests: swapping the version order inverts added/removed; identical normalized text never yields `modified`; renumbering is detected on a fixture.

## dbt
- `dbt-duckdb`, profile points at `data/warehouse.duckdb`.
- `stg_*` per source table; `dim_documents`, `fct_changes`, `fct_section_versions`; marts `mart_change_timeline`, `mart_topic_trends`, `mart_freshness`.
- Tests: `unique`, `not_null`, `relationships`, `accepted_values` for `change_type`; custom test for no `modified` rows with identical text; freshness on `fetched_at` (latest successful ingest within 8 days).

## Few real changes?
If the corpus yields too few real changes, add amending acts, corrigenda, or Commission proposals vs adopted text, or widen the corpus. Synthetic changes are allowed only as flagged test fixtures.
