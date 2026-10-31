from pathlib import Path

from regtracker.common.db import TABLES, connect, init_schema


def test_schema_is_idempotent(tmp_path: Path) -> None:
    con = connect(tmp_path / "w.duckdb")
    init_schema(con)
    init_schema(con)  # second run must not fail
    names = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert set(TABLES) <= names


def test_enrichment_primary_key_prevents_duplicates(tmp_path: Path) -> None:
    import duckdb
    import pytest

    con = connect(tmp_path / "w.duckdb")
    init_schema(con)
    sql = (
        "INSERT INTO enrichments (change_id, model, prompt_version, status) "
        "VALUES ('c1', 'm', 'v1', 'success')"
    )
    con.execute(sql)
    with pytest.raises(duckdb.ConstraintException):
        con.execute(sql)
