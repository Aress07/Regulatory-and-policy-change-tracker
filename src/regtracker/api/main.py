"""HTTP API over the warehouse, plus the built React frontend (one deployable container).

Run (development):  uvicorn regtracker.api.main:app --reload   and   npm run dev   in frontend/
Run (production):   build frontend/ first; FRONTEND_DIST points at its dist/ folder.

All endpoints are read-only and live under /api. No business logic here: queries come from
regtracker.app.queries and answers from regtracker.rag.
"""

import os
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any

import duckdb
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from regtracker.app import queries
from regtracker.app.snapshot import resolve_warehouse
from regtracker.common.config import get_settings
from regtracker.rag.answer import Answerer, load_rag_config

DISCLAIMER = "Not legal advice. AI-generated text can be wrong; check the official source."
TOPICS = [
    "data_protection", "ai_governance", "cybersecurity", "platform_liability", "competition",
    "data_sharing", "transparency", "enforcement_penalties", "scope_definitions", "other",
]  # fmt: skip
SECTORS = [
    "all", "healthcare", "finance", "public_sector", "online_platforms", "manufacturing",
    "telecom", "education", "other",
]  # fmt: skip


# --- response models ----------------------------------------------------------------------------


class Change(BaseModel):
    change_id: str
    doc_id: str
    instrument: str
    section_key: str
    old_section_key: str | None
    section_type: str | None
    heading: str | None
    change_type: str
    from_version: str
    to_version: str
    from_date: date
    to_date: date
    is_synthetic: bool
    source_url: str
    summary: str | None = Field(None, description="AI-generated")
    topics: list[str] | None = Field(None, description="AI-generated")
    sectors: list[str] | None = Field(None, description="AI-generated")
    impact: str | None = Field(None, description="AI-generated")
    impact_rationale: str | None = Field(None, description="AI-generated")
    enrichment_model: str | None = None
    prompt_version: str | None = None
    enriched_at: datetime | None = None
    is_enriched: bool
    enrichment_failed: bool
    similarity: float | None


class ChangeDetail(Change):
    old_text: str | None
    new_text: str | None
    diff_html: str | None = Field(
        None, description="Word-level diff; all source text is HTML-escaped, only <del>/<ins> tags"
    )


class Document(BaseModel):
    doc_id: str
    instrument: str
    title: str | None
    celex_base: str
    doc_type: str | None
    versions: int
    latest_version: date | None
    repealed: bool
    changes: int
    source_url: str


class Freshness(BaseModel):
    last_successful_ingest: datetime | None
    days_since_ingest: int | None
    failures_last_7_days: int


class InstrumentTypeCount(BaseModel):
    instrument: str
    change_type: str
    changes: int


class Overview(BaseModel):
    instruments: int
    versions_parsed: int
    changes: int
    high_impact: int
    enriched: int
    latest_change_date: date | None
    changes_by_instrument_and_type: list[InstrumentTypeCount]
    freshness: Freshness


class TopicCount(BaseModel):
    instrument: str
    year: int
    topic: str
    changes: int


class Run(BaseModel):
    stage: str
    subject: str | None
    status: str | None
    started_at: datetime | None
    finished_at: datetime | None
    seconds: float | None
    rows_in: int | None
    rows_out: int | None
    error: str | None
    run_id: str


class LlmUsage(BaseModel):
    model: str
    prompt_version: str
    succeeded: int
    failed: int
    tokens_in: int | None
    tokens_out: int | None
    tokens_per_change: float | None
    shadow_cost_usd: float | None
    shadow_cost_per_1000_changes: float | None
    median_latency_ms: float | None


class Meta(BaseModel):
    topics: list[str]
    sectors: list[str]
    impacts: list[str]
    change_types: list[str]
    disclaimer: str
    ask_enabled: bool


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


# --- rate limiting ------------------------------------------------------------------------------


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


# --- app factory --------------------------------------------------------------------------------


def create_app(
    warehouse_path: Path | None = None,
    answerer_factory: Callable[[duckdb.DuckDBPyConnection], Answerer] | None = None,
    ask_limit: RateLimiter | None = None,
    daily_ask_limit: RateLimiter | None = None,
    cors_origins: list[str] | None = None,
    frontend_dist: Path | None = None,
) -> FastAPI:
    limiter = ask_limit or RateLimiter(max_calls=10, window_s=60)
    # Protects a shared free-tier key: questions per day across all users get LLM answers;
    # beyond that, /ask returns retrieved passages only.
    daily = daily_ask_limit or RateLimiter(max_calls=200, window_s=24 * 3600)
    state: dict[str, Any] = {}

    def db_path() -> str:
        if "db_path" not in state:
            settings = get_settings()
            path = warehouse_path or resolve_warehouse(
                Path(settings.warehouse_path),
                os.environ.get("HF_DATASET_REPO"),
                os.environ.get("HF_TOKEN"),
            )
            state["db_path"] = str(path)
        return str(state["db_path"])

    def db() -> Iterator[duckdb.DuckDBPyConnection]:
        con = duckdb.connect(db_path(), read_only=True)
        try:
            yield con
        finally:
            con.close()

    Db = Annotated[duckdb.DuckDBPyConnection, Depends(db)]
    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health(con: Db) -> dict[str, Any]:
        row = con.execute("SELECT count(*) FROM changes").fetchone()
        return {"status": "ok", "changes": row[0] if row else 0}

    @api.get("/meta", response_model=Meta)
    def meta() -> dict[str, Any]:
        return {
            "topics": TOPICS,
            "sectors": SECTORS,
            "impacts": ["high", "medium", "low", "unrated"],
            "change_types": ["added", "removed", "modified", "renumbered"],
            "disclaimer": DISCLAIMER,
            "ask_enabled": bool(get_settings().llm_api_key) or answerer_factory is not None,
        }

    def _freshness(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        fresh = queries.freshness(con)
        last = fresh["last_successful_ingest"]
        fresh["days_since_ingest"] = (datetime.now() - last).days if last else None
        return fresh

    @api.get("/freshness", response_model=Freshness)
    def freshness(con: Db) -> dict[str, Any]:
        return _freshness(con)

    @api.get("/overview", response_model=Overview)
    def overview(con: Db) -> dict[str, Any]:
        return {**queries.overview(con), "freshness": _freshness(con)}

    @api.get("/documents", response_model=list[Document])
    def documents(con: Db) -> list[dict[str, Any]]:
        return queries.documents(con)

    @api.get("/changes", response_model=list[Change])
    def list_changes(
        con: Db,
        doc_id: Annotated[list[str] | None, Query()] = None,
        topic: Annotated[list[str] | None, Query()] = None,
        sector: Annotated[list[str] | None, Query()] = None,
        impact: Annotated[list[str] | None, Query()] = None,
        change_type: Annotated[list[str] | None, Query()] = None,
        date_from: date | None = None,
        date_to: date | None = None,
        include_synthetic: bool = False,
        limit: int = Query(500, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> list[dict[str, Any]]:
        allowed_impacts = {"low", "medium", "high", "unrated"}
        if impact and not set(impact) <= allowed_impacts:
            raise HTTPException(422, f"impact must be one of {sorted(allowed_impacts)}")
        filters = queries.ChangeFilters(
            doc_ids=tuple(doc_id or ()),
            topics=tuple(topic or ()),
            sectors=tuple(sector or ()),
            impacts=tuple(impact or ()),
            change_types=tuple(change_type or ()),
            date_from=date_from,
            date_to=date_to,
            include_synthetic=include_synthetic,
            limit=limit,
            offset=offset,
        )
        return queries.changes(con, filters)

    @api.get("/changes/{change_id}", response_model=ChangeDetail)
    def get_change(con: Db, change_id: str) -> dict[str, Any]:
        detail = queries.change_detail(con, change_id)
        if detail is None:
            raise HTTPException(404, "change not found")
        return detail

    @api.get("/trends", response_model=list[TopicCount])
    def trends(con: Db) -> list[dict[str, Any]]:
        return queries.topic_counts(con)

    @api.get("/runs", response_model=list[Run])
    def runs(
        con: Db,
        stage: str | None = None,
        only_failed: bool = False,
        limit: int = Query(500, ge=1, le=2000),
    ) -> list[dict[str, Any]]:
        return queries.pipeline_runs(con, stage, only_failed, limit)

    @api.get("/llm-usage", response_model=list[LlmUsage])
    def llm_usage(con: Db) -> list[dict[str, Any]]:
        return queries.llm_usage(con)

    @api.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest, request: Request, con: Db) -> dict[str, Any]:
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(429, "too many questions; try again in a minute")
        if "answerer" not in state:
            state["answerer"] = (answerer_factory or _default_answerer)(con)
        answerer: Answerer = state["answerer"]
        if not daily.allow("global"):
            answerer = Answerer(
                answerer.index, answerer.embedder, None, answerer.model, answerer.urls,
                answerer.config,
            )  # fmt: skip
        from regtracker.index.search import Filters

        result = answerer.ask(body.question, Filters(doc_ids=(body.doc_id,) if body.doc_id else ()))
        note = result.note
        if answerer.llm is None and result.status == "retrieval_only":
            note = "Daily question limit reached; showing the most relevant passages."
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
            "note": note,
        }  # fmt: skip

    app = FastAPI(
        title="EU Regulation Change Tracker API",
        description=f"Read-only access to detected changes and cited Q&A. {DISCLAIMER}",
        version="0.2.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:5173"],  # Vite dev server
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(api)
    _mount_frontend(app, frontend_dist or _default_dist())
    return app


def _default_dist() -> Path:
    return Path(os.environ.get("FRONTEND_DIST", "frontend/dist"))


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built single-page app; unknown non-API paths return index.html."""
    index = dist / "index.html"
    if not index.exists():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        # index.html names the hashed asset files of the current build; a cached copy would
        # point at assets a redeploy has removed, so browsers must revalidate it.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def _default_answerer(con: duckdb.DuckDBPyConnection) -> Answerer:
    """Real embedder and LLM. LLM calls are logged to an in-memory table: the API never writes
    to the warehouse."""
    from regtracker.common.db import init_schema
    from regtracker.enrich.llm_client import OpenAICompatibleLLM, load_llm_config
    from regtracker.index.embed import E5Embedder
    from regtracker.index.search import SearchIndex
    from regtracker.rag.answer import source_urls

    settings = get_settings()
    llm_config = load_llm_config(settings)
    llm_con = duckdb.connect(":memory:")
    init_schema(llm_con)
    llm = OpenAICompatibleLLM(settings, llm_config, llm_con) if settings.llm_api_key else None
    return Answerer(
        SearchIndex.load(con), E5Embedder(), llm, llm_config.summary_model, source_urls(con),
        load_rag_config(),
    )  # fmt: skip


app = create_app()
