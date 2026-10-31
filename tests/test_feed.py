import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from regtracker.app.feed import build_feed, validate_feed
from regtracker.app.publish import export_snapshot
from regtracker.common.fixture_db import build_fixture_db

FIXTURES = Path(__file__).parent / "fixtures" / "xhtml"


@pytest.fixture
def warehouse(tmp_path: Path) -> Path:
    path = tmp_path / "w.duckdb"
    build_fixture_db(path, FIXTURES)
    con = duckdb.connect(str(path))
    ids = [r[0] for r in con.execute("SELECT change_id FROM changes ORDER BY 1").fetchall()]
    for change_id, impact in zip(ids, ["high", "medium", "low"], strict=False):
        con.execute(
            "INSERT INTO enrichments (change_id, model, prompt_version, status, summary, topics, "
            "sectors, impact, impact_rationale, created_at) VALUES (?, 'm', 'v1', 'success', "
            "'S <&> x.', ['other'], ['telecom'], ?, 'R.', now())",
            [change_id, impact],
        )
    con.close()
    return path


def test_feed_has_only_notable_changes_and_is_valid(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    data = build_feed(con, "https://example.org", now=datetime(2026, 1, 1, tzinfo=UTC))
    con.close()

    assert validate_feed(data) == []
    items = ET.fromstring(data).findall("channel/item")
    assert len(items) == 2  # high + medium; low excluded
    assert all("Not legal advice" in (i.findtext("description") or "") for i in items)
    assert b"S &lt;&amp;&gt; x." in data  # text is escaped


def test_validate_feed_catches_problems() -> None:
    assert validate_feed(b"<rss version='2.0'><channel><item/></channel></rss>")


def test_export_snapshot(warehouse: Path, tmp_path: Path) -> None:
    files = export_snapshot(warehouse, tmp_path / "snap", "https://example.org")
    names = sorted(f.name for f in files)
    assert names == ["README.md", "feed.xml", "warehouse.duckdb"]
    con = duckdb.connect(str(tmp_path / "snap" / "warehouse.duckdb"), read_only=True)
    assert con.execute("SELECT count(*) FROM changes").fetchone() == (10,)
    con.close()
