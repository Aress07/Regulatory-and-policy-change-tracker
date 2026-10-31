"""DuckDB connection and schema. Foreign keys are documented, not enforced."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  doc_id VARCHAR PRIMARY KEY,
  celex_base VARCHAR NOT NULL,
  title VARCHAR,
  doc_type VARCHAR,
  language VARCHAR DEFAULT 'EN'
);

CREATE TABLE IF NOT EXISTS document_versions (
  version_id VARCHAR PRIMARY KEY,        -- doc_id || '@' || version_date
  doc_id VARCHAR NOT NULL,               -- -> documents.doc_id
  celex VARCHAR NOT NULL,
  version_date DATE,
  source_url VARCHAR NOT NULL,
  fetched_at TIMESTAMP NOT NULL,
  content_hash VARCHAR NOT NULL,
  raw_path VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
  section_id VARCHAR PRIMARY KEY,        -- version_id || '#' || section_key
  version_id VARCHAR NOT NULL,           -- -> document_versions.version_id
  section_key VARCHAR NOT NULL,          -- art_5 | rct_12 | annex_III
  section_type VARCHAR NOT NULL,         -- article | recital | annex
  number VARCHAR,
  heading VARCHAR,
  text VARCHAR NOT NULL,
  text_hash VARCHAR NOT NULL,
  position INTEGER
);

CREATE TABLE IF NOT EXISTS changes (
  change_id VARCHAR PRIMARY KEY,
  doc_id VARCHAR NOT NULL,
  from_version VARCHAR NOT NULL,
  to_version VARCHAR NOT NULL,
  section_key VARCHAR NOT NULL,
  change_type VARCHAR NOT NULL,          -- added | removed | modified | renumbered
  old_text VARCHAR,
  new_text VARCHAR,
  similarity DOUBLE,
  diff_html VARCHAR,
  is_synthetic BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS enrichments (
  change_id VARCHAR NOT NULL,
  model VARCHAR NOT NULL,
  prompt_version VARCHAR NOT NULL,
  status VARCHAR NOT NULL,               -- success | failed
  summary VARCHAR,
  topics VARCHAR[],
  sectors VARCHAR[],
  impact VARCHAR,
  impact_rationale VARCHAR,
  error VARCHAR,
  tokens_in INTEGER,
  tokens_out INTEGER,
  latency_ms INTEGER,
  shadow_cost_usd DOUBLE,
  created_at TIMESTAMP,
  PRIMARY KEY (change_id, model, prompt_version)
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id VARCHAR PRIMARY KEY,
  section_id VARCHAR NOT NULL,
  text VARCHAR NOT NULL,
  embedding FLOAT[384]
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id VARCHAR NOT NULL,
  stage VARCHAR NOT NULL,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  status VARCHAR,                        -- success | failed | skipped
  rows_in INTEGER,
  rows_out INTEGER,
  error VARCHAR
);
"""

TABLES = [
    "documents",
    "document_versions",
    "sections",
    "changes",
    "enrichments",
    "chunks",
    "pipeline_runs",
]


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA)


@contextmanager
def warehouse(path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(path)
    try:
        init_schema(con)
        yield con
    finally:
        con.close()
