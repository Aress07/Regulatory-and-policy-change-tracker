"""Write one `pipeline_runs` row per stage execution."""

import uuid
from datetime import UTC, datetime

import duckdb


def utcnow() -> datetime:
    """Naive UTC timestamp (DuckDB TIMESTAMP has no time zone)."""
    return datetime.now(UTC).replace(tzinfo=None)


def new_run_id() -> str:
    return uuid.uuid4().hex


def log_run(
    con: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    stage: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    rows_in: int,
    rows_out: int,
    error: str | None = None,
) -> None:
    con.execute(
        "INSERT INTO pipeline_runs (run_id, stage, started_at, finished_at, status, rows_in, "
        "rows_out, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [run_id, stage, started_at, finished_at, status, rows_in, rows_out, error],
    )
