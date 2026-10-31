from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from regtracker.common.config import Settings
from regtracker.common.http import PoliteClient, RateLimiter, RetryableStatusError, cache_key

SETTINGS = Settings(user_agent="test-agent/0.1 (contact: test@example.com)")


def make_client(handler: httpx.MockTransport, tmp_path: Path, **kwargs: object) -> PoliteClient:
    return PoliteClient(
        SETTINGS,
        cache_dir=tmp_path / "cache",
        transport=handler,
        rate_limiter=RateLimiter(0, sleep=lambda s: None),
        wait=wait_none(),
        **kwargs,  # type: ignore[arg-type]
    )


def test_sends_user_agent_and_headers(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"ok")

    with make_client(httpx.MockTransport(handler), tmp_path) as client:
        client.get("https://example.org/x", headers={"Accept-Language": "eng"})

    assert seen[0].headers["user-agent"] == SETTINGS.user_agent
    assert seen[0].headers["accept-language"] == "eng"


def test_retries_on_5xx_then_succeeds(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503 if calls["n"] < 3 else 200, content=b"ok")

    with make_client(httpx.MockTransport(handler), tmp_path) as client:
        response = client.get("https://example.org/x")

    assert response.status_code == 200
    assert calls["n"] == 3


def test_gives_up_after_max_attempts(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500)

    with (
        make_client(httpx.MockTransport(handler), tmp_path, max_attempts=3) as client,
        pytest.raises(RetryableStatusError),
    ):
        client.get("https://example.org/x")

    assert calls["n"] == 3


def test_retries_on_timeout(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("slow", request=request)
        return httpx.Response(200, content=b"ok")

    with make_client(httpx.MockTransport(handler), tmp_path) as client:
        assert client.get("https://example.org/x").status_code == 200
    assert calls["n"] == 2


def test_404_is_returned_not_retried_not_cached(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with make_client(httpx.MockTransport(handler), tmp_path) as client:
        assert client.get("https://example.org/x").status_code == 404
        assert client.get("https://example.org/x").status_code == 404

    assert calls["n"] == 2  # no retry within a call, no caching across calls


def test_success_is_cached_by_url_and_headers(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=b"body", headers={"content-type": "text/plain"})

    with make_client(httpx.MockTransport(handler), tmp_path) as client:
        first = client.get("https://example.org/x", headers={"Accept-Language": "eng"})
        second = client.get("https://example.org/x", headers={"Accept-Language": "eng"})
        client.get("https://example.org/x", headers={"Accept-Language": "fra"})

    assert calls["n"] == 2  # eng cached, fra is a different key
    assert second.content == first.content == b"body"
    assert second.headers["content-type"] == "text/plain"


def test_follows_redirects(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/celex":
            return httpx.Response(303, headers={"location": "https://example.org/doc"})
        return httpx.Response(200, content=b"doc")

    with make_client(httpx.MockTransport(handler), tmp_path) as client:
        assert client.get("https://example.org/celex").content == b"doc"


def test_rate_limiter_spaces_requests() -> None:
    now = {"t": 100.0}
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now["t"] += seconds

    limiter = RateLimiter(1.0, clock=lambda: now["t"], sleep=sleep)
    limiter.wait()  # first call never waits
    limiter.wait()  # immediately again: must wait a full interval
    now["t"] += 5.0
    limiter.wait()  # long gap: no wait

    assert slept == [pytest.approx(1.0)]


def test_cache_key_ignores_header_name_case_and_order() -> None:
    a = cache_key("u", {"Accept": "x", "Accept-Language": "eng"})
    b = cache_key("u", {"accept-language": "eng", "accept": "x"})
    assert a == b
    assert a != cache_key("u", {"accept": "x", "accept-language": "fra"})


def test_use_cache_false_always_hits_network(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=b"body")

    with make_client(httpx.MockTransport(handler), tmp_path) as client:
        client.get("https://example.org/q", params={"query": "x"}, use_cache=False)
        client.get("https://example.org/q", params={"query": "x"}, use_cache=False)

    assert calls["n"] == 2
    assert not (tmp_path / "cache").exists()
