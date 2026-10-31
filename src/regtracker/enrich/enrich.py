"""Batch enrichment: explain each detected change with a validated LLM analysis.

Resumable: changes that already have a row for (model, prompt_version) are skipped, and the job
stops cleanly when the daily token budget is reached. A response that fails validation is retried
once with the error message; a second failure is stored as an explicit `failed` row.
"""

import csv
import difflib
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import duckdb
from pydantic import ValidationError

from regtracker.common.runs import log_run, new_run_id, utcnow
from regtracker.enrich.llm_client import LLM, BudgetExceededError, LLMConfig, LLMResult
from regtracker.enrich.schemas import ChangeAnalysis

DEFAULT_PROMPT_VERSION = "v1"
MAX_PASSAGE_CHARS = 6000


def load_prompt(version: str) -> str:
    return (resources.files("regtracker.enrich") / "prompts" / f"{version}.md").read_text(
        encoding="utf-8"
    )


def read_change_ids(path: Path) -> list[str]:
    """Change ids from a CSV with a `change_id` column, or from a file with one id per line."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".csv":
        return [row["change_id"] for row in csv.DictReader(io.StringIO(text)) if row["change_id"]]
    return [line.strip() for line in text.splitlines() if line.strip()]


def changed_passages(old: str, new: str, context: int = 1) -> tuple[str, str]:
    """Only the paragraphs that differ (plus `context` neighbours), to save tokens."""
    a, b = old.split("\n"), new.split("\n")
    keep_a: set[int] = set()
    keep_b: set[int] = set()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        keep_a.update(range(max(i1 - context, 0), min(i2 + context, len(a))))
        keep_b.update(range(max(j1 - context, 0), min(j2 + context, len(b))))

    def render(lines: list[str], keep: set[int]) -> str:
        out: list[str] = []
        for i in sorted(keep):
            if out and i - 1 not in keep:
                out.append("[...]")
            out.append(lines[i])
        return "\n".join(out)

    return render(a, keep_a), render(b, keep_b)


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_PASSAGE_CHARS else text[:MAX_PASSAGE_CHARS] + "\n[truncated]"


@dataclass(frozen=True)
class ChangeInput:
    change_id: str
    instrument: str
    heading: str
    change_type: str
    old_text: str
    new_text: str


def build_messages(prompt: str, change: ChangeInput) -> list[dict[str, str]]:
    old, new = change.old_text, change.new_text
    if change.change_type in ("modified", "renumbered") and old and new:
        old, new = changed_passages(old, new)
    user = (
        f"Instrument: {change.instrument}\n"
        f'Change: {change.change_type}, "{change.heading}"\n'
        f"Old:\n{_truncate(old) or '(empty)'}\n\n"
        f"New:\n{_truncate(new) or '(empty)'}\n\n"
        "Return the JSON object."
    )
    return [{"role": "system", "content": prompt}, {"role": "user", "content": user}]


@dataclass
class Outcome:
    analysis: ChangeAnalysis | None
    error: str | None
    tokens_in: int
    tokens_out: int
    latency_ms: int
    llm_calls: int  # real (non-cached) calls


def _validate(result: LLMResult) -> ChangeAnalysis:
    return ChangeAnalysis.model_validate(json.loads(result.content))


def analyze(llm: LLM, model: str, prompt_version: str, messages: list[dict[str, str]]) -> Outcome:
    """Call, validate, and on failure retry once with the error message."""
    first = llm.complete_json(model, messages, prompt_version)
    totals = [first.tokens_in, first.tokens_out, first.latency_ms, int(not first.cached)]
    try:
        return Outcome(_validate(first), None, *totals)
    except (json.JSONDecodeError, ValidationError) as exc:
        error = f"{type(exc).__name__}: {exc}"[:1000]
        llm.forget(model, messages, prompt_version)  # never replay an invalid answer

    retry_messages = [
        *messages,
        {"role": "assistant", "content": first.content},
        {
            "role": "user",
            "content": f"That output was invalid: {error}\nReturn a corrected JSON object only.",
        },
    ]
    second = llm.complete_json(model, retry_messages, prompt_version)
    totals = [
        totals[0] + second.tokens_in,
        totals[1] + second.tokens_out,
        totals[2] + second.latency_ms,
        totals[3] + int(not second.cached),
    ]
    try:
        return Outcome(_validate(second), None, *totals)
    except (json.JSONDecodeError, ValidationError) as exc:
        llm.forget(model, retry_messages, prompt_version)
        return Outcome(None, f"invalid after retry: {type(exc).__name__}: {exc}"[:1000], *totals)


def pending_changes(
    con: duckdb.DuckDBPyConnection,
    model: str,
    prompt_version: str,
    retry_failed: bool = False,
    limit: int | None = None,
    change_ids: Sequence[str] | None = None,
) -> list[ChangeInput]:
    """Changes without an enrichment for (model, prompt_version), optionally only `change_ids`."""
    status_filter = "AND e.status = 'success'" if retry_failed else ""
    id_filter = "AND c.change_id IN (SELECT unnest(?::VARCHAR[]))" if change_ids is not None else ""
    sql = f"""
        SELECT c.change_id,
               d.doc_id || coalesce(' - ' || d.title, '') AS instrument,
               coalesce(
                 CASE c.section_type WHEN 'annex' THEN 'Annex ' ELSE 'Article ' END
                   || coalesce(ns.number, os.number)
                   || coalesce(' ' || coalesce(ns.heading, os.heading), ''),
                 c.section_key
               ) AS heading,
               c.change_type, coalesce(c.old_text, ''), coalesce(c.new_text, '')
        FROM changes c
        JOIN documents d USING (doc_id)
        LEFT JOIN sections ns ON ns.section_id = c.to_version || '#' || c.section_key
        LEFT JOIN sections os ON os.section_id = c.from_version || '#' || c.old_section_key
        WHERE NOT EXISTS (
          SELECT 1 FROM enrichments e
          WHERE e.change_id = c.change_id AND e.model = ? AND e.prompt_version = ? {status_filter}
        ) {id_filter}
        ORDER BY c.doc_id, c.to_version, c.section_key
    """
    params: list[object] = [model, prompt_version]
    if change_ids is not None:
        params.append(list(change_ids))
    rows = con.execute(sql + (f" LIMIT {int(limit)}" if limit else ""), params)
    return [ChangeInput(*r) for r in rows.fetchall()]


def store_outcome(
    con: duckdb.DuckDBPyConnection,
    config: LLMConfig,
    change_id: str,
    model: str,
    prompt_version: str,
    outcome: Outcome,
) -> None:
    a = outcome.analysis
    con.execute(
        """
        INSERT INTO enrichments (change_id, model, prompt_version, status, summary, topics,
          sectors, impact, impact_rationale, error, tokens_in, tokens_out, latency_ms,
          shadow_cost_usd, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (change_id, model, prompt_version) DO UPDATE SET
          status = excluded.status, summary = excluded.summary, topics = excluded.topics,
          sectors = excluded.sectors, impact = excluded.impact,
          impact_rationale = excluded.impact_rationale, error = excluded.error,
          tokens_in = excluded.tokens_in, tokens_out = excluded.tokens_out,
          latency_ms = excluded.latency_ms, shadow_cost_usd = excluded.shadow_cost_usd,
          created_at = excluded.created_at
        """,
        [
            change_id,
            model,
            prompt_version,
            "success" if a else "failed",
            a.summary if a else None,
            list(a.topics) if a else None,
            list(a.sectors) if a else None,
            a.impact if a else None,
            a.impact_rationale if a else None,
            outcome.error,
            outcome.tokens_in,
            outcome.tokens_out,
            outcome.latency_ms,
            config.shadow_cost(model, outcome.tokens_in, outcome.tokens_out),
            utcnow(),
        ],
    )


def _is_fatal(exc: BaseException) -> bool:
    import openai

    return isinstance(
        exc, openai.AuthenticationError | openai.PermissionDeniedError | openai.NotFoundError
    )


@dataclass
class EnrichReport:
    pending: int = 0
    succeeded: int = 0
    failed: int = 0
    llm_calls: int = 0
    tokens: int = 0
    stopped_reason: str | None = None


def enrich_pending(
    con: duckdb.DuckDBPyConnection,
    llm: LLM,
    config: LLMConfig,
    model: str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    *,
    limit: int | None = None,
    retry_failed: bool = False,
    change_ids: Sequence[str] | None = None,
) -> EnrichReport:
    prompt = load_prompt(prompt_version)
    todo = pending_changes(con, model, prompt_version, retry_failed, limit, change_ids)
    report = EnrichReport(pending=len(todo))
    started = utcnow()
    for change in todo:
        try:
            outcome = analyze(llm, model, prompt_version, build_messages(prompt, change))
        except BudgetExceededError as exc:
            report.stopped_reason = str(exc)
            break
        except Exception as exc:
            if _is_fatal(exc):  # e.g. bad API key: every later call would fail the same way
                report.stopped_reason = f"{type(exc).__name__}: {exc}"[:500]
                break
            outcome = Outcome(None, f"{type(exc).__name__}: {exc}"[:1000], 0, 0, 0, 0)
        store_outcome(con, config, change.change_id, model, prompt_version, outcome)
        report.succeeded += outcome.analysis is not None
        report.failed += outcome.analysis is None
        report.llm_calls += outcome.llm_calls
        report.tokens += (outcome.tokens_in + outcome.tokens_out) if outcome.llm_calls else 0
    log_run(
        con,
        run_id=new_run_id(),
        stage=f"enrich:{model}",
        started_at=started,
        finished_at=utcnow(),
        status="success" if report.failed == 0 and not report.stopped_reason else "failed",
        rows_in=report.pending,
        rows_out=report.succeeded,
        error=report.stopped_reason
        or (f"{report.failed} changes failed validation" if report.failed else None),
    )
    return report
