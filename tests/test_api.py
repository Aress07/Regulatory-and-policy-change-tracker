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
        "sectors, impact, impact_rationale, tokens_in, tokens_out, latency_ms, shadow_cost_usd, "
        "created_at) VALUES (?, 'm', 'v1', 'success', 'A committee procedure is added.', "
        "['other'], ['telecom'], 'low', 'Procedural.', 10, 5, 100, 0.001, now())",
        [change_id],
    )
    con.close()
    return path


def client_for(
    warehouse: Path,
    answers: list[str] | None = None,
    limit: int = 10,
    daily: int = 100,
    dist: Path | None = None,
) -> TestClient:
    def factory(con: duckdb.DuckDBPyConnection) -> Answerer:
        return Answerer(
            SearchIndex.load(con), FakeEmbedder(), FakeLLM(answers or []), "m",
            source_urls(con), RagConfig(min_cosine=0.1),
        )  # fmt: skip

    app = create_app(
        warehouse, factory, RateLimiter(limit, 60), RateLimiter(daily, 86400),
        frontend_dist=dist or Path("does-not-exist"),
    )  # fmt: skip
    return TestClient(app)


def test_health_meta_freshness(warehouse: Path) -> None:
    client = client_for(warehouse)
    assert client.get("/api/health").json() == {"status": "ok", "changes": 10}
    meta = client.get("/api/meta").json()
    assert "data_protection" in meta["topics"] and "Not legal advice" in meta["disclaimer"]
    fresh = client.get("/api/freshness").json()
    assert fresh["days_since_ingest"] == 0 and fresh["failures_last_7_days"] == 0


def test_overview_and_documents(warehouse: Path) -> None:
    client = client_for(warehouse)
    ov = client.get("/api/overview").json()
    assert (ov["changes"], ov["enriched"], ov["instruments"]) == (10, 1, 2)
    assert {r["change_type"] for r in ov["changes_by_instrument_and_type"]} == {"added", "modified"}
    docs = {d["doc_id"]: d for d in client.get("/api/documents").json()}
    assert docs["eprivacy"]["versions"] == 2 and docs["eprivacy"]["changes"] == 10
    assert docs["universal_service"]["repealed"] is True


def test_list_and_filter_changes(warehouse: Path) -> None:
    client = client_for(warehouse)
    changes = client.get("/api/changes").json()
    assert len(changes) == 10
    assert all(c["source_url"].endswith("CELEX:02002L0058-20091219") for c in changes)

    low = client.get("/api/changes", params={"impact": "low"}).json()
    assert [c["section_key"] for c in low] == ["art_14a"]
    assert low[0]["summary"] == "A committee procedure is added."
    assert len(client.get("/api/changes", params={"impact": "unrated"}).json()) == 9
    assert len(client.get("/api/changes", params={"topic": "other"}).json()) == 1
    assert len(client.get("/api/changes", params={"sector": ["telecom", "all"]}).json()) == 1
    added = client.get("/api/changes", params={"change_type": "added"}).json()
    assert {c["section_key"] for c in added} == {"art_14a", "art_15a"}
    assert client.get("/api/changes", params={"doc_id": "nope"}).json() == []
    assert client.get("/api/changes", params={"date_from": "2010-01-01"}).json() == []
    assert len(client.get("/api/changes", params={"limit": 3}).json()) == 3
    assert client.get("/api/changes", params={"impact": "extreme"}).status_code == 422


def test_change_detail_and_404(warehouse: Path) -> None:
    client = client_for(warehouse)
    change_id = client.get("/api/changes").json()[0]["change_id"]
    detail = client.get(f"/api/changes/{change_id}").json()
    assert "diff_html" in detail and "new_text" in detail and detail["instrument"]
    assert client.get("/api/changes/does-not-exist").status_code == 404


def test_trends_runs_usage(warehouse: Path) -> None:
    client = client_for(warehouse)
    assert client.get("/api/trends").json() == [
        {"instrument": "eprivacy", "year": 2009, "topic": "other", "changes": 1}
    ]
    runs = client.get("/api/runs").json()
    assert {r["stage"] for r in runs} >= {"ingest", "parse", "diff"}
    assert client.get("/api/runs", params={"only_failed": True}).json() == []
    [usage] = client.get("/api/llm-usage").json()
    assert usage["succeeded"] == 1 and usage["shadow_cost_usd"] == 0.001


def test_ask_returns_validated_citations(warehouse: Path) -> None:
    client = client_for(warehouse, ["Subscribers may receive non-itemised bills [1]."])
    body = client.post("/api/ask", json={"question": "Can subscribers get non-itemised bills?"})
    data = body.json()
    assert data["status"] == "answered"
    assert data["citations"][0]["section_id"] == data["retrieved"][0]["section_id"]
    assert "Not legal advice" in data["disclaimer"]


def test_ask_input_limits_and_rate_limit(warehouse: Path) -> None:
    client = client_for(warehouse, ["A [1]."] * 5, limit=2)
    assert client.post("/api/ask", json={"question": "x" * 501}).status_code == 422
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json={"question": "bills?"}).status_code == 200
    assert client.post("/api/ask", json={"question": "bills?"}).status_code == 200
    assert client.post("/api/ask", json={"question": "bills?"}).status_code == 429


def test_daily_cap_degrades_to_passages(warehouse: Path) -> None:
    client = client_for(warehouse, ["A [1]."] * 5, daily=1)
    assert client.post("/api/ask", json={"question": "bills?"}).json()["status"] == "answered"
    over = client.post("/api/ask", json={"question": "bills?"}).json()
    assert over["status"] == "retrieval_only" and over["retrieved"]
    assert "limit" in over["note"]


def test_serves_frontend_with_spa_fallback(warehouse: Path, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    client = client_for(warehouse, dist=dist)

    assert client.get("/").text == "<html>app</html>"
    assert client.get("/changes/abc").text == "<html>app</html>"  # client-side route
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/api/unknown").status_code == 404  # API 404s are not swallowed
    assert client.get("/api/health").json()["status"] == "ok"
    assert "secret" not in client.get("/..%2F..%2Fsecret").text


def test_rate_limiter_window() -> None:
    now = {"t": 0.0}
    limiter = RateLimiter(2, 60, clock=lambda: now["t"])
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a")
    assert limiter.allow("b")
    now["t"] = 61
    assert limiter.allow("a")
