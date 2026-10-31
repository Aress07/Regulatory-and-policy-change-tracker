# EU Digital Regulation Change Tracker: Execution Plan (100% free to build)

A pipeline that ingests EU digital and data regulations, versions them, detects article-level changes, explains those changes with an LLM, answers cited questions (RAG), and shows everything on a dashboard.

> **Not legal advice.** Put this disclaimer in the README and in the dashboard footer.
> **Free-tier caveat:** vendors change limits often. Before relying on any service below, check its current pricing page. Every service here has a fully local fallback.

---

## Status (updated 2026-10-31): read this first when resuming

**Where things stand.** Weeks 0-6 are implemented, the UI design pass is done, and everything is
pushed. The project is code-complete but not "done" per section 0.4: deployment (needs the user's
Hugging Face account), the remaining LLM-budget runs, verified labels, the demo video and `v1.0.0`
are open.

**Deviations from the plan below (already decided, do not revisit):**
- Corpus widened to 14 instruments / 27 consolidated versions / 107 real changes, because most of the
  six headline acts have no pair of English consolidated versions (ADR-002). Added eIDAS, ePrivacy, EECC.
- UI is **FastAPI + React** (`frontend/`, served by FastAPI from one Docker image on port 7860),
  not Streamlit (ADR-004). Read "Streamlit" in sections 10, 11.2 and 13 as "React web app"; the
  deployment target is a Hugging Face Space (Docker SDK), not Streamlit Community Cloud.
- BM25 is implemented in Python, not DuckDB FTS (ADR-003).
- Real LLM runs use Groq (`openai/gpt-oss-20b` / `-120b`), key in `.env` as `LLM_API_KEY`.
- Eval gold labels in `eval/datasets/` are LLM-drafted (`status=draft`); metrics are provisional
  until the user verifies them.

**Git.** Branch `main`, pushed. Commit locally per milestone; push on the user's go-ahead (given
for "finish the project"). No co-author trailer. `CV_*.pdf` in the repo root is the user's file:
never commit it.

**Next steps, in order:**
1. **Deploy** (user creates the accounts; Claude can guide): Hugging Face write token; a dataset
   repo; an empty **Docker** Space. GitHub: variables `HF_DATASET_REPO`, `HF_SPACE_REPO`, `USER_AGENT`
   (same value as `.env`), secret `HF_TOKEN`. Locally `regtracker snapshot --upload` (with
   `HF_DATASET_REPO`/`HF_TOKEN` set), then run "Deploy to Hugging Face Space" from the Actions tab
   (it also runs after every green CI on `main`). In the Space settings: variable `HF_DATASET_REPO`,
   secret `LLM_API_KEY` (optional). Check the Space from a fresh browser, then tick 0.4 and add the
   URL to the README and section 16.
2. **LLM-budget tasks** (Groq free tier, ~150K tokens/day; ~1.8K tokens/change):
   - Day A: `regtracker enrich` for the remaining 25 of 107 changes (v1, 82 done).
   - Day B: `regtracker enrich --prompt-version v2 --ids-file eval/datasets/changes_labeled.csv`, then
     `python eval/run_eval.py --suite classification --prompt-version v2` and compare with v1.
     v2 (written, untested) states the sector convention and adds impact examples; it was written
     after seeing v1 errors on the same draft labels, so report it as tuned, not blind. Switch
     `DEFAULT_PROMPT_VERSION` only if it wins; then re-enrich all changes with v2.
   - Day C: `python eval/run_eval.py --suite answers` (end-to-end cited answers).
   - After each: refresh `docs/eval-report.md`, the README table and section 16.
3. **User verifies draft labels** (`docs/labeling-guide.md`), then rerun `eval/run_eval.py --suite all`.
4. **Ship:** record the 2-3 minute demo video (`docs/demo-script.md`), update `CHANGELOG.md`, tag `v1.0.0`.

**Run locally:** `make demo` (fixture warehouse) or `make app` / `make api` (real warehouse) on
http://localhost:8000; `make frontend-dev` for Vite on :5173. Before saying a task is done: `make check`,
`dbt build --project-dir dbt` for pipeline changes, `npm test && npm run build` in `frontend/` for UI changes.

**Current results (provisional, draft labels):** retrieval hybrid MRR 0.975 (BM25 0.869, vector 0.927);
refusal gate 25/25 on test (`min_cosine` 0.8313); impact accuracy 0.568, within-one 0.973; topic micro-F1
0.624; sector micro-F1 0.253; 1,810 tokens/change, shadow cost $0.37 per 1,000 changes.

---

## 0. Project definition

### 0.1 Problem statement
Compliance teams and small businesses can't easily see *what changed* in EU digital regulation, *why it matters*, or *where exactly in the text*. This tool answers three questions:

1. What changed since I last looked?
2. What does that change mean in plain language, and who does it affect?
3. Can I ask a question and get an answer that cites the exact article?

### 0.2 Scope (keep it small enough to finish)

| In scope | Out of scope (for v1) |
|---|---|
| English texts | Other languages (stretch goal: FR summaries) |
| 5-8 core instruments (see 0.3) | All of EUR-Lex |
| Article / recital / annex level | Case law, national transposition |
| Weekly batch ingestion | Real-time streaming |
| Single-user demo | Auth, multi-tenant |

### 0.3 Starting corpus (verify identifiers on EUR-Lex)

| Instrument | CELEX (base act) |
|---|---|
| GDPR | 32016R0679 |
| AI Act | 32024R1689 |
| Data Act | 32023R2854 |
| Digital Services Act | 32022R2065 |
| Digital Markets Act | 32022R1925 |
| NIS2 Directive | 32022L2555 |

Consolidated versions use CELEX numbers of the form `0` + year + type + number + `-` + date (for example `02016R0679-YYYYMMDD`). Each consolidated version is a natural "version" for diffing.

**Risk to plan for:** real amendments are infrequent, so you may have few real changes to show. Mitigations are in section 9 (amending acts, corrigenda, Commission proposals, and clearly labeled synthetic test changes).

### 0.4 Definition of done (v1)
- [x] Scheduled pipeline ingests, versions, parses, and diffs documents without manual steps
- [ ] Every change has a plain-language summary, topic tags, sector tags, and an impact rating
- [x] Cited Q&A that refuses when retrieval is weak
- [ ] Dashboard live at a public URL
- [x] Evaluation report with real numbers
- [ ] README with architecture diagram, setup instructions, and a 2-3 minute demo video

---

## 1. Free stack

| Layer | Choice | Cost | Notes / fallback |
|---|---|---|---|
| Language | Python 3.11+ | Free | Use `uv` (fast) or `pip` + `venv` |
| Code hosting + CI | GitHub + GitHub Actions | Free for public repos | Keep the repo public (also good for your resume) |
| Raw storage | Local filesystem, gitignored | Free | Snapshot goes to Hugging Face Hub (below) |
| Warehouse | **DuckDB** (single file) | Free | Zero ops, great with dbt and Parquet |
| Transformations | **dbt-core + dbt-duckdb** | Free | |
| Orchestration | **Dagster OSS** (local) + **GitHub Actions cron** (scheduled) | Free | Prefect OSS is an alternative |
| Data quality | dbt tests + `pytest` (+ optional Great Expectations) | Free | |
| Embeddings | `sentence-transformers` with `intfloat/multilingual-e5-small` (384 dims, CPU-friendly) | Free | Runs locally; multilingual helps the FR stretch goal |
| Search | DuckDB FTS (BM25) + cosine similarity, hybrid | Free | Corpus is small, so brute-force vectors are fast enough |
| LLM (dev, batch enrichment) | **Ollama** with a local model (e.g., Qwen2.5 7B or Llama 3.x 8B; use 3B variants on low RAM) | Free | Fully offline |
| LLM (hosted demo Q&A) | A free-tier API (Gemini, Groq, or OpenRouter free models) | Free, rate-limited | Fallback: show retrieved passages only, no generated answer |
| LLM client | `openai` Python SDK pointed at any OpenAI-compatible base URL | Free | One client covers Ollama, Gemini, Groq, OpenRouter |
| API | FastAPI | Free | Run locally; optional deploy on Hugging Face Spaces (Docker) |
| Dashboard | Streamlit | Free | Deploy on Streamlit Community Cloud (needs a public GitHub repo) |
| Data snapshot hosting | Hugging Face Hub (dataset repo) | Free | The deployed app downloads the snapshot at startup |
| Alerts | RSS feed file + SMTP email (Gmail app password) or GitHub Issues | Free | |
| Containers | Docker Desktop (free for personal use) or Podman | Free | |
| Quality tooling | `ruff`, `pytest`, `mypy`, `pre-commit` | Free | |

**Design decision:** the heavy LLM work (enrichment, embeddings) runs **locally in batch**; results are stored in the snapshot. The deployed demo therefore needs almost no compute. Only the Q&A answer step calls a hosted free-tier LLM, and it degrades gracefully.

---

## 2. Architecture

```
GitHub Actions cron (weekly)  /  Dagster (local)
        │
        ▼
[1 Ingest] ──► data/raw/{celex}/{version}.xhtml  (immutable, hashed)
        │
        ▼
[2 Parse + chunk] ──► sections (articles, recitals, annexes)
        │
        ▼
[3 Diff] ──► changes (added / removed / modified / renumbered)
        │
        ▼
[4 Enrich (LLM, local)] ──► summary, topics, sectors, impact, rationale
        │
        ▼
[5 Embed + index] ──► vectors + BM25 index
        │
        ▼
[6 dbt marts + tests] ──► dashboard-ready tables
        │
        ├──► [7 RAG API (FastAPI)] ──► cited answers
        └──► [8 Dashboard (Streamlit)] + RSS/email digest
```

### 2.1 Repo layout

```
eu-reg-tracker/
├── README.md
├── pyproject.toml
├── Makefile
├── docker-compose.yml          # optional: app + api
├── .pre-commit-config.yaml
├── .github/workflows/
│   ├── ci.yml                  # lint + tests + dbt build on a fixture DB
│   └── ingest.yml              # weekly cron: ingest -> snapshot -> HF Hub
├── configs/
│   └── sources.yml             # CELEX list, languages, polite-fetch settings
├── src/regtracker/
│   ├── common/                 # config, db, logging, hashing
│   ├── ingest/                 # cellar client, fetcher, version discovery
│   ├── parse/                  # xhtml parser, section model, chunker
│   ├── diff/                   # article-level diff
│   ├── enrich/                 # llm_client, schemas, prompts/, enrich.py
│   ├── index/                  # embed.py, search.py (hybrid)
│   ├── rag/                    # retrieve, answer, citation check
│   └── api/                    # FastAPI app
├── dbt/                        # models/, tests/, seeds/
├── orchestration/              # Dagster definitions
├── dashboard/                  # app.py, pages/
├── eval/
│   ├── datasets/               # labeled changes + QA set (CSV/JSONL)
│   ├── run_eval.py
│   └── reports/
├── tests/                      # unit + integration + fixtures
├── data/                       # gitignored: raw/, warehouse.duckdb
└── docs/                       # architecture.md, decisions/ (ADRs), eval-report.md
```

---

## 3. Data model (DuckDB)

```sql
-- One row per legal instrument
CREATE TABLE documents (
  doc_id        VARCHAR PRIMARY KEY,        -- e.g. 'gdpr'
  celex_base    VARCHAR NOT NULL,           -- e.g. '32016R0679'
  title         VARCHAR,
  doc_type      VARCHAR,                    -- regulation | directive | proposal ...
  language      VARCHAR DEFAULT 'EN'
);

-- One row per version (consolidated text, original, corrigendum, proposal)
CREATE TABLE document_versions (
  version_id    VARCHAR PRIMARY KEY,        -- doc_id || '@' || version_date
  doc_id        VARCHAR REFERENCES documents(doc_id),
  celex         VARCHAR NOT NULL,           -- CELEX of this specific version
  version_date  DATE,
  source_url    VARCHAR NOT NULL,
  fetched_at    TIMESTAMP NOT NULL,
  content_hash  VARCHAR NOT NULL,           -- sha256 of raw bytes
  raw_path      VARCHAR NOT NULL
);

-- Structural units
CREATE TABLE sections (
  section_id    VARCHAR PRIMARY KEY,        -- version_id || '#' || section_key
  version_id    VARCHAR REFERENCES document_versions(version_id),
  section_key   VARCHAR NOT NULL,           -- 'art_5', 'rct_12', 'annex_III'
  section_type  VARCHAR NOT NULL,           -- article | recital | annex
  number        VARCHAR,
  heading       VARCHAR,
  text          VARCHAR NOT NULL,
  text_hash     VARCHAR NOT NULL,           -- hash of normalized text
  position      INTEGER
);

-- Differences between consecutive versions
CREATE TABLE changes (
  change_id     VARCHAR PRIMARY KEY,
  doc_id        VARCHAR,
  from_version  VARCHAR,
  to_version    VARCHAR,
  section_key   VARCHAR,
  change_type   VARCHAR,                    -- added | removed | modified | renumbered
  old_text      VARCHAR,
  new_text      VARCHAR,
  similarity    DOUBLE,                     -- 0..1 for modified
  diff_html     VARCHAR
);

-- LLM output, fully traceable
CREATE TABLE enrichments (
  change_id        VARCHAR REFERENCES changes(change_id),
  model            VARCHAR,
  prompt_version   VARCHAR,
  summary          VARCHAR,
  topics           VARCHAR[],
  sectors          VARCHAR[],
  impact           VARCHAR,                 -- low | medium | high
  impact_rationale VARCHAR,
  tokens_in        INTEGER,
  tokens_out       INTEGER,
  latency_ms       INTEGER,
  shadow_cost_usd  DOUBLE,                  -- estimated at public API prices
  created_at       TIMESTAMP
);

-- Retrieval units
CREATE TABLE chunks (
  chunk_id      VARCHAR PRIMARY KEY,
  section_id    VARCHAR REFERENCES sections(section_id),
  text          VARCHAR,
  embedding     FLOAT[384]
);

-- Observability
CREATE TABLE pipeline_runs (
  run_id        VARCHAR,
  stage         VARCHAR,
  started_at    TIMESTAMP,
  finished_at   TIMESTAMP,
  status        VARCHAR,                    -- success | failed | skipped
  rows_in       INTEGER,
  rows_out      INTEGER,
  error         VARCHAR
);
```

**Why shadow cost?** Local models cost $0, but recruiters like cost-awareness. Record tokens, then compute what the same run would cost at public API prices for a few reference models. Report both.

---

## 4. Phase 0: Environment setup (Days 1-2)

### Tasks
1. **Create the repo** `eu-reg-tracker` on GitHub (public), add MIT license, `.gitignore` (Python, `data/`, `.env`).
2. **Install tooling**
   - Python 3.11+, `uv` (or `pip`), Git, Docker (optional), [Ollama](https://ollama.com).
3. **Scaffold the project**
   - `uv init` or `pyproject.toml` with dependencies: `httpx`, `lxml`, `beautifulsoup4`, `duckdb`, `pydantic`, `pydantic-settings`, `tenacity`, `typer`, `rich`, `sentence-transformers`, `numpy`, `openai`, `fastapi`, `uvicorn`, `streamlit`, `plotly`, `dbt-duckdb`, `dagster`, `dagster-webserver`, `dagster-dbt`, `pytest`, `ruff`, `mypy`, `huggingface_hub`.
4. **Quality gates**
   - `ruff` (lint + format), `mypy`, `pre-commit` hooks, `pytest` config.
   - `Makefile` targets: `setup`, `lint`, `test`, `ingest`, `parse`, `diff`, `enrich`, `index`, `dbt`, `app`, `api`, `eval`.
5. **Pull a local model**
   - `ollama pull qwen2.5:7b-instruct` (or a 3B model if RAM is limited).
   - Smoke-test via the OpenAI-compatible endpoint (`http://localhost:11434/v1`).
6. **Create the first CI workflow**: lint + pytest on every push.
7. **Write ADR-001** (`docs/decisions/001-duckdb-over-postgres.md`): why DuckDB, trade-offs, and what you'd change at scale. ADRs are cheap and look professional.

### Done when
- `make lint test` passes locally and in GitHub Actions
- An LLM call through your client returns a JSON response from Ollama

---

## 5. Phase 1 (Week 1): Ingestion and raw storage

### Goals
Reliably discover and download versions of each instrument, store them immutably, and record provenance.

### Day-by-day

**Day 1: Understand the source**
- Read the Publications Office documentation for **Cellar** (the open EUR-Lex repository). Two access routes that need no payment:
  - **Content negotiation** on `publications.europa.eu/resource/celex/{CELEX}` with `Accept` and `Accept-Language` headers to fetch a specific format and language.
  - **SPARQL endpoint** to discover works, versions, and metadata.
- Check the EUR-Lex legal notice for reuse conditions and record them in the README.
- Do **not** scrape rendered HTML pages aggressively; they may be rate-limited or blocked.
- Manually fetch one document (GDPR) and inspect the XHTML structure: article containers, recital containers, annex containers. Note how IDs and classes are structured.

**Day 2: Config + HTTP client**
- `configs/sources.yml`: list of instruments (doc_id, CELEX base, type).
- `common/http.py`: `httpx` client with
  - a descriptive `User-Agent` including a contact email,
  - rate limit of about 1 request per second,
  - retries with exponential backoff (`tenacity`),
  - timeouts.
- Local response cache keyed by URL + headers (saves you from re-downloading while developing).

**Day 3: Version discovery**
- Implement `ingest/discover.py`: for each base CELEX, list consolidated versions with their dates (via SPARQL or the documented pattern). Output: list of `(celex_version, version_date, url)`.
- Unit test with a recorded fixture (save one SPARQL response in `tests/fixtures/`).

**Day 4: Download + store**
- `ingest/fetch.py`: download each version's XHTML, compute SHA-256, write to `data/raw/{doc_id}/{version_date}.xhtml`, insert into `document_versions`.
- **Idempotency:** if the hash already exists, skip. A rerun must never duplicate rows or overwrite files.
- Log every run to `pipeline_runs`.

**Day 5: CLI + tests + docs**
- `regtracker ingest --doc gdpr` and `--all` using Typer.
- Tests: idempotency, retry on 5xx, handling of 404/missing language.
- Write `docs/sources.md` describing each source, license, and quirks.

### Done when
- [ ] `make ingest` downloads all configured versions for at least 3 instruments
- [ ] A second run downloads nothing and reports "0 new versions"
- [ ] `document_versions` has correct URL, date, and hash for every file

---

## 6. Phase 2 (Week 2): Parsing, diffing, and dbt

### Goals
Turn raw XHTML into clean structural sections, and detect what changed between versions.

### Day-by-day

**Day 1-2: Parser**
- `parse/xhtml_parser.py` using `lxml`/`BeautifulSoup`:
  - Extract **recitals**, **articles** (number, title, paragraphs), and **annexes**.
  - Strip footnote markers, amendment markers (such as ▼M1 or ►M1 symbols in consolidated texts), and navigation noise, but keep a record of which amendment affected each article if the markup provides it. This is valuable metadata.
  - Generate stable `section_key`s such as `art_5`, `rct_12`, `annex_III`.
- Normalize text: Unicode NFC, collapse whitespace, normalize quotes and non-breaking spaces. The `text_hash` must be computed on **normalized** text, otherwise cosmetic differences create fake changes.
- Golden-file tests: for each instrument, assert the number of articles and recitals matches the known counts (for example, assert the GDPR has 99 articles and 173 recitals; verify counts against the official text).

**Day 3: Diff engine**
- `diff/article_diff.py`, compare two versions of the same document by `section_key`:
  - key only in new → `added`
  - key only in old → `removed`
  - same key, hash differs → `modified` (compute similarity with `difflib.SequenceMatcher` or `rapidfuzz`, plus word-level diff HTML)
  - **Renumbering:** if an old key is removed and a new key is added with high similarity (> ~0.9), mark as `renumbered` instead of two unrelated changes. This is a common real-world false positive.
- **Do not use an LLM here.** Deterministic diffing is auditable. Say this explicitly in the README; it's a good design point.

**Day 4: dbt project**
- `dbt-duckdb` profile pointing to `data/warehouse.duckdb`.
- Models:
  - `stg_*` for each source table,
  - `dim_documents`, `fct_changes`, `fct_section_versions`,
  - marts: `mart_change_timeline`, `mart_topic_trends` (stub until enrichment exists), `mart_freshness`.
- Tests: `unique`, `not_null`, `relationships`, `accepted_values` (change_type), plus custom tests (for example, no `modified` change where old_text = new_text).
- Source freshness check on `document_versions.fetched_at`.

**Day 5: Hardening**
- Property-style tests for the diff (swap order → added/removed invert).
- Write `docs/architecture.md` v1 with the diagram.

### Done when
- [ ] `make parse diff dbt` runs end to end
- [ ] Article counts match the official counts for each instrument
- [ ] dbt tests pass in CI against a small fixture database
- [ ] You can open a diff for one real pair of versions and visually confirm it is correct

---

## 7. Phase 3 (Week 3): LLM enrichment

### Goals
Add structured, traceable, cost-aware LLM analysis to each change.

### Day-by-day

**Day 1: LLM client abstraction**
- `enrich/llm_client.py`: a thin wrapper around the `openai` SDK with
  - configurable `base_url`, `model`, `api_key` via env (`.env`, never committed),
  - retries/backoff, timeouts,
  - logging of tokens, latency, and model name,
  - a **disk cache** keyed by `(model, prompt_version, input_hash)` so reruns are free and deterministic.
- Providers to test: Ollama (local), one free-tier hosted provider.

**Day 2: Output schema + prompt**
- Define the output with Pydantic and enforce it (JSON mode / JSON schema, then validate):

```python
from typing import Literal
from pydantic import BaseModel, Field

Topic = Literal[
    "data_protection",
    "ai_governance",
    "cybersecurity",
    "platform_liability",
    "competition",
    "data_sharing",
    "transparency",
    "enforcement_penalties",
    "scope_definitions",
    "other",
]
Sector = Literal[
    "all",
    "healthcare",
    "finance",
    "public_sector",
    "online_platforms",
    "manufacturing",
    "telecom",
    "education",
    "other",
]


class ChangeAnalysis(BaseModel):
    summary: str = Field(max_length=500, description="Plain-language, 1-3 sentences")
    topics: list[Topic] = Field(min_length=1, max_length=3)
    sectors: list[Sector] = Field(min_length=1, max_length=3)
    impact: Literal["low", "medium", "high"]
    impact_rationale: str = Field(max_length=300)
```

- Prompt rules (store in `src/regtracker/enrich/prompts/v1.md`, version it):
  - Provide `old_text`, `new_text`, article title, instrument name.
  - Instruct: describe **only** what the text diff shows, do not speculate beyond it, no legal advice.
  - Define the impact scale explicitly (for example: *low* = wording or clarification; *medium* = obligation or scope changes for some actors; *high* = new or removed obligations, penalties, or deadlines that affect many actors).
  - Use 2-3 few-shot examples from your own labeled data (keep them out of the eval set).

**Day 3: Batch enrichment job**
- `regtracker enrich` processes unenriched changes, validates output, and on a validation failure retries once with the error message, then marks the row as failed rather than silently dropping it.
- Store `prompt_version`, `model`, tokens, latency, shadow cost.
- Model routing experiment: small model for classification fields, larger model for the summary. Record the quality/cost trade-off in a table (this goes into your eval report).

**Day 4: Test with synthetic and real changes**
- Unit tests with a **mock LLM** returning canned JSON (no network in CI).
- Add a handful of **clearly labeled synthetic changes** (for example, edit a penalty amount in a fixture article) to verify the pipeline and the "high impact" detection. Never present synthetic changes as real in the dashboard (use a `is_synthetic` flag and a visible badge).

**Day 5: Start labeling**
- Create `eval/datasets/changes_labeled.csv`: `change_id, topic(s), sector(s), impact, notes`.
- Label about 20 changes today; you'll finish by Week 6. Use a spreadsheet; no tool is required.

### Done when
- [ ] Every change has a validated enrichment row or an explicit failure row
- [ ] Rerunning `make enrich` hits the cache and makes no LLM calls
- [ ] Token and cost columns are populated

---

## 8. Phase 4 (Week 4): Embeddings, hybrid search, and RAG

### Goals
Cited question answering that refuses when it doesn't know.

### Day-by-day

**Day 1: Chunking + embeddings**
- Chunk by structure: one chunk per article paragraph group, ~200-400 tokens, never crossing article boundaries. Prefix each chunk with its breadcrumb, for example `GDPR > Article 17 > Right to erasure`.
- Embed with `multilingual-e5-small`. Remember the model's conventions: prefix passages with `passage: ` and queries with `query: `.
- Store in `chunks.embedding`; cache embeddings by text hash.
- Index only the **latest version** by default; keep a flag to search historical versions.

**Day 2: Hybrid retrieval**
- BM25 via DuckDB's full-text search extension + cosine similarity on embeddings.
- Merge with **Reciprocal Rank Fusion** (RRF). Return top-k with scores and section IDs.
- Add metadata filters (instrument, date range, section type).

**Day 3: Answer generation with citations**
- Prompt: answer only from the numbered context passages; every sentence must end with `[n]`; if the context doesn't contain the answer, reply exactly `NOT_FOUND`.
- Post-processing:
  - Parse citations, map `[n]` → `section_id` and source URL.
  - **Citation validator:** reject any citation not in the retrieved set.
  - **Refusal gate:** if the top retrieval score is below a threshold, don't call the LLM; return "not enough evidence" with the closest passages.
- Return a structured response: `answer`, `citations[]`, `confidence`, `retrieved[]`.

**Day 4: FastAPI**
- Endpoints: `GET /health`, `GET /changes`, `GET /changes/{id}`, `POST /ask`, `GET /freshness`.
- Pydantic response models, rate limit on `/ask`, CORS config, OpenAPI docs auto-generated.
- Tests with `TestClient` and a mock LLM.

**Day 5: Retrieval evaluation (early)**
- Write 40 questions with the correct source section(s). Compute hit@1/3/5 and MRR; tune chunk size, k, and RRF weights using these numbers.
- Add 10 **out-of-scope** questions (for example, about US law or unrelated topics) to test refusals.

### Done when
- [ ] `/ask` returns citations that resolve to real sections 100% of the time
- [ ] Out-of-scope questions are refused
- [ ] You have baseline retrieval metrics written down

---

## 9. Handling the "not enough real changes" risk

Do this in Week 2-3 so you aren't stuck at the end.

| Source of changes | How |
|---|---|
| **Consolidated version history** | Compare successive consolidated versions of the same act |
| **Amending acts and corrigenda** | Ingest the amending act and link it to the base act |
| **Proposed vs. adopted text** | Treat a Commission proposal and the final text as two versions of the same instrument (verify which instruments have proposals worth tracking, including any current omnibus-style amendment proposals) |
| **Different instruments, same theme** | Cross-reference definitions across GDPR, AI Act, and Data Act (a "terminology comparison" feature) |
| **Synthetic changes** | Clearly labeled test fixtures, used for pipeline tests only |

If after Week 3 you still have fewer than ~40 real changes, extend the corpus (add Digital Governance Act, Cyber Resilience Act, e-Privacy Directive, or the Cybersecurity Act) rather than faking data.

---

## 10. Phase 5 (Week 5): Dashboard, orchestration, alerts

### Goals
A shareable UI and a pipeline that runs itself.

### Day-by-day

**Day 1-2: Streamlit dashboard** (`dashboard/app.py` + `pages/`)

| Page | Content |
|---|---|
| **Overview** | KPIs (instruments tracked, changes in last 30/90 days, high-impact count), data freshness banner ("last successful ingest: …") |
| **Change timeline** | Filter by instrument, topic, sector, impact, date; table with summary; click to open detail |
| **Change detail** | Side-by-side diff (old vs. new, word-level highlights), AI summary, impact rating + rationale, link to official source, "AI-generated" badge |
| **Topic trends** | Changes per topic over time (Plotly), heatmap of instrument × topic |
| **Since I last looked** | Date picker → grouped list of changes since that date |
| **Ask** | Q&A box with citations rendered as links to sections |
| **Pipeline health** | Last runs, durations, failures, row counts, cost per run |

Design rules: keep a persistent disclaimer; show confidence and model/prompt version in an expandable "How was this generated?" box; cache queries with `st.cache_data`.

**Day 3: Orchestration**
- Dagster assets: `raw_versions → sections → changes → enrichments → chunks → dbt models`.
- Add an asset check for freshness and one for "no failed enrichments".
- Local schedule definition (weekly). This is the demo for interviews: show the lineage graph.

**Day 4: Free scheduled production run (GitHub Actions)**
- `.github/workflows/ingest.yml`:
  - `schedule: cron` weekly + `workflow_dispatch` for manual runs.
  - Steps: checkout → install → `regtracker ingest parse diff` → build dbt → export a **snapshot** (DuckDB file or Parquet files + embeddings) → upload to the Hugging Face dataset repo using a token stored in GitHub **Secrets**.
- Heavy LLM enrichment stays local: run it on your machine, then push the updated snapshot. (Alternatively, run a small model in Actions, but CPU runners are slow; test before committing to it.)
- Keep Actions runs short and deterministic; free minutes are generous for public repos but not infinite.

**Day 5: Alerts**
- Generate `feed.xml` (RSS) with the newest high/medium-impact changes.
- Optional email digest via SMTP using an app password stored as a secret.
- Add a failure notification (GitHub Actions already emails on failure; also write the failure into `pipeline_runs`).

### Done when
- [ ] Dashboard runs locally from a snapshot with one command
- [ ] A scheduled workflow completes successfully at least once on its own
- [ ] The RSS feed validates

---

## 11. Phase 6 (Week 6): Evaluation, deployment, polish

### 11.1 Evaluation (the part that sets you apart)

**Datasets**
- `changes_labeled.csv`: 60-100 real changes with gold topic(s), sector(s), impact.
- `qa_set.jsonl`: 40 in-scope questions with gold section(s) + 10 out-of-scope.
- Keep few-shot examples **out** of the eval sets. Freeze the sets before tuning on them, or split into dev/test.

**Metrics**

| Component | Metrics |
|---|---|
| Diff | Precision/recall of detected changes against a manually verified sample; renumbering false-positive rate |
| Classification | Topic F1 (micro/macro), sector F1, impact accuracy and "within one level" accuracy, confusion matrix |
| Summaries | Human rating 1-5 on faithfulness (20 samples); optional LLM-as-judge with the caveat that it is biased and not a replacement for human review |
| Retrieval | hit@1/3/5, MRR |
| Answers | Citation validity (must be 100%), citation correctness (cited section actually supports the claim, manually reviewed on 20), refusal accuracy on out-of-scope questions |
| System | Tokens/change, latency, shadow cost per 1,000 changes, pipeline runtime |

**Experiments worth reporting** (each a single table row)
1. Model A vs. Model B for classification (local 3B vs. 7B, plus one free-tier hosted model).
2. With vs. without few-shot examples.
3. Vector-only vs. BM25-only vs. hybrid retrieval.
4. Chunk size 200 vs. 400 tokens.

Write `docs/eval-report.md` with the tables, an honest "failure analysis" section (what went wrong and why), and known limitations.

### 11.2 Deployment (all free)

1. **Snapshot:** upload `warehouse.duckdb` (or Parquet + `embeddings.npy`) to a Hugging Face dataset repo.
2. **Streamlit Community Cloud:** connect the public GitHub repo, set `dashboard/app.py` as the entry point, store secrets (HF token if the dataset is private, free-tier LLM key) in the app's secrets settings. At startup, download the snapshot with `huggingface_hub` and cache it.
3. **Graceful degradation:** if the LLM rate limit is hit, the Ask page shows ranked passages with a note instead of an error.
4. **Optional API deploy:** Hugging Face Spaces (Docker SDK) with the FastAPI app.
5. **Smoke test:** add a CI job that starts the app against the fixture DB and checks the health endpoint.
6. **Security basics:** no secrets in the repo (add `gitleaks` or GitHub secret scanning), pinned dependencies, input length limits on `/ask`, simple per-IP rate limit.

### 11.3 Polish
- **README** structure: one-sentence pitch → screenshot/GIF → architecture diagram → features → quickstart (`make setup && make demo`) → design decisions (why deterministic diff, why DuckDB, why hybrid search) → evaluation summary table → limitations → disclaimer.
- **Demo video** (2-3 min): the problem, run the pipeline, show a diff with its AI summary, ask a question, show the lineage graph and eval results. Screen-record with any free tool (OBS).
- **Diagram:** draw with draw.io or Mermaid (renders natively on GitHub).
- Tag a `v1.0.0` release with a changelog.

### Done when
- [ ] Public dashboard URL works from a fresh browser
- [x] Eval report published with real numbers
- [ ] README lets a stranger run the project in under 10 minutes

---

## 12. Cross-cutting practices

### 12.1 Git workflow
- Trunk-based with short feature branches; Conventional Commits (`feat:`, `fix:`, `docs:`).
- One PR per weekly milestone even though you're solo; PR descriptions double as your project log.
- Protect `main` with required CI checks.

### 12.2 Testing pyramid

| Level | Examples | Network? |
|---|---|---|
| Unit | normalization, hashing, diff logic, citation validator | No |
| Component | parser on saved XHTML fixtures, enrichment with mock LLM | No |
| Integration | full pipeline on a 2-document fixture corpus | No (fixtures) |
| Smoke | app boots, `/health` OK | No |
| Manual / eval | real LLM, real data | Yes (never in CI) |

### 12.3 Observability
- Structured logging (JSON) with a `run_id` on every line.
- `pipeline_runs` table feeds the "Pipeline health" page.
- Track: rows in/out per stage, failures, tokens, cost, latency.

### 12.4 Data quality rules (implement as dbt/pytest tests)
- Every `section` belongs to a version that exists.
- `text_hash` is unique per `(version_id, section_key)`.
- No `modified` change with identical normalized text.
- Every enrichment has valid enum values.
- Every citation in an answer resolves to a stored section.
- Freshness: latest successful ingest is no older than 8 days.

### 12.5 Responsible-use checklist
- [ ] Disclaimer on README and every page that shows AI output
- [ ] AI-generated content visually labeled
- [ ] Official source link next to every summary
- [ ] Source license/reuse notice documented
- [ ] Polite crawling (user agent, rate limit, caching)
- [ ] No personal data collected; if you log questions, say so and don't store identifiers

---

## 13. Week-by-week checklist (print this)

**Week 0 (2 days): Setup**
- [x] Repo, tooling, CI, Ollama, ADR-001

**Week 1: Ingestion**
- [x] Cellar access understood, config file, HTTP client
- [x] Version discovery, download, hashing, idempotency
- [x] CLI + tests + `docs/sources.md`

**Week 2: Parse + diff + dbt**
- [x] Parser with golden counts
- [x] Normalization + diff engine + renumbering detection
- [x] dbt models + tests + freshness
- [x] Plan for sufficient real changes (section 9)

**Week 3: Enrichment**
- [x] LLM client with cache and logging
- [x] Pydantic schema + versioned prompt
- [x] Batch job + failure handling + shadow cost
- [x] 20 changes labeled

**Week 4: Retrieval + RAG**
- [x] Chunking + embeddings
- [x] Hybrid search with RRF
- [x] Cited answers + citation validator + refusal gate
- [x] FastAPI + tests
- [x] 40+10 question set and baseline metrics

**Week 5: Product**
- [x] Streamlit pages (replaced by the React web app, ADR-004)
- [x] Dagster assets + checks
- [x] GitHub Actions scheduled ingest + snapshot upload
- [x] RSS / email digest

**Week 6: Ship**
- [ ] Finish labeling, run all experiments
- [x] Eval report with failure analysis
- [ ] Deploy (Streamlit Cloud + HF snapshot)
- [ ] README, diagram, demo video, `v1.0.0`
- [ ] Resume bullets filled with real numbers

---

## 14. Risks and fallbacks

| Risk | Likelihood | Fallback |
|---|---|---|
| EUR-Lex access is blocked or rate-limited | Medium | Use Cellar content negotiation + caching; download once and work from fixtures |
| Document markup differs between instruments or versions | High | Parser adapter per markup variant; golden tests catch regressions early |
| Too few real changes | Medium-High | Section 9; widen the corpus |
| Local LLM too slow / too weak | Medium | Smaller model for classification; hosted free tier for summaries only; shorter inputs (send only the changed paragraphs) |
| Free-tier API rate limits or policy changes | Medium | Provider-agnostic client; local Ollama; degrade to retrieval-only |
| Streamlit Cloud app sleeps or resource limits | Medium | Keep the snapshot small (<~200 MB, ideally much less); lazy-load; a README GIF as backup |
| Scope creep | High | Freeze scope after Week 1; use the stretch list only after v1.0.0 |
| Evaluation labels are subjective | Medium | Write a one-page labeling guide; label twice a week apart on a 20-item subset and report your own agreement |

---

## 15. Stretch goals (only after v1.0.0)

1. **French summaries and French Q&A** using the multilingual embedding model and bilingual prompts; evaluate separately.
2. **Cross-instrument concept map:** how "high-risk", "personal data", or "provider" are defined across acts.
3. **Obligation extractor:** structured extraction of "who must do what by when" with deadlines (a timeline view of application dates).
4. **Swap DuckDB search for Postgres + pgvector** (free tiers exist, or run it locally in Docker) and write up the comparison.
5. **Langfuse (self-hosted or free cloud tier)** for LLM tracing.
6. **Feedback loop:** a "was this summary right?" button that feeds a correction table for future eval sets.
7. **MCP server** exposing your tracker to other AI tools.

---

## 16. Resume material (real numbers as of 2026-10-31)

**Title line:** *EU Regulation Change Tracker | Python, DuckDB, dbt, Dagster, FastAPI, React/TypeScript, LLMs (Groq), RAG, Docker, GitHub Actions*

- Built an idempotent pipeline tracking **14 EU digital regulations** (27 consolidated versions, 1,261 articles and annexes) from the EU Publications Office (SPARQL + Cellar), with deterministic article-level diffing that detected **107 real legal changes** without an LLM.
- Wrote a parser for two generations of EUR-Lex markup, validated on **27/27 versions** against independent article counts, with **0 remaining false-positive changes** in a manual audit after fixes.
- Designed LLM enrichment (plain-language summary, topic tags, impact rating) with schema-validated JSON, caching, token throttling and a daily budget: **0 of 82** outputs failed validation, at **1.8K tokens/change** and **$0.37 per 1,000 changes** (shadow cost).
- Built cited Q&A over **1,475 chunks** with hybrid BM25 + vector retrieval (RRF): **MRR 0.975** vs 0.869 (BM25) and 0.927 (vector), **100% hit@3**; a tuned refusal gate scored **25/25** on the held-out set.
- Shipped a React + FastAPI web app in one Docker image with rate-limited Q&A that degrades to retrieval-only, **215 automated tests** (152 Python, 17 frontend, 46 dbt), weekly GitHub Actions ingestion and 4 ADRs.

**CV version (French, matches the CV's project format):**

> **Veille réglementaire UE : suivi des lois numériques par IA** · Octobre 2026
> - Concevoir un **pipeline de données** (Python, DuckDB, dbt) sur 14 textes UE : **107** changements détectés sans LLM.
> - Construire un **RAG** hybride (BM25 + vecteurs) avec citations vérifiées : MRR de **0,975**, **25/25** refus corrects.
> - Déployer une app **FastAPI** et **React** sous **Docker**, **215** tests : **0,37** dollar pour 1 000 changements analysés.

Provisional until the draft labels and QA set are human-verified (see `docs/eval-report.md`); add the public URL once deployed.

**Interview talking points:** why the diff is deterministic and the LLM is not; how you prevented hallucinated citations; the renumbering false-positive problem; what your failure analysis revealed; how the system degrades without an LLM.

---

## Appendix A: Command cheat sheet

```bash
# setup
uv sync && pre-commit install && ollama pull qwen2.5:7b-instruct

# pipeline
regtracker ingest --all
regtracker parse --all
regtracker diff --all
regtracker enrich --model qwen2.5:7b-instruct --prompt-version v1
regtracker index --embed-model intfloat/multilingual-e5-small
dbt build --project-dir dbt

# apps
streamlit run dashboard/app.py
uvicorn regtracker.api.main:app --reload

# quality
ruff check . && ruff format --check . && mypy src && pytest -q
python eval/run_eval.py --suite all --out eval/reports/
```

## Appendix B: Environment variables (`.env`, never committed)

```
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b-instruct
LLM_API_KEY=ollama                 # placeholder for local
HOSTED_LLM_BASE_URL=               # free-tier provider (OpenAI-compatible)
HOSTED_LLM_API_KEY=
HF_TOKEN=                          # for snapshot upload/download
WAREHOUSE_PATH=data/warehouse.duckdb
USER_AGENT="eu-reg-tracker/0.1 (contact: you@example.com)"
```

## Appendix C: Labeling guide (one page, write it in Week 3)

- **Impact: low** → wording fix, clarification, formatting, cross-reference update.
- **Impact: medium** → changes obligations, scope, or definitions for a subset of actors; new exemptions.
- **Impact: high** → new or removed obligations, penalties, deadlines, or scope that affects many actors.
- When unsure between two levels, choose the lower one and note it in `notes`.
- A change can have 1-3 topics and 1-3 sectors; list the primary one first.
