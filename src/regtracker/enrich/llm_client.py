"""OpenAI-compatible LLM client (Groq or local Ollama) with throttle, budget, cache and retries.

The API key comes from settings (environment / .env) and is never logged or stored.
Every real call is recorded in `llm_calls`; the daily budget is computed from that table, so
cache hits never count against it.
"""

import hashlib
import json
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import duckdb
import yaml
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from regtracker.common.config import Settings
from regtracker.common.runs import utcnow

DEFAULT_CACHE_DIR = Path("data/cache/llm")
LLM_CONFIG_PATH = Path("configs/llm.yml")


class BudgetExceededError(Exception):
    """The daily token budget would be exceeded; stop and resume on the next run."""


@dataclass(frozen=True)
class ModelOptions:
    strict_schema: bool = False
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class LLMConfig:
    classify_model: str
    summary_model: str
    model_options: dict[str, ModelOptions] = field(default_factory=dict)
    max_output_tokens: int = 1200
    request_timeout_s: float = 60.0
    prices_per_million: dict[str, dict[str, float]] = field(default_factory=dict)

    def options(self, model: str) -> ModelOptions:
        return self.model_options.get(model, ModelOptions())

    def shadow_cost(self, model: str, tokens_in: int, tokens_out: int) -> float | None:
        price = self.prices_per_million.get(model)
        if price is None:
            return None
        return (tokens_in * price["input"] + tokens_out * price["output"]) / 1_000_000


def load_llm_config(settings: Settings, path: Path = LLM_CONFIG_PATH) -> LLMConfig:
    """configs/llm.yml, with LLM_MODEL_CLASSIFY / LLM_MODEL_SUMMARY from the environment winning."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return LLMConfig(
        classify_model=settings.llm_model_classify or data["models"]["classify"],
        summary_model=settings.llm_model_summary or data["models"]["summary"],
        model_options={k: ModelOptions(**v) for k, v in data.get("model_options", {}).items()},
        max_output_tokens=int(data.get("max_output_tokens", 1200)),
        request_timeout_s=float(data.get("request_timeout_s", 60)),
        prices_per_million=data.get("prices_per_million", {}),
    )


class TokenThrottle:
    """Rolling 60-second token window: wait until `tokens` more fit under `tokens_per_minute`."""

    def __init__(
        self,
        tokens_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        window_s: float = 60.0,
    ) -> None:
        self.limit = tokens_per_minute
        self._clock, self._sleep, self._window = clock, sleep, window_s
        self._events: deque[tuple[float, int]] = deque()

    def _used(self, now: float) -> int:
        while self._events and now - self._events[0][0] >= self._window:
            self._events.popleft()
        return sum(t for _, t in self._events)

    def acquire(self, tokens: int) -> None:
        tokens = min(tokens, self.limit)  # a single oversized request can still go alone
        while True:
            now = self._clock()
            if self._used(now) + tokens <= self.limit:
                return
            oldest = self._events[0][0]
            self._sleep(max(oldest + self._window - now, 0.01))

    def record(self, tokens: int) -> None:
        self._events.append((self._clock(), tokens))


def tokens_used_today(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute(
        "SELECT coalesce(sum(tokens_in + tokens_out), 0) FROM llm_calls "
        "WHERE created_at >= date_trunc('day', ?::TIMESTAMP)",
        [utcnow()],
    ).fetchone()
    return int(row[0]) if row else 0


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cached: bool


class LLM(Protocol):
    def complete_json(
        self,
        model: str,
        messages: list[dict[str, str]],
        prompt_version: str,
        schema: dict[str, Any] | None = None,
    ) -> LLMResult: ...

    def forget(self, model: str, messages: list[dict[str, str]], prompt_version: str) -> None:
        """Drop a cached response (e.g. one that failed validation) so it is not replayed."""


def cache_key(model: str, prompt_version: str, messages: list[dict[str, str]]) -> str:
    """(model, prompt_version, input_hash) -> one file name."""
    input_hash = hashlib.sha256(json.dumps(messages, sort_keys=True).encode("utf-8")).hexdigest()
    raw = f"{model}|{prompt_version}|{input_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def estimate_tokens(messages: list[dict[str, str]], max_output: int) -> int:
    """Rough upper bound for throttling: ~4 characters per token plus the output allowance."""
    return sum(len(m["content"]) for m in messages) // 4 + max_output


def _is_retryable(exc: BaseException) -> bool:
    import openai

    if isinstance(exc, openai.RateLimitError | openai.APITimeoutError | openai.APIConnectionError):
        return True
    return isinstance(exc, openai.APIStatusError) and exc.status_code >= 500


def _is_invalid_json_error(exc: BaseException) -> bool:
    import openai

    return isinstance(exc, openai.BadRequestError) and "json" in str(exc).lower()


class _WaitRetryAfter(wait_base):
    """Honor the server's `retry-after` header on 429; otherwise exponential backoff."""

    def __init__(self, fallback: wait_base) -> None:
        self.fallback = fallback

    def __call__(self, retry_state: Any) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        response = getattr(exc, "response", None)
        header = response.headers.get("retry-after") if response is not None else None
        try:
            return min(float(header), 120.0) if header else float(self.fallback(retry_state))
        except ValueError:
            return float(self.fallback(retry_state))


class OpenAICompatibleLLM:
    """Groq / Ollama through the `openai` SDK. JSON output, temperature 0, cached on disk."""

    def __init__(
        self,
        settings: Settings,
        config: LLMConfig,
        con: duckdb.DuckDBPyConnection,
        *,
        cache_dir: Path | None = DEFAULT_CACHE_DIR,
        throttle: TokenThrottle | None = None,
        daily_budget: int | None = None,
        client: Any = None,
        wait: wait_base | None = None,
        max_attempts: int = 5,
    ) -> None:
        self._config = config
        self._con = con
        self._cache_dir = cache_dir
        self._throttle = throttle or TokenThrottle(settings.llm_tpm)
        self._budget = settings.llm_daily_token_budget if daily_budget is None else daily_budget
        self._wait = wait or wait_exponential(multiplier=2, min=2, max=60)
        self._max_attempts = max_attempts
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key or "not-needed-for-ollama",
                timeout=config.request_timeout_s,
                max_retries=0,  # retries are handled here, with throttle and budget awareness
            )
        self._client = client

    # --- cache -------------------------------------------------------------------------------

    def _cache_path(self, key: str) -> Path | None:
        return self._cache_dir / f"{key}.json" if self._cache_dir else None

    def _read_cache(self, key: str) -> LLMResult | None:
        path = self._cache_path(key)
        if path is None or not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return LLMResult(**{**data, "cached": True})

    def _write_cache(self, key: str, result: LLMResult) -> None:
        path = self._cache_path(key)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in result.__dict__.items() if k != "cached"}
        tmp = path.with_suffix(".part")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)

    def forget(self, model: str, messages: list[dict[str, str]], prompt_version: str) -> None:
        path = self._cache_path(cache_key(model, prompt_version, messages))
        if path is not None:
            path.unlink(missing_ok=True)

    # --- call --------------------------------------------------------------------------------

    def _request_kwargs(
        self, model: str, messages: list[dict[str, str]], schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        from regtracker.enrich.schemas import strict_json_schema

        options = self._config.options(model)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_completion_tokens": self._config.max_output_tokens,
        }
        if options.strict_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": schema or strict_json_schema(),
                },
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}
        if options.reasoning_effort:
            kwargs["extra_body"] = {
                "reasoning_effort": options.reasoning_effort,
                "include_reasoning": False,
            }
        return kwargs

    def complete_json(
        self,
        model: str,
        messages: list[dict[str, str]],
        prompt_version: str,
        schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        """JSON completion. `schema` defaults to the change-analysis schema."""
        key = cache_key(model, prompt_version, messages)
        if (cached := self._read_cache(key)) is not None:
            return cached

        estimate = estimate_tokens(messages, self._config.max_output_tokens)
        if tokens_used_today(self._con) + estimate > self._budget:
            raise BudgetExceededError(
                f"daily token budget {self._budget} would be exceeded; resume on the next run"
            )

        kwargs = self._request_kwargs(model, messages, schema)

        timing = {"ms": 0}

        def attempt() -> Any:
            self._throttle.acquire(estimate)
            started = time.monotonic()  # API time only, not time spent waiting in the throttle
            response = self._client.chat.completions.create(**kwargs)
            timing["ms"] = int((time.monotonic() - started) * 1000)
            return response

        retrying = Retrying(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self._max_attempts),
            wait=_WaitRetryAfter(self._wait),
            reraise=True,
        )
        try:
            response = retrying(attempt)
        except Exception as exc:
            if _is_invalid_json_error(exc):
                # Groq rejects generations that fail its own schema check (HTTP 400). Report it
                # as an empty answer so the caller's validation-retry path handles it.
                return LLMResult("", model, 0, 0, timing["ms"], cached=False)
            raise
        latency_ms = timing["ms"]

        usage = response.usage
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
        self._throttle.record(tokens_in + tokens_out)
        self._con.execute(
            "INSERT INTO llm_calls (created_at, model, prompt_version, tokens_in, tokens_out, "
            "latency_ms) VALUES (?, ?, ?, ?, ?, ?)",
            [utcnow(), model, prompt_version, tokens_in, tokens_out, latency_ms],
        )
        result = LLMResult(
            content=response.choices[0].message.content or "",
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cached=False,
        )
        self._write_cache(key, result)
        return result
