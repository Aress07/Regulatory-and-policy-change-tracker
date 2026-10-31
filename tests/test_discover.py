import json
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from tenacity import wait_none

from regtracker.common.config import Settings
from regtracker.common.http import PoliteClient, RateLimiter
from regtracker.ingest.discover import (
    DiscoveryError,
    build_query,
    discover_versions,
    parse_results,
    parse_version_celex,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sparql" / "ai_act_consolidated_versions.json"


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def row(celex: str, doc_date: str | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {"celex": {"type": "literal", "value": celex}}
    if doc_date:
        r["date"] = {"type": "literal", "value": doc_date}
    return r


def test_parses_recorded_ai_act_response() -> None:
    versions = parse_results(load_fixture())

    assert [v.celex_version for v in versions] == ["02024R1689-20240712", "02024R1689-20260727"]
    assert versions[0].version_date == date(2024, 7, 12)
    assert versions[1].url == "http://publications.europa.eu/resource/celex/02024R1689-20260727"


def test_results_sorted_by_date_and_deduplicated() -> None:
    payload = {
        "results": {
            "bindings": [
                row("02024R1689-20260727"),
                row("02024R1689-20240712", "2024-07-12"),
                row("02024R1689-20240712", "2024-07-12"),
            ]
        }
    }
    versions = parse_results(payload)
    assert [v.version_date for v in versions] == [date(2024, 7, 12), date(2026, 7, 27)]


def test_empty_result_means_no_versions() -> None:
    assert parse_results({"results": {"bindings": []}}) == []


def test_date_mismatch_is_an_error() -> None:
    with pytest.raises(DiscoveryError, match="differ"):
        parse_results({"results": {"bindings": [row("02016R0679-20160504", "2016-05-05")]}})


def test_unexpected_shape_is_an_error() -> None:
    with pytest.raises(DiscoveryError):
        parse_results({"boolean": True})


@pytest.mark.parametrize(
    ("celex", "expected"),
    [("02016R0679-20160504", date(2016, 5, 4)), ("02022L2555-20221227", date(2022, 12, 27))],
)
def test_parse_version_celex(celex: str, expected: date) -> None:
    assert parse_version_celex(celex) == expected


@pytest.mark.parametrize("celex", ["32016R0679", "02016R0679", "02016R0679-2016050", "x"])
def test_parse_version_celex_rejects_non_consolidated(celex: str) -> None:
    with pytest.raises(ValueError):
        parse_version_celex(celex)


@pytest.mark.parametrize("bad", ["02016R0679", '32016R0679" } #', "", "32016R0679-20160504"])
def test_build_query_rejects_non_base_celex(bad: str) -> None:
    with pytest.raises(ValueError):
        build_query(bad)


def test_discover_versions_queries_endpoint(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=load_fixture())

    client = PoliteClient(
        Settings(user_agent="test-agent"),
        cache_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        rate_limiter=RateLimiter(0),
        wait=wait_none(),
    )
    with client:
        versions = discover_versions(client, "32024R1689")

    assert len(versions) == 2
    request = seen[0]
    assert request.headers["accept"] == "application/sparql-results+json"
    query = parse_qs(request.url.query.decode())["query"][0]
    assert '"32024R1689"' in query


def test_discover_versions_raises_on_http_error(tmp_path: Path) -> None:
    client = PoliteClient(
        Settings(user_agent="test-agent"),
        cache_dir=None,
        transport=httpx.MockTransport(lambda r: httpx.Response(400)),
        rate_limiter=RateLimiter(0),
        wait=wait_none(),
    )
    with client, pytest.raises(DiscoveryError, match="400"):
        discover_versions(client, "32024R1689")
