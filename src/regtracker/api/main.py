"""Read-only HTTP API over the warehouse: changes, freshness, and cited Q&A.

Run: uvicorn regtracker.api.main:app --reload
No business logic lives here; it calls into regtracker.* modules.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from regtracker.common.config import get_settings
from regtracker.rag.answer import Answerer, load_rag_config

DISCLAIMER = "Not legal advice. AI-generated text can be wrong; check the official source."


class Change(BaseModel):
    change_id: str
    doc_id: str
    section_key: str
    old_section_key: str | None
    section_type: str | None
    change_type: str
    from_version: str
    to_version: str
    to_date: date
    is_synthetic: bool
    source_url: str
    summary: str | None = Field(None, description="AI-generated")
    topics: list[str] | None = None
    sectors: list[str] | None = None
    impact: str | None = None
    impact_rationale: str | None = None
    enrichment_model: str | None = None
    prompt_version: str | None = None


class ChangeDetail(Change):
    old_text: str | None
    new_text: str | None
    similarity: float | None
    diff_html: str | None


class Freshness(BaseModel):
    last_successful_ingest: datetime | None
    days_since_ingest: int | None
    failures_last_7_days: int


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    doc_id: str | None = None


class CitationOut(BaseModel):
    n: int
    section_id: str
    breadcrumb: str
    source_url: str


class PassageOut(BaseModel):
    section_id: str
    breadcrumb: str
    text: str
    score: float
    cosine: float


class AskResponse(BaseModel):
    status: str
    answer: str | None
    citations: list[CitationOut]
    confidence: str
    retrieved: list[PassageOut]
    note: str | None
    disclaimer: str = DISCLAIMER


class RateLimiter:
    """Sliding-window limit per client key (in memory; fine for a single-process demo)."""

    def __init__(
        self, max_calls: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ):
        self.max_calls, self.window_s, self.clock = max_calls, window_s, clock
        self.calls: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now, q = self.clock(), self.calls[key]
        while q and now - q[0] >= self.window_s:
            q.popleft()
        if len(q) >= self.max_calls:
            return False
        q.append(now)
        return True


_CHANGE_COLUMNS = (
    "change_id, doc_id, section_key, old_section_key, section_type, change_type, from_version, "
    "to_version, to_date, is_synthetic, source_url, summary, topics, sectors, impact, "
    "impact_rationale, enrichment_model, prompt_version"
)
_CHANGES_SQL = """
    WITH latest AS (
      SELECT * FROM enrichments WHERE status = 'success'
      QUALIFY row_number() OVER (PARTITION BY change_id ORDER BY created_at DESC) = 1
    )
    SELECT c.change_id, c.doc_id, c.section_key, c.old_section_key, c.section_type,
           c.change_type, c.from_version, c.to_version, tv.version_date AS to_date,
           coalesce(c.is_synthetic, false) AS is_synthetic,
           'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:' || tv.celex AS source_url,
           e.summary, e.topics, e.sectors, e.impact, e.impact_rationale,
           e.model AS enrichment_model, e.prompt_version,
           c.old_text, c.new_text, c.similarity, c.diff_html
    FROM changes c
    JOIN document_versions tv ON tv.version_id = c.to_version
    LEFT JOIN latest e USING (change_id)
"""


def create_app(
    warehouse_path: Path | None = None,
    answerer_factory: Callable[[duckdb.DuckDBPyConnection], Answerer] | None = None,
    ask_limit: RateLimiter | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    db_path = warehouse_path or get_settings().warehouse_path
    limiter = ask_limit or RateLimiter(max_calls=10, window_s=60)
    state: dict[str, Any] = {}

    app = FastAPI(
        title="EU Regulation Change Tracker API",
        description=f"Read-only access to detected changes and cited Q&A. {DISCLAIMER}",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:8501"],  # Streamlit dev server
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def db() -> Iterator[duckdb.DuckDBPyConnection]:
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            yield con
        finally:
            con.close()

    Db = Annotated[duckdb.DuckDBPyConnection, Depends(db)]

    def rows_to_changes(
        con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]
    ) -> list[dict[str, Any]]:
        cur = con.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]

    @app.get("/health")
    def health(con: Db) -> dict[str, Any]:
        row = con.execute("SELECT count(*) FROM changes").fetchone()
        return {"status": "ok", "changes": row[0] if row else 0}

    @app.get("/changes", response_model=list[Change])
    def list_changes(
        con: Db,
        doc_id: str | None = None,
        impact: str | None = Query(None, pattern="^(low|medium|high)$"),
        since: date | None = None,
        include_synthetic: bool = False,
        limit: int = Query(100, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        where: list[str] = ["1=1"]
        params: list[object] = []
        if doc_id:
            where.append("c.doc_id = ?")
            params.append(doc_id)
        if impact:
            where.append("e.impact = ?")
            params.append(impact)
        if since:
            where.append("tv.version_date >= ?")
            params.append(since)
        if not include_synthetic:
            where.append("NOT coalesce(c.is_synthetic, false)")
        sql = (
            f"SELECT {_CHANGE_COLUMNS} FROM ({_CHANGES_SQL} WHERE {' AND '.join(where)}) "
            f"ORDER BY to_date DESC, doc_id, section_key LIMIT {int(limit)}"
        )
        return rows_to_changes(con, sql, params)

    @app.get("/changes/{change_id}", response_model=ChangeDetail)
    def get_change(con: Db, change_id: str) -> dict[str, Any]:
        rows = rows_to_changes(con, f"{_CHANGES_SQL} WHERE c.change_id = ?", [change_id])
        if not rows:
            raise HTTPException(404, "change not found")
        return rows[0]

    @app.get("/freshness", response_model=Freshness)
    def freshness(con: Db) -> dict[str, Any]:
        last, failures = con.execute(
            "SELECT max(finished_at) FILTER (WHERE stage LIKE 'ingest:%' AND status = 'success'), "
            "count(*) FILTER (WHERE status = 'failed' AND finished_at > now() - INTERVAL 7 DAY) "
            "FROM pipeline_runs"
        ).fetchone() or (None, 0)
        days = (datetime.now() - last).days if last else None
        return {
            "last_successful_ingest": last,
            "days_since_ingest": days,
            "failures_last_7_days": failures,
        }

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest, request: Request, con: Db) -> dict[str, Any]:
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(429, "too many questions; try again in a minute")
        if "answerer" not in state:
            state["answerer"] = (answerer_factory or _default_answerer)(con)
        answerer: Answerer = state["answerer"]
        from regtracker.index.search import Filters

        result = answerer.ask(body.question, Filters(doc_ids=(body.doc_id,) if body.doc_id else ()))
        return {
            "status": result.status,
            "answer": result.answer,
            "citations": [c.__dict__ for c in result.citations],
            "confidence": result.confidence,
            "retrieved": [
                {"section_id": h.section_id, "breadcrumb": h.breadcrumb, "text": h.text,
                 "score": h.score, "cosine": h.cosine}
                for h in result.retrieved
            ],
            "note": result.note,
        }  # fmt: skip

    return app


def _default_answerer(con: duckdb.DuckDBPyConnection) -> Answerer:
    """Real embedder and LLM. The LLM gets its own writable connection for call logging only if
    the warehouse is writable; the API itself never writes."""
    from regtracker.enrich.llm_client import OpenAICompatibleLLM, load_llm_config
    from regtracker.index.embed import E5Embedder
    from regtracker.index.search import SearchIndex
    from regtracker.rag.answer import source_urls

    settings = get_settings()
    llm_config = load_llm_config(settings)
    llm_con = duckdb.connect(":memory:")  # budget/call log kept in memory for the API process
    from regtracker.common.db import init_schema

    init_schema(llm_con)
    llm = OpenAICompatibleLLM(settings, llm_config, llm_con) if settings.llm_api_key else None
    return Answerer(
        SearchIndex.load(con), E5Embedder(), llm, llm_config.summary_model, source_urls(con),
        load_rag_config(),
    )  # fmt: skip


app = create_app()
