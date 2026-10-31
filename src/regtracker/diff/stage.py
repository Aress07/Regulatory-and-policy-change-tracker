"""Diff stage: compare consecutive parsed versions of each document -> `changes` rows."""

from dataclasses import dataclass

import duckdb

from regtracker.common.runs import log_run, new_run_id, utcnow
from regtracker.diff.article_diff import SectionText, change_id, diff_sections


@dataclass
class DiffReport:
    doc_id: str
    from_version: str
    to_version: str
    changes: int = 0
    new: int = 0


def load_sections(con: duckdb.DuckDBPyConnection, version_id: str) -> list[SectionText]:
    rows = con.execute(
        "SELECT section_key, section_type, text, text_hash FROM sections "
        "WHERE version_id = ? ORDER BY position",
        [version_id],
    ).fetchall()
    return [SectionText(*r) for r in rows]


def version_pairs(
    con: duckdb.DuckDBPyConnection, doc_id: str | None = None
) -> list[tuple[str, str, str]]:
    """(doc_id, from_version, to_version) for consecutive parsed versions, oldest first."""
    sql = """
        WITH parsed AS (
          SELECT v.doc_id, v.version_id, v.version_date FROM document_versions v
          WHERE EXISTS (SELECT 1 FROM sections s WHERE s.version_id = v.version_id)
        )
        SELECT doc_id, prev, version_id FROM (
          SELECT doc_id, version_id, version_date,
                 lag(version_id) OVER (PARTITION BY doc_id ORDER BY version_date) AS prev
          FROM parsed
        ) WHERE prev IS NOT NULL
    """
    params: list[object] = []
    if doc_id:
        sql += " AND doc_id = ?"
        params.append(doc_id)
    return [
        tuple(r) for r in con.execute(sql + " ORDER BY doc_id, version_date", params).fetchall()
    ]


def diff_all(con: duckdb.DuckDBPyConnection, doc_id: str | None = None) -> list[DiffReport]:
    """Diff every consecutive pair. Deterministic ids make reruns insert nothing new."""
    run_id = new_run_id()
    reports: list[DiffReport] = []
    for doc, from_v, to_v in version_pairs(con, doc_id):
        started = utcnow()
        changes = diff_sections(load_sections(con, from_v), load_sections(con, to_v))
        before = _count(con, doc, from_v, to_v)
        rows = [
            [
                change_id(doc, from_v, to_v, c),
                doc,
                from_v,
                to_v,
                c.section_key,
                c.old_section_key,
                c.section_type,
                c.change_type,
                c.old_text,
                c.new_text,
                c.similarity,
                c.diff_html,
            ]
            for c in changes
        ]
        if rows:
            con.executemany(
                "INSERT INTO changes (change_id, doc_id, from_version, to_version, section_key, "
                "old_section_key, section_type, change_type, old_text, new_text, similarity, "
                "diff_html, is_synthetic) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE) "
                "ON CONFLICT (change_id) DO NOTHING",
                rows,
            )
        report = DiffReport(
            doc, from_v, to_v, len(changes), _count(con, doc, from_v, to_v) - before
        )
        log_run(
            con,
            run_id=run_id,
            stage=f"diff:{doc}",
            started_at=started,
            finished_at=utcnow(),
            status="success",
            rows_in=2,
            rows_out=report.new,
        )
        reports.append(report)
    return reports


def _count(con: duckdb.DuckDBPyConnection, doc: str, from_v: str, to_v: str) -> int:
    row = con.execute(
        "SELECT count(*) FROM changes WHERE doc_id = ? AND from_version = ? AND to_version = ?",
        [doc, from_v, to_v],
    ).fetchone()
    return int(row[0]) if row else 0
