"""Enrichment tests with a fake OpenAI client: no network, no real LLM."""

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import httpx
import openai
import pytest
from tenacity import wait_none

from regtracker.common.config import Settings
from regtracker.common.db import connect, init_schema
from regtracker.common.fixture_db import build_fixture_db
from regtracker.enrich.enrich import (
    ChangeInput,
    analyze,
    build_messages,
    changed_passages,
    enrich_pending,
    load_prompt,
    read_change_ids,
)
from regtracker.enrich.llm_client import (
    BudgetExceededError,
    LLMConfig,
    ModelOptions,
    OpenAICompatibleLLM,
    TokenThrottle,
    _WaitRetryAfter,
)
from regtracker.enrich.schemas import ChangeAnalysis

FIXTURES = Path(__file__).parent / "fixtures" / "xhtml"
MODEL = "test/model"
CONFIG = LLMConfig(
    classify_model=MODEL,
    summary_model=MODEL,
    model_options={MODEL: ModelOptions(strict_schema=True, reasoning_effort="low")},
    max_output_tokens=200,
    prices_per_million={MODEL: {"input": 1.0, "output": 2.0}},
)
SETTINGS = Settings(llm_api_key="", llm_tpm=100_000, llm_daily_token_budget=1_000_000)

VALID = {
    "summary": "The deadline is shortened.",
    "topics": ["cybersecurity"],
    "sectors": ["all"],
    "impact": "high",
    "impact_rationale": "A deadline for all providers changes.",
}


class FakeOpenAI:
    """Mimics `client.chat.completions.create`, returning queued contents or `VALID`."""

    def __init__(self, contents: list[str] | None = None, error: Exception | None = None) -> None:
        self.contents = list(contents or [])
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            error, self.error = self.error, None
            raise error
        content = self.contents.pop(0) if self.contents else json.dumps(VALID)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        )


@pytest.fixture
def con(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    c = connect(tmp_path / "w.duckdb")
    init_schema(c)
    yield c
    c.close()


def make_llm(
    con: duckdb.DuckDBPyConnection, fake: FakeOpenAI, tmp_path: Path, **kwargs: Any
) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(
        SETTINGS, CONFIG, con, cache_dir=tmp_path / "llm", client=fake, wait=wait_none(), **kwargs
    )


MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_request_is_deterministic_json_with_strict_schema(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fake = FakeOpenAI()
    make_llm(con, fake, tmp_path).complete_json(MODEL, MESSAGES, "v1")

    [call] = fake.calls
    assert call["temperature"] == 0
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["strict"] is True
    schema = call["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert call["extra_body"] == {"reasoning_effort": "low", "include_reasoning": False}


def test_other_models_use_json_object_mode(con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    fake = FakeOpenAI()
    make_llm(con, fake, tmp_path).complete_json("other/model", MESSAGES, "v1")
    assert fake.calls[0]["response_format"] == {"type": "json_object"}
    assert "extra_body" not in fake.calls[0]


def test_cache_hit_makes_no_call_and_logs_nothing(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fake = FakeOpenAI()
    llm = make_llm(con, fake, tmp_path)
    first = llm.complete_json(MODEL, MESSAGES, "v1")
    second = llm.complete_json(MODEL, MESSAGES, "v1")

    assert len(fake.calls) == 1
    assert (first.cached, second.cached) == (False, True)
    assert second.content == first.content
    assert con.execute("SELECT count(*), sum(tokens_in) FROM llm_calls").fetchone() == (1, 100)


def test_cache_key_includes_prompt_version(con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    fake = FakeOpenAI()
    llm = make_llm(con, fake, tmp_path)
    llm.complete_json(MODEL, MESSAGES, "v1")
    llm.complete_json(MODEL, MESSAGES, "v2")
    assert len(fake.calls) == 2


def test_budget_stops_before_calling(con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    fake = FakeOpenAI()
    llm = make_llm(con, fake, tmp_path, daily_budget=300)
    llm.complete_json(MODEL, MESSAGES, "v1")  # estimate ~200, actual 150 recorded
    with pytest.raises(BudgetExceededError):
        llm.complete_json(MODEL, [*MESSAGES, {"role": "user", "content": "more"}], "v1")
    assert len(fake.calls) == 1


def test_rate_limit_is_retried(con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    request = httpx.Request("POST", "https://example.org")
    error = openai.RateLimitError(
        "slow down", response=httpx.Response(429, request=request), body=None
    )
    fake = FakeOpenAI(error=error)
    result = make_llm(con, fake, tmp_path).complete_json(MODEL, MESSAGES, "v1")
    assert len(fake.calls) == 2
    assert json.loads(result.content) == VALID


def test_wait_honors_retry_after_header() -> None:
    request = httpx.Request("POST", "https://example.org")
    exc = openai.RateLimitError(
        "slow",
        response=httpx.Response(429, headers={"retry-after": "7"}, request=request),
        body=None,
    )
    state = SimpleNamespace(outcome=SimpleNamespace(exception=lambda: exc))
    assert _WaitRetryAfter(wait_none())(state) == 7.0


def test_throttle_waits_for_the_window_with_fake_clock() -> None:
    now = {"t": 0.0}
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        now["t"] += s

    throttle = TokenThrottle(1000, clock=lambda: now["t"], sleep=sleep)
    throttle.acquire(600)
    throttle.record(600)
    now["t"] = 10.0
    throttle.acquire(600)  # 600 + 600 > 1000: must wait until t=60 when the first expires

    assert slept == [pytest.approx(50.0)]
    throttle.record(600)
    throttle.acquire(300)  # 600 in window + 300 <= 1000: no wait
    assert len(slept) == 1


def test_validation_failure_is_retried_once_with_the_error(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    bad = json.dumps({**VALID, "impact": "severe"})
    fake = FakeOpenAI(contents=[bad])
    outcome = analyze(make_llm(con, fake, tmp_path), MODEL, "v1", MESSAGES)

    assert outcome.analysis is not None and outcome.analysis.impact == "high"
    assert outcome.llm_calls == 2
    retry_messages = fake.calls[1]["messages"]
    assert retry_messages[-2] == {"role": "assistant", "content": bad}
    assert "invalid" in retry_messages[-1]["content"]


def test_second_validation_failure_is_reported(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fake = FakeOpenAI(contents=["not json", json.dumps({**VALID, "topics": []})])
    outcome = analyze(make_llm(con, fake, tmp_path), MODEL, "v1", MESSAGES)
    assert outcome.analysis is None
    assert outcome.error is not None and outcome.error.startswith("invalid after retry")


def test_changed_passages_keep_only_differences_with_context() -> None:
    old = "1. Scope.\n2. Same.\n3. Fines up to 10.\n4. Same too.\n5. End."
    new = "1. Scope.\n2. Same.\n3. Fines up to 20.\n4. Same too.\n5. End."
    o, n = changed_passages(old, new)
    assert o == "2. Same.\n3. Fines up to 10.\n4. Same too."
    assert n == "2. Same.\n3. Fines up to 20.\n4. Same too."


def test_messages_contain_prompt_and_change() -> None:
    change = ChangeInput("c1", "gdpr", "Article 83 Fines", "added", "", "New text.")
    system, user = build_messages(load_prompt("v1"), change)
    assert "Impact scale" in system["content"] and "JSON" in system["content"]
    assert 'added, "Article 83 Fines"' in user["content"]
    assert "Old:\n(empty)" in user["content"]


# --- batch job on the fixture warehouse -------------------------------------------------------


@pytest.fixture
def fixture_con(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    out = tmp_path / "fixture.duckdb"
    build_fixture_db(out, FIXTURES)
    c = duckdb.connect(str(out))
    yield c
    c.close()


def test_batch_enriches_every_change_and_reruns_free(
    fixture_con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fake = FakeOpenAI()
    llm = make_llm(fixture_con, fake, tmp_path)

    report = enrich_pending(fixture_con, llm, CONFIG, MODEL)
    assert (report.pending, report.succeeded, report.failed) == (10, 10, 0)
    rows = fixture_con.execute(
        "SELECT count(*), count(*) FILTER (WHERE tokens_in > 0 AND shadow_cost_usd > 0) "
        "FROM enrichments WHERE status = 'success'"
    ).fetchone()
    assert rows == (10, 10)

    rerun = enrich_pending(fixture_con, llm, CONFIG, MODEL)
    assert rerun.pending == 0

    # Rebuilding enrichments from scratch hits the disk cache: zero LLM calls.
    calls_before = len(fake.calls)
    fixture_con.execute("DELETE FROM enrichments")
    rebuilt = enrich_pending(fixture_con, llm, CONFIG, MODEL)
    assert (rebuilt.succeeded, rebuilt.llm_calls) == (10, 0)
    assert len(fake.calls) == calls_before


def test_batch_stores_failure_rows_and_retries_them_on_request(
    fixture_con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fake = FakeOpenAI(contents=["oops", "still not json"])
    llm = make_llm(fixture_con, fake, tmp_path)

    report = enrich_pending(fixture_con, llm, CONFIG, MODEL, limit=1)
    assert (report.succeeded, report.failed) == (0, 1)
    status, error = fixture_con.execute("SELECT status, error FROM enrichments").fetchone()  # type: ignore[misc]
    assert status == "failed" and error

    assert enrich_pending(fixture_con, llm, CONFIG, MODEL, limit=1).pending == 1  # next change
    fixture_con.execute("DELETE FROM enrichments WHERE status = 'success'")
    retried = enrich_pending(fixture_con, llm, CONFIG, MODEL, retry_failed=True)
    assert retried.failed == 0
    assert fixture_con.execute(
        "SELECT count(*) FROM enrichments WHERE status = 'failed'"
    ).fetchone() == (0,)


def test_batch_stops_cleanly_at_budget(
    fixture_con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fake = FakeOpenAI()
    llm = make_llm(fixture_con, fake, tmp_path, daily_budget=2_500)

    report = enrich_pending(fixture_con, llm, CONFIG, MODEL)

    assert report.stopped_reason is not None and "budget" in report.stopped_reason
    assert 0 < report.succeeded < 10
    stored = fixture_con.execute("SELECT count(*) FROM enrichments").fetchone()
    assert stored == (report.succeeded,)
    status = fixture_con.execute(
        "SELECT status FROM pipeline_runs WHERE stage LIKE 'enrich:%'"
    ).fetchone()
    assert status == ("failed",)


def test_invalid_answers_are_not_cached(con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    fake = FakeOpenAI(contents=["bad", "bad again"])
    llm = make_llm(con, fake, tmp_path)
    assert analyze(llm, MODEL, "v1", MESSAGES).analysis is None
    assert analyze(llm, MODEL, "v1", MESSAGES).analysis is not None  # fresh call, now valid
    assert len(fake.calls) == 3


def _bad_request(message: str) -> openai.BadRequestError:
    request = httpx.Request("POST", "https://example.org")
    return openai.BadRequestError(message, response=httpx.Response(400, request=request), body=None)


def test_groq_json_validation_400_goes_through_retry_path(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fake = FakeOpenAI(error=_bad_request("Failed to validate JSON. Please adjust your prompt."))
    outcome = analyze(make_llm(con, fake, tmp_path), MODEL, "v1", MESSAGES)
    assert outcome.analysis is not None  # second call (valid) succeeded
    assert len(fake.calls) == 2


def test_unexpected_error_fails_one_change_not_the_run(
    fixture_con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fake = FakeOpenAI(error=_bad_request("context length exceeded"))
    report = enrich_pending(fixture_con, make_llm(fixture_con, fake, tmp_path), CONFIG, MODEL)
    assert (report.failed, report.succeeded, report.stopped_reason) == (1, 9, None)


def test_auth_error_stops_the_run(fixture_con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    request = httpx.Request("POST", "https://example.org")
    error = openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=request), body=None
    )
    report = enrich_pending(
        fixture_con, make_llm(fixture_con, FakeOpenAI(error=error), tmp_path), CONFIG, MODEL
    )
    assert report.stopped_reason is not None and report.succeeded == 0
    assert fixture_con.execute("SELECT count(*) FROM enrichments").fetchone() == (0,)


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_prompt_examples_match_the_output_schema(version: str) -> None:
    """A few-shot example the validator would reject teaches the model a wrong format."""
    lines = [line for line in load_prompt(version).splitlines() if line.startswith("JSON: ")]
    assert len(lines) >= 3
    for line in lines:
        ChangeAnalysis.model_validate(json.loads(line.removeprefix("JSON: ")))


def test_batch_can_be_limited_to_listed_changes(
    fixture_con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    ids = [r[0] for r in fixture_con.execute("SELECT change_id FROM changes LIMIT 3").fetchall()]
    csv_file = tmp_path / "labeled.csv"
    csv_file.write_text("change_id,impact\n" + "".join(f"{i},low\n" for i in ids), "utf-8")
    txt_file = tmp_path / "ids.txt"
    txt_file.write_text("\n".join(ids[:2]) + "\n\n", "utf-8")
    assert read_change_ids(csv_file) == ids
    assert read_change_ids(txt_file) == ids[:2]

    llm = make_llm(fixture_con, FakeOpenAI(), tmp_path)
    report = enrich_pending(fixture_con, llm, CONFIG, MODEL, change_ids=read_change_ids(csv_file))
    assert report.succeeded == 3
    enriched = {r[0] for r in fixture_con.execute("SELECT change_id FROM enrichments").fetchall()}
    assert enriched == set(ids)
    assert enrich_pending(fixture_con, llm, CONFIG, MODEL, change_ids=[]).pending == 0
