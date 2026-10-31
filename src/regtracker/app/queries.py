"""Read-only queries behind the dashboard. Pages call these; they hold no SQL themselves."""

from datetime import date
from typing import Any

import duckdb
import pandas as pd

EURLEX = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:"

_CHANGES = f"""
    WITH latest AS (
      SELECT * FROM enrichments WHERE status = 'success'
      QUALIFY row_number() OVER (PARTITION BY change_id ORDER BY created_at DESC) = 1
    ),
    failed AS (
      SELECT DISTINCT change_id FROM enrichments WHERE status = 'failed'
    )
    SELECT c.change_id, c.doc_id, coalesce(d.short_name, c.doc_id) AS instrument,
           c.section_key, c.old_section_key, c.section_type, c.change_type,
           c.from_version, c.to_version, fv.version_date AS from_date, tv.version_date AS to_date,
           coalesce(c.is_synthetic, false) AS is_synthetic,
           '{EURLEX}' || tv.celex AS source_url,
           coalesce(ns.heading, os.heading) AS heading,
           e.summary, e.topics, e.sectors, e.impact, e.impact_rationale,
           e.model AS enrichment_model, e.prompt_version, e.created_at AS enriched_at,
           e.change_id IS NOT NULL AS is_enriched,
           f.change_id IS NOT NULL AND e.change_id IS NULL AS enrichment_failed,
           c.similarity
    FROM changes c
    JOIN documents d USING (doc_id)
    JOIN document_versions fv ON fv.version_id = c.from_version
    JOIN document_versions tv ON tv.version_id = c.to_version
    LEFT JOIN sections ns ON ns.section_id = c.to_version || '#' || c.section_key
    LEFT JOIN sections os ON os.section_id = c.from_version || '#' || c.old_section_key
    LEFT JOIN latest e USING (change_id)
    LEFT JOIN failed f USING (change_id)
"""


def changes(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """All detected changes with their latest successful enrichment (if any)."""
    return con.execute(f"{_CHANGES} ORDER BY to_date DESC, instrument, section_key").df()


def change_detail(con: duckdb.DuckDBPyConnection, change_id: str) -> dict[str, Any] | None:
    cur = con.execute(
        f"SELECT x.*, c.old_text, c.new_text, c.diff_html FROM ({_CHANGES}) x "
        "JOIN changes c USING (change_id) WHERE x.change_id = ?",
        [change_id],
    )
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cur.description], row, strict=True))


def documents(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        f"""
        SELECT d.doc_id, coalesce(d.short_name, d.doc_id) AS instrument, d.celex_base, d.doc_type,
               count(*) FILTER (WHERE v.parse_status = 'parsed') AS versions,
               max(v.version_date) FILTER (WHERE v.parse_status = 'parsed') AS latest_version,
               bool_or(v.parse_status = 'repealed') AS repealed,
               '{EURLEX}' || d.celex_base AS source_url
        FROM documents d LEFT JOIN document_versions v USING (doc_id)
        GROUP BY ALL ORDER BY instrument
        """
    ).df()


def freshness(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    row = con.execute(
        "SELECT max(finished_at) FILTER (WHERE stage LIKE 'ingest:%' AND status = 'success'), "
        "count(*) FILTER (WHERE status = 'failed' AND finished_at > now() - INTERVAL 7 DAY) "
        "FROM pipeline_runs"
    ).fetchone()
    last, failures = row if row else (None, 0)
    return {"last_successful_ingest": last, "failures_last_7_days": failures}


def pipeline_runs(con: duckdb.DuckDBPyConnection, limit: int = 500) -> pd.DataFrame:
    return con.execute(
        "SELECT split_part(stage, ':', 1) AS stage, "
        "nullif(split_part(stage, ':', 2), '') AS subject, "
        "status, started_at, finished_at, "
        "datediff('millisecond', started_at, finished_at) / 1000.0 AS seconds, "
        "rows_in, rows_out, error, run_id "
        "FROM pipeline_runs ORDER BY started_at DESC LIMIT ?",
        [limit],
    ).df()


def llm_usage(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Per model and prompt version: enrichments, tokens, shadow cost (cache hits included once)."""
    return con.execute(
        "SELECT model, prompt_version, count(*) FILTER (WHERE status = 'success') AS succeeded, "
        "count(*) FILTER (WHERE status = 'failed') AS failed, "
        "sum(tokens_in) AS tokens_in, sum(tokens_out) AS tokens_out, "
        "round(avg(tokens_in + tokens_out)) AS tokens_per_change, "
        "round(sum(shadow_cost_usd), 4) AS shadow_cost_usd, "
        "round(1000 * avg(shadow_cost_usd), 4) AS shadow_cost_per_1000_changes, "
        "round(median(latency_ms)) AS median_latency_ms "
        "FROM enrichments GROUP BY ALL ORDER BY model, prompt_version"
    ).df()


def topic_counts(frame: pd.DataFrame) -> pd.DataFrame:
    """Explode enriched, real changes into one row per (instrument, year, topic)."""
    enriched = frame[frame["is_enriched"] & ~frame["is_synthetic"]].copy()
    if enriched.empty:
        return pd.DataFrame(columns=["instrument", "year", "topic", "changes"])
    enriched["year"] = pd.to_datetime(enriched["to_date"]).dt.year
    exploded = enriched.explode("topics").rename(columns={"topics": "topic"})
    return exploded.groupby(["instrument", "year", "topic"]).size().reset_index(name="changes")


def changes_since(frame: pd.DataFrame, since: date) -> pd.DataFrame:
    return frame[pd.to_datetime(frame["to_date"]).dt.date >= since]
