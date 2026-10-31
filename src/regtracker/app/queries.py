"""Read-only queries behind the API and the feed. All filtering happens in SQL with bound
parameters; results are plain dicts ready for JSON."""

from dataclasses import dataclass
from datetime import date
from typing import Any

import duckdb

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


def records(
    con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None
) -> list[dict[str, Any]]:
    cur = con.execute(sql, params or [])
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


@dataclass(frozen=True)
class ChangeFilters:
    doc_ids: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    sectors: tuple[str, ...] = ()
    impacts: tuple[str, ...] = ()  # low | medium | high | unrated
    change_types: tuple[str, ...] = ()
    date_from: date | None = None
    date_to: date | None = None
    include_synthetic: bool = False
    limit: int = 500
    offset: int = 0


def changes(con: duckdb.DuckDBPyConnection, f: ChangeFilters | None = None) -> list[dict[str, Any]]:
    """Detected changes with their latest successful enrichment, newest first."""
    f = f or ChangeFilters()
    where: list[str] = []
    params: list[Any] = []
    if f.doc_ids:
        where.append("doc_id IN (SELECT unnest(?::VARCHAR[]))")
        params.append(list(f.doc_ids))
    if f.topics:
        where.append("len(list_intersect(coalesce(topics, []), ?::VARCHAR[])) > 0")
        params.append(list(f.topics))
    if f.sectors:
        where.append("len(list_intersect(coalesce(sectors, []), ?::VARCHAR[])) > 0")
        params.append(list(f.sectors))
    if f.impacts:
        rated = [i for i in f.impacts if i != "unrated"]
        clause = "impact IN (SELECT unnest(?::VARCHAR[]))"
        params.append(rated)
        if "unrated" in f.impacts:
            clause = f"({clause} OR impact IS NULL)"
        where.append(clause)
    if f.change_types:
        where.append("change_type IN (SELECT unnest(?::VARCHAR[]))")
        params.append(list(f.change_types))
    if f.date_from:
        where.append("to_date >= ?")
        params.append(f.date_from)
    if f.date_to:
        where.append("to_date <= ?")
        params.append(f.date_to)
    if not f.include_synthetic:
        where.append("NOT is_synthetic")
    sql = f"SELECT * FROM ({_CHANGES}) x"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY to_date DESC, instrument, section_key LIMIT ? OFFSET ?"
    return records(con, sql, [*params, int(f.limit), int(f.offset)])


def change_detail(con: duckdb.DuckDBPyConnection, change_id: str) -> dict[str, Any] | None:
    rows = records(
        con,
        f"SELECT x.*, c.old_text, c.new_text, c.diff_html FROM ({_CHANGES}) x "
        "JOIN changes c USING (change_id) WHERE x.change_id = ?",
        [change_id],
    )
    return rows[0] if rows else None


def documents(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return records(
        con,
        f"""
        SELECT d.doc_id, coalesce(d.short_name, d.doc_id) AS instrument, d.title, d.celex_base,
               d.doc_type,
               count(v.version_id) FILTER (WHERE v.parse_status = 'parsed') AS versions,
               max(v.version_date) FILTER (WHERE v.parse_status = 'parsed') AS latest_version,
               coalesce(bool_or(v.parse_status = 'repealed'), false) AS repealed,
               (SELECT count(*) FROM changes c WHERE c.doc_id = d.doc_id
                  AND NOT coalesce(c.is_synthetic, false)) AS changes,
               '{EURLEX}' || d.celex_base AS source_url
        FROM documents d LEFT JOIN document_versions v USING (doc_id)
        GROUP BY ALL ORDER BY instrument
        """,
    )


def freshness(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    row = con.execute(
        "SELECT max(finished_at) FILTER (WHERE stage LIKE 'ingest:%' AND status = 'success'), "
        "count(*) FILTER (WHERE status = 'failed' AND finished_at > now() - INTERVAL 7 DAY) "
        "FROM pipeline_runs"
    ).fetchone()
    last, failures = row if row else (None, 0)
    return {"last_successful_ingest": last, "failures_last_7_days": int(failures or 0)}


def overview(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    row = con.execute(
        f"""
        SELECT (SELECT count(*) FROM documents),
               (SELECT count(*) FROM document_versions WHERE parse_status = 'parsed'),
               count(*),
               count(*) FILTER (WHERE impact = 'high'),
               count(*) FILTER (WHERE is_enriched),
               max(to_date)
        FROM ({_CHANGES}) x WHERE NOT is_synthetic
        """
    ).fetchone()
    instruments, versions, total, high, enriched, latest = row or (0, 0, 0, 0, 0, None)
    by_type = records(
        con,
        f"SELECT instrument, change_type, count(*) AS changes FROM ({_CHANGES}) x "
        "WHERE NOT is_synthetic GROUP BY ALL ORDER BY instrument, change_type",
    )
    return {
        "instruments": instruments,
        "versions_parsed": versions,
        "changes": total,
        "high_impact": high,
        "enriched": enriched,
        "latest_change_date": latest,
        "changes_by_instrument_and_type": by_type,
    }


def topic_counts(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """One row per (instrument, year, topic) over enriched, real changes."""
    return records(
        con,
        f"""
        SELECT instrument, year(to_date) AS year, topic, count(*) AS changes
        FROM (SELECT instrument, to_date, unnest(topics) AS topic FROM ({_CHANGES}) x
              WHERE is_enriched AND NOT is_synthetic)
        GROUP BY ALL ORDER BY year, instrument, topic
        """,
    )


def pipeline_runs(
    con: duckdb.DuckDBPyConnection,
    stage: str | None = None,
    only_failed: bool = False,
    limit: int = 500,
) -> list[dict[str, Any]]:
    where, params = ["1=1"], []
    if stage:
        where.append("split_part(stage, ':', 1) = ?")
        params.append(stage)
    if only_failed:
        where.append("status = 'failed'")
    return records(
        con,
        "SELECT split_part(stage, ':', 1) AS stage, "
        "nullif(split_part(stage, ':', 2), '') AS subject, status, started_at, finished_at, "
        "datediff('millisecond', started_at, finished_at) / 1000.0 AS seconds, "
        "rows_in, rows_out, error, run_id "
        f"FROM pipeline_runs WHERE {' AND '.join(where)} ORDER BY started_at DESC LIMIT ?",
        [*params, int(limit)],
    )


def llm_usage(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Per model and prompt version: enrichments, tokens, shadow cost."""
    return records(
        con,
        "SELECT model, prompt_version, count(*) FILTER (WHERE status = 'success') AS succeeded, "
        "count(*) FILTER (WHERE status = 'failed') AS failed, "
        "sum(tokens_in) AS tokens_in, sum(tokens_out) AS tokens_out, "
        "round(avg(tokens_in + tokens_out)) AS tokens_per_change, "
        "round(sum(shadow_cost_usd), 4) AS shadow_cost_usd, "
        "round(1000 * avg(shadow_cost_usd), 4) AS shadow_cost_per_1000_changes, "
        "round(median(latency_ms)) AS median_latency_ms "
        "FROM enrichments GROUP BY ALL ORDER BY model, prompt_version",
    )
