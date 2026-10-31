"""Polite HTTP client: descriptive User-Agent, rate limit, retries with backoff, on-disk cache."""

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from regtracker.common.config import Settings, get_settings

DEFAULT_CACHE_DIR = Path("data/cache/http")
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


class RetryableStatusError(Exception):
    """Server answered 429 or 5xx; worth retrying."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"{response.status_code} for {response.request.url}")
        self.response = response


class RateLimiter:
    """Blocks so that calls to `wait()` are at least 1/rate seconds apart."""

    def __init__(
        self,
        requests_per_second: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._next_allowed = 0.0

    def wait(self) -> None:
        now = self._clock()
        if now < self._next_allowed:
            self._sleep(self._next_allowed - now)
            now = self._next_allowed
        self._next_allowed = now + self._interval


def cache_key(url: str, headers: Mapping[str, str]) -> str:
    """Stable key from URL plus request headers (case-insensitive names, sorted)."""
    normalized = sorted((k.lower(), v) for k, v in headers.items())
    payload = json.dumps([url, normalized], ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PoliteClient:
    """GET-only client. Only successful (2xx) responses are cached; 404s and errors are not."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        cache_dir: Path | None = DEFAULT_CACHE_DIR,
        transport: httpx.BaseTransport | None = None,
        rate_limiter: RateLimiter | None = None,
        max_attempts: int = 4,
        wait: wait_base | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._cache_dir = cache_dir
        self._limiter = rate_limiter or RateLimiter(self._settings.requests_per_second)
        self._max_attempts = max_attempts
        self._wait = wait if wait is not None else wait_exponential(multiplier=2, min=2, max=30)
        self._client = httpx.Client(
            headers={"User-Agent": self._settings.user_agent},
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
            transport=transport,
            # Throttle every hop, including redirects (Cellar answers 303 before 200).
            event_hooks={"request": [self._throttle]},
        )

    def _throttle(self, request: httpx.Request) -> None:
        self._limiter.wait()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        *,
        use_cache: bool = True,
    ) -> httpx.Response:
        """GET with cache, rate limit and retries. 4xx (other than 429) is returned, not raised.

        Pass `use_cache=False` for answers that change over time (e.g. version discovery).
        """
        if params:
            url = str(httpx.URL(url, params=params))
        req_headers = dict(headers or {})
        key = cache_key(url, {"User-Agent": self._settings.user_agent, **req_headers})
        if not use_cache:
            return self._fetch(url, req_headers)
        cached = self._read_cache(key, url)
        if cached is not None:
            return cached
        response = self._fetch(url, req_headers)
        if response.is_success:
            self._write_cache(key, response)
        return response

    def _fetch(self, url: str, headers: dict[str, str]) -> httpx.Response:

        retrying = Retrying(
            retry=retry_if_exception_type((RetryableStatusError, httpx.TransportError)),
            stop=stop_after_attempt(self._max_attempts),
            wait=self._wait,
            reraise=True,
        )
        return retrying(self._attempt, url, headers)

    def _attempt(self, url: str, headers: dict[str, str]) -> httpx.Response:
        response = self._client.get(url, headers=headers)
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableStatusError(response)
        return response

    def _paths(self, key: str) -> tuple[Path, Path] | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"{key}.body", self._cache_dir / f"{key}.meta.json"

    def _read_cache(self, key: str, url: str) -> httpx.Response | None:
        paths = self._paths(key)
        if paths is None or not (paths[0].exists() and paths[1].exists()):
            return None
        meta = json.loads(paths[1].read_text(encoding="utf-8"))
        return httpx.Response(
            meta["status_code"],
            headers=meta["headers"],
            content=paths[0].read_bytes(),
            request=httpx.Request("GET", url),
        )

    def _write_cache(self, key: str, response: httpx.Response) -> None:
        paths = self._paths(key)
        if paths is None:
            return
        paths[0].parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "status_code": response.status_code,
            "headers": {"content-type": response.headers.get("content-type", "")},
        }
        # Write meta last: a body without meta is treated as a miss.
        paths[0].write_bytes(response.content)
        paths[1].write_text(json.dumps(meta), encoding="utf-8")
