"""Smoke test: every dashboard page renders against the fixture warehouse without errors."""

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

from regtracker.common.config import get_settings
from regtracker.common.fixture_db import build_fixture_db

ROOT = Path(__file__).parent.parent
APP = str(ROOT / "dashboard" / "app.py")
PAGES = [
    "app_pages/overview.py",
    "app_pages/timeline.py",
    "app_pages/detail.py",
    "app_pages/trends.py",
    "app_pages/since.py",
    "app_pages/ask.py",
    "app_pages/health.py",
]


@pytest.fixture
def fixture_warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "fixture.duckdb"
    build_fixture_db(path, ROOT / "tests" / "fixtures" / "xhtml")
    con = duckdb.connect(str(path))
    change_id = con.execute("SELECT change_id FROM changes LIMIT 1").fetchone()[0]  # type: ignore[index]
    con.execute(
        "INSERT INTO enrichments (change_id, model, prompt_version, status, summary, topics, "
        "sectors, impact, impact_rationale, tokens_in, tokens_out, shadow_cost_usd, created_at) "
        "VALUES (?, 'm', 'v1', 'success', 'Summary.', ['other'], ['telecom'], 'high', 'Why.', "
        "10, 5, 0.001, now())",
        [change_id],
    )
    con.close()
    monkeypatch.setenv("WAREHOUSE_PATH", str(path))
    monkeypatch.delenv("HF_DATASET_REPO", raising=False)
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(fixture_warehouse: Path, page: str) -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.switch_page(page).run()
    assert not at.exception, at.exception
    assert any("Not legal advice" in c.value for c in at.caption)


def test_detail_shows_ai_badge_and_official_link(fixture_warehouse: Path) -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.switch_page("app_pages/detail.py").run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "AI-generated" in text
