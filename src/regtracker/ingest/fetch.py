"""Download consolidated versions, store raw XHTML immutably, record provenance.

Idempotency rules:
- a version already in `document_versions` is skipped without any network request;
- a download whose SHA-256 already exists for the same document is not stored twice;
- raw files are never overwritten; an existing file with different bytes is an error.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb

from regtracker.common.config import Instrument
from regtracker.common.http import PoliteClient
from regtracker.common.runs import log_run, new_run_id, utcnow
from regtracker.ingest.discover import ConsolidatedVersion, discover_versions

XHTML = "application/xhtml+xml"
LANGUAGE = "eng"  # Cellar expects ISO 639-3; two-letter codes return 404


class RawFileConflictError(Exception):
    """A raw file exists with different bytes. Raw files are immutable, so we stop."""


@dataclass
class IngestReport:
    doc_id: str
    discovered: int = 0
    new: int = 0
    already_known: int = 0
    duplicate_content: int = 0
    unavailable: list[str] = field(default_factory=list)  # "CELEX (HTTP 404)"
    error: str | None = None


def version_id(doc_id: str, version: ConsolidatedVersion) -> str:
    return f"{doc_id}@{version.version_date.isoformat()}"


def raw_path_for(raw_dir: Path, doc_id: str, version: ConsolidatedVersion) -> Path:
    return raw_dir / doc_id / f"{version.version_date.isoformat()}.xhtml"


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_raw_once(path: Path, content: bytes) -> None:
    """Write `content` to `path` unless it is already there. Never overwrites different bytes."""
    if path.exists():
        if sha256(path.read_bytes()) != sha256(content):
            raise RawFileConflictError(f"{path} exists with different content; not overwriting")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(content)
    tmp.replace(path)


def upsert_document(con: duckdb.DuckDBPyConnection, inst: Instrument) -> None:
    con.execute(
        "INSERT INTO documents (doc_id, celex_base, doc_type) VALUES (?, ?, ?) "
        "ON CONFLICT (doc_id) DO UPDATE SET celex_base = excluded.celex_base, "
        "doc_type = excluded.doc_type",
        [inst.doc_id, inst.celex_base, inst.doc_type],
    )


def _scalar_exists(con: duckdb.DuckDBPyConnection, sql: str, params: list[object]) -> bool:
    return con.execute(sql, params).fetchone() is not None


def ingest_instrument(
    con: duckdb.DuckDBPyConnection,
    client: PoliteClient,
    inst: Instrument,
    raw_dir: Path,
    now: Callable[[], datetime] = utcnow,
) -> IngestReport:
    """Discover, download and store every new version of one instrument."""
    report = IngestReport(doc_id=inst.doc_id)
    upsert_document(con, inst)
    versions = discover_versions(client, inst.celex_base)
    report.discovered = len(versions)

    for version in versions:
        vid = version_id(inst.doc_id, version)
        if _scalar_exists(con, "SELECT 1 FROM document_versions WHERE version_id = ?", [vid]):
            report.already_known += 1
            continue

        response = client.get(version.url, headers={"Accept": XHTML, "Accept-Language": LANGUAGE})
        content_type = response.headers.get("content-type", "")
        if not response.is_success or not content_type.startswith(XHTML):
            # 404: no English XHTML; 406: format not available. Record and move on.
            detail = f"HTTP {response.status_code}" if not response.is_success else content_type
            report.unavailable.append(f"{version.celex_version} ({detail})")
            continue

        content = response.content
        digest = sha256(content)
        if _scalar_exists(
            con,
            "SELECT 1 FROM document_versions WHERE doc_id = ? AND content_hash = ?",
            [inst.doc_id, digest],
        ):
            report.duplicate_content += 1
            continue

        path = raw_path_for(raw_dir, inst.doc_id, version)
        write_raw_once(path, content)
        con.execute(
            "INSERT INTO document_versions (version_id, doc_id, celex, version_date, source_url, "
            "fetched_at, content_hash, raw_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                vid,
                inst.doc_id,
                version.celex_version,
                version.version_date,
                version.url,
                now(),
                digest,
                path.as_posix(),
            ],
        )
        report.new += 1
    return report


def _log_ingest(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    report: IngestReport,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    problems = [f"unavailable: {', '.join(report.unavailable)}"] if report.unavailable else []
    if report.error:
        problems.insert(0, report.error)
    log_run(
        con,
        run_id=run_id,
        stage=f"ingest:{report.doc_id}",
        started_at=started_at,
        finished_at=finished_at,
        status="failed" if report.error else "success",
        rows_in=report.discovered,
        rows_out=report.new,
        error="; ".join(problems) or None,
    )


def ingest_all(
    con: duckdb.DuckDBPyConnection,
    client: PoliteClient,
    instruments: list[Instrument],
    raw_dir: Path,
    now: Callable[[], datetime] = utcnow,
) -> list[IngestReport]:
    """Ingest each instrument; one failure is logged and does not stop the others."""
    run_id = new_run_id()
    reports = []
    for inst in instruments:
        started = now()
        try:
            report = ingest_instrument(con, client, inst, raw_dir, now)
        except Exception as exc:  # logged to pipeline_runs, then reported by the caller
            report = IngestReport(doc_id=inst.doc_id, error=f"{type(exc).__name__}: {exc}")
        _log_ingest(con, run_id, report, started, now())
        reports.append(report)
    return reports
