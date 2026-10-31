"""API tests: fixture warehouse, fake embedder and fake LLM (no network)."""

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from regtracker.api.main import RateLimiter, create_app
from regtracker.common.fixture_db import build_fixture_db
from regtracker.index.search import SearchIndex
from regtracker.index.stage import build_index
from regtracker.rag.answer import Answerer, RagConfig, source_urls
from tests.test_rag import FakeEmbedder, FakeLLM

FIXTURES = Path(__file__).parent / "fixtures" / "xhtml"


@pytest.fixture
def warehouse(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.duckdb"
    build_fixture_db(path, FIXTURES)
    con = duckdb.connect(str(path))
    build_index(con, FakeEmbedder())
    change_id = con.execute(
        "SELECT change_id FROM changes WHERE section_key = 'art_14a'"
    ).fetchone()[0]  # type: ignore[index]
    con.execute(
        "INSERT INTO enrichments (change_id, model, prompt_version, status, summary, topics, "
        "sectors, impact, impact_rationale, created_at) VALUES (?, 'm', 'v1', 'success', "
        "'A committee procedure is added.', ['other'], ['telecom'], 'low', 'Procedural.', now())",
        [change_id],
    )
    con.close()
    return path


def client_for(warehouse: Path, answers: list[str], limit: int = 10) -> TestClient:
    def factory(con: duckdb.DuckDBPyConnection) -> Answerer:
        return Answerer(
            SearchIndex.load(con), FakeEmbedder(), FakeLLM(answers), "m", source_urls(con),
            RagConfig(min_cosine=0.1),
        )  # fmt: skip

    app = create_app(warehouse, factory, RateLimiter(limit, 60))
    return TestClient(app)


def test_health_and_freshness(warehouse: Path) -> None:
    client = client_for(warehouse, [])
    assert client.get("/health").json() == {"status": "ok", "changes": 10}
    fresh = client.get("/freshness").json()
    assert fresh["days_since_ingest"] == 0 and fresh["failures_last_7_days"] == 0


def test_list_and_filter_changes(warehouse: Path) -> None:
    client = client_for(warehouse, [])
    changes = client.get("/changes").json()
    assert len(changes) == 10
    assert all(c["source_url"].endswith("CELEX:02002L0058-20091219") for c in changes)

    low = client.get("/changes", params={"impact": "low"}).json()
    assert [c["section_key"] for c in low] == ["art_14a"]
    assert low[0]["summary"] == "A committee procedure is added."
    assert client.get("/changes", params={"doc_id": "nope"}).json() == []
    assert client.get("/changes", params={"impact": "extreme"}).status_code == 422


def test_change_detail_and_404(warehouse: Path) -> None:
    client = client_for(warehouse, [])
    change_id = client.get("/changes").json()[0]["change_id"]
    detail = client.get(f"/changes/{change_id}").json()
    assert "diff_html" in detail and "new_text" in detail
    assert client.get("/changes/does-not-exist").status_code == 404


def test_ask_returns_validated_citations(warehouse: Path) -> None:
    client = client_for(warehouse, ["Subscribers may receive non-itemised bills [1]."])
    body = client.post("/ask", json={"question": "Can subscribers get non-itemised bills?"}).json()
    assert body["status"] == "answered"
    assert body["citations"][0]["section_id"] == body["retrieved"][0]["section_id"]
    assert "Not legal advice" in body["disclaimer"]


def test_ask_input_limits_and_rate_limit(warehouse: Path) -> None:
    client = client_for(warehouse, ["A [1]."] * 5, limit=2)
    assert client.post("/ask", json={"question": "x" * 501}).status_code == 422
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "bills?"}).status_code == 200
    assert client.post("/ask", json={"question": "bills?"}).status_code == 200
    assert client.post("/ask", json={"question": "bills?"}).status_code == 429


def test_rate_limiter_window() -> None:
    now = {"t": 0.0}
    limiter = RateLimiter(2, 60, clock=lambda: now["t"])
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a")
    assert limiter.allow("b")
    now["t"] = 61
    assert limiter.allow("a")
