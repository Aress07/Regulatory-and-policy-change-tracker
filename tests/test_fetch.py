from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import duckdb
import httpx
import pytest
from tenacity import wait_none

from regtracker.common.config import Instrument, Settings
from regtracker.common.db import connect, init_schema
from regtracker.common.http import PoliteClient, RateLimiter
from regtracker.ingest.fetch import (
    RawFileConflictError,
    ingest_all,
    write_raw_once,
)

AI_ACT = Instrument(doc_id="ai_act", celex_base="32024R1689", doc_type="regulation")
GDPR = Instrument(doc_id="gdpr", celex_base="32016R0679", doc_type="regulation")
VERSIONS = {
    "32024R1689": ["02024R1689-20240712", "02024R1689-20260727"],
    "32016R0679": ["02016R0679-20160504"],
}
XHTML = "application/xhtml+xml;charset=UTF-8"
FIXED_NOW = datetime(2026, 10, 31, 12, 0, 0)

Handler = Callable[[httpx.Request], httpx.Response]


def sparql_response(request: httpx.Request) -> httpx.Response:
    query = request.url.params["query"]
    base = next(b for b in VERSIONS if f'"{b}"' in query)
    bindings = [{"celex": {"type": "literal", "value": c}} for c in VERSIONS[base]]
    return httpx.Response(200, json={"results": {"bindings": bindings}})


def server(documents: dict[str, httpx.Response], log: list[str]) -> Handler:
    """Fake Cellar: SPARQL plus one response per version CELEX."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sparql"):
            log.append("sparql")
            return sparql_response(request)
        celex = request.url.path.rsplit("/", 1)[-1]
        log.append(celex)
        assert request.headers["accept-language"] == "eng"
        return documents[celex]

    return handler


def doc(body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body, headers={"content-type": XHTML})


@pytest.fixture
def con(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    c = connect(tmp_path / "w.duckdb")
    init_schema(c)
    yield c
    c.close()


def run(
    con: duckdb.DuckDBPyConnection,
    handler: Handler,
    raw_dir: Path,
    instruments: list[Instrument] | None = None,
) -> list:  # type: ignore[type-arg]
    client = PoliteClient(
        Settings(user_agent="test-agent"),
        cache_dir=None,
        transport=httpx.MockTransport(handler),
        rate_limiter=RateLimiter(0),
        wait=wait_none(),
    )
    with client:
        return ingest_all(con, client, instruments or [AI_ACT], raw_dir, now=lambda: FIXED_NOW)


def test_first_run_stores_files_rows_and_run_log(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    raw = tmp_path / "raw"
    docs = {
        "02024R1689-20240712": doc(b"<html>v1</html>"),
        "02024R1689-20260727": doc(b"<html>v2</html>"),
    }
    [report] = run(con, server(docs, []), raw)

    assert (report.discovered, report.new) == (2, 2)
    assert (raw / "ai_act" / "2024-07-12.xhtml").read_bytes() == b"<html>v1</html>"
    rows = con.execute(
        "SELECT version_id, celex, CAST(version_date AS VARCHAR), raw_path, content_hash "
        "FROM document_versions ORDER BY version_date"
    ).fetchall()
    assert [r[0] for r in rows] == ["ai_act@2024-07-12", "ai_act@2026-07-27"]
    assert rows[0][1] == "02024R1689-20240712"
    assert rows[0][3].endswith("raw/ai_act/2024-07-12.xhtml")
    assert len(rows[0][4]) == 64
    assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)
    run_row = con.execute("SELECT stage, status, rows_in, rows_out FROM pipeline_runs").fetchone()
    assert run_row == ("ingest:ai_act", "success", 2, 2)


def test_second_run_downloads_nothing(con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    docs = {"02024R1689-20240712": doc(b"a"), "02024R1689-20260727": doc(b"b")}
    run(con, server(docs, []), tmp_path)

    log: list[str] = []
    [report] = run(con, server(docs, log), tmp_path)

    assert (report.new, report.already_known) == (0, 2)
    assert log == ["sparql"]  # discovery only; no document downloads
    assert con.execute("SELECT count(*) FROM document_versions").fetchone() == (2,)
    assert con.execute("SELECT count(*) FROM pipeline_runs").fetchone() == (2,)


def test_new_version_is_picked_up_on_rerun(
    con: duckdb.DuckDBPyConnection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs = {"02024R1689-20240712": doc(b"a"), "02024R1689-20260727": doc(b"b")}
    monkeypatch.setitem(VERSIONS, "32024R1689", ["02024R1689-20240712"])
    run(con, server(docs, []), tmp_path)
    monkeypatch.setitem(VERSIONS, "32024R1689", ["02024R1689-20240712", "02024R1689-20260727"])

    [report] = run(con, server(docs, []), tmp_path)
    assert (report.new, report.already_known) == (1, 1)


def test_missing_language_or_format_is_reported_not_fatal(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    docs = {
        "02024R1689-20240712": httpx.Response(404),
        "02024R1689-20260727": doc(b"b"),
    }
    [report] = run(con, server(docs, []), tmp_path)

    assert report.new == 1
    assert report.unavailable == ["02024R1689-20240712 (HTTP 404)"]
    status, error = con.execute("SELECT status, error FROM pipeline_runs").fetchone()  # type: ignore[misc]
    assert status == "success"
    assert "02024R1689-20240712" in error


def test_wrong_content_type_is_not_stored(con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    docs = {
        "02024R1689-20240712": httpx.Response(
            200, content=b"%PDF", headers={"content-type": "application/pdf"}
        ),
        "02024R1689-20260727": doc(b"b"),
    }
    [report] = run(con, server(docs, []), tmp_path)

    assert report.new == 1
    assert report.unavailable == ["02024R1689-20240712 (application/pdf)"]
    assert not (tmp_path / "ai_act" / "2024-07-12.xhtml").exists()


def test_retries_transient_server_error(con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    flaky = iter([httpx.Response(503), doc(b"a")])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sparql"):
            return sparql_response(request)
        return next(flaky)

    [report] = run(con, handler, tmp_path, [GDPR])
    assert report.new == 1


def test_identical_content_is_not_stored_twice(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    docs = {"02024R1689-20240712": doc(b"same"), "02024R1689-20260727": doc(b"same")}
    [report] = run(con, server(docs, []), tmp_path)

    assert (report.new, report.duplicate_content) == (1, 1)
    assert not (tmp_path / "ai_act" / "2026-07-27.xhtml").exists()


def test_existing_raw_file_with_other_bytes_fails_that_doc_only(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    conflicting = tmp_path / "ai_act" / "2024-07-12.xhtml"
    conflicting.parent.mkdir(parents=True)
    conflicting.write_bytes(b"older bytes")
    docs = {
        "02024R1689-20240712": doc(b"new bytes"),
        "02024R1689-20260727": doc(b"b"),
        "02016R0679-20160504": doc(b"g"),
    }

    ai, gdpr = run(con, server(docs, []), tmp_path, [AI_ACT, GDPR])

    assert ai.error is not None and "RawFileConflictError" in ai.error
    assert conflicting.read_bytes() == b"older bytes"  # never overwritten
    assert gdpr.new == 1  # other instruments still ingested
    statuses = dict(con.execute("SELECT stage, status FROM pipeline_runs").fetchall())
    assert statuses == {"ingest:ai_act": "failed", "ingest:gdpr": "success"}


def test_write_raw_once_is_idempotent_and_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "d" / "2024-01-01.xhtml"
    write_raw_once(path, b"x")
    write_raw_once(path, b"x")  # same bytes: fine
    with pytest.raises(RawFileConflictError):
        write_raw_once(path, b"y")
    assert path.read_bytes() == b"x"
    assert not list(path.parent.glob("*.part"))
