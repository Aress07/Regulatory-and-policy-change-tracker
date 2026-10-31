"""Parse stage: raw XHTML of every unparsed version -> `sections` rows.

`document_versions.parse_status` records the outcome: `parsed`, `repealed` (a repeal notice with no
text; `repealed_by` holds the repealing acts) or `failed` (retried on the next run).
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb

from regtracker.common.runs import log_run, new_run_id, utcnow
from regtracker.parse.xhtml_parser import ParsedDocument, parse_document


@dataclass
class ParseReport:
    version_id: str
    sections: int = 0
    variant: str | None = None
    error: str | None = None


def store_parsed(
    con: duckdb.DuckDBPyConnection, version_id: str, doc_id: str, parsed: ParsedDocument
) -> None:
    """Insert all sections of one version and mark it parsed, in one transaction."""
    rows = [
        [
            f"{version_id}#{s.section_key}",
            version_id,
            s.section_key,
            s.section_type,
            s.number,
            s.heading,
            s.text,
            s.text_hash,
            s.position,
            s.amended_by,
        ]
        for s in parsed.sections
    ]
    status = "repealed" if parsed.variant == "repealed" else "parsed"
    con.execute("BEGIN TRANSACTION")
    try:
        if rows:
            con.executemany(
                "INSERT INTO sections (section_id, version_id, section_key, section_type, number, "
                "heading, text, text_hash, position, amended_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        con.execute(
            "UPDATE document_versions SET parse_status = ?, repealed_by = ? WHERE version_id = ?",
            [status, parsed.repealed_by or None, version_id],
        )
        if parsed.title:
            con.execute(
                "UPDATE documents SET title = ? WHERE doc_id = ? AND title IS NULL",
                [parsed.title, doc_id],
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def clear_derived(con: duckdb.DuckDBPyConnection, doc_id: str | None = None) -> None:
    """Drop sections and changes (rebuilt from immutable raw files) so they can be re-parsed.

    Enrichments are kept: they are keyed by change_id, which is deterministic, so they reattach
    to identical changes after a rebuild.
    """
    where, params = ("WHERE doc_id = ?", [doc_id]) if doc_id else ("", [])
    con.execute(f"DELETE FROM changes {where}", params)
    con.execute(
        "DELETE FROM sections WHERE version_id IN "
        f"(SELECT version_id FROM document_versions {where})",
        params,
    )
    con.execute(
        f"UPDATE document_versions SET parse_status = NULL, repealed_by = NULL {where}", params
    )


def parse_pending(
    con: duckdb.DuckDBPyConnection,
    doc_id: str | None = None,
    base_dir: Path = Path("."),
    force: bool = False,
) -> list[ParseReport]:
    """Parse versions not yet parsed (or that failed before). Idempotent.

    `force=True` first clears sections and changes, e.g. after a parser fix.
    """
    if force:
        clear_derived(con, doc_id)
    sql = (
        "SELECT version_id, doc_id, raw_path FROM document_versions "
        "WHERE coalesce(parse_status, 'failed') = 'failed'"
    )
    params: list[object] = []
    if doc_id:
        sql += " AND doc_id = ?"
        params.append(doc_id)
    pending = con.execute(sql + " ORDER BY doc_id, version_date", params).fetchall()

    run_id = new_run_id()
    reports: list[ParseReport] = []
    for version_id, version_doc, raw_path in pending:
        started = utcnow()
        report = ParseReport(version_id)
        try:
            parsed = parse_document((base_dir / raw_path).read_bytes())
            store_parsed(con, version_id, version_doc, parsed)
            report.sections, report.variant = len(parsed.sections), parsed.variant
        except Exception as exc:  # recorded in pipeline_runs; other versions continue
            report.error = f"{type(exc).__name__}: {exc}"
            con.execute(
                "UPDATE document_versions SET parse_status = 'failed' WHERE version_id = ?",
                [version_id],
            )
        log_run(
            con,
            run_id=run_id,
            stage=f"parse:{version_id}",
            started_at=started,
            finished_at=utcnow(),
            status="failed" if report.error else "success",
            rows_in=1,
            rows_out=report.sections,
            error=report.error,
        )
        reports.append(report)
    return reports
