"""CLI entry point. One command per pipeline stage; stages are implemented week by week."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from regtracker.common.config import get_settings, load_instruments
from regtracker.common.db import TABLES, warehouse
from regtracker.common.fixture_db import build_fixture_db
from regtracker.common.http import PoliteClient
from regtracker.diff.stage import diff_all
from regtracker.enrich.enrich import DEFAULT_PROMPT_VERSION, enrich_pending, read_change_ids
from regtracker.enrich.llm_client import OpenAICompatibleLLM, load_llm_config
from regtracker.ingest.fetch import ingest_all
from regtracker.parse.stage import parse_pending

DEFAULT_FIXTURE_DB = Path("data/fixture.duckdb")
DEFAULT_SNAPSHOT_DIR = Path("data/snapshot")

app = typer.Typer(help="EU Regulation Change Tracker", no_args_is_help=True)
console = Console()


@app.command("init-db")
def init_db() -> None:
    """Create the DuckDB warehouse and all tables (idempotent)."""
    settings = get_settings()
    with warehouse(settings.warehouse_path) as con:
        for table in TABLES:
            count = con.execute(f"SELECT count(*) FROM {table}").fetchone()
            console.print(f"{table}: {count[0] if count else 0} rows")
    console.print(f"[green]Warehouse ready:[/green] {settings.warehouse_path}")


@app.command("sources")
def sources() -> None:
    """List configured instruments."""
    for inst in load_instruments():
        console.print(f"{inst.doc_id:10} {inst.celex_base}  {inst.doc_type}")


@app.command()
def ingest(
    doc: str | None = typer.Option(None, help="doc_id from configs/sources.yml"),
    all_docs: bool = typer.Option(False, "--all", help="Ingest every configured instrument"),
) -> None:
    """Discover and download new versions. Without options, ingests everything."""
    instruments = load_instruments()
    if doc and all_docs:
        raise typer.BadParameter("use either --doc or --all, not both")
    if doc:
        instruments = [i for i in instruments if i.doc_id == doc]
        if not instruments:
            raise typer.BadParameter(f"unknown doc_id {doc!r}; see `regtracker sources`")

    settings = get_settings()
    with warehouse(settings.warehouse_path) as con, PoliteClient(settings) as client:
        reports = ingest_all(con, client, instruments, settings.raw_dir)

    for r in reports:
        if r.error:
            console.print(f"[red]{r.doc_id:10} failed:[/red] {r.error}")
            continue
        line = f"{r.doc_id:10} {r.discovered} discovered, {r.new} new, {r.already_known} known"
        if r.duplicate_content:
            line += f", {r.duplicate_content} duplicate content"
        console.print(line)
        for item in r.unavailable:
            console.print(f"[yellow]  unavailable:[/yellow] {item}")
    total_new = sum(r.new for r in reports)
    console.print(f"[green]{total_new} new versions[/green]")
    if any(r.error for r in reports):
        raise typer.Exit(code=1)


@app.command()
def parse(
    doc: str | None = typer.Option(None, help="doc_id, or omit for all"),
    all_docs: bool = typer.Option(False, "--all", help="Parse every document (default)"),
    force: bool = typer.Option(
        False, "--force", help="Rebuild sections and changes from raw files (after parser fixes)"
    ),
) -> None:
    """Parse raw XHTML of unparsed versions into sections."""
    settings = get_settings()
    with warehouse(settings.warehouse_path) as con:
        reports = parse_pending(con, doc, force=force)
    for r in reports:
        if r.error:
            console.print(f"[red]{r.version_id:24} failed:[/red] {r.error}")
        else:
            console.print(f"{r.version_id:24} {r.variant:6} {r.sections} sections")
    console.print(f"[green]{sum(not r.error for r in reports)} versions parsed[/green]")
    if any(r.error for r in reports):
        raise typer.Exit(code=1)


@app.command()
def diff(
    doc: str | None = typer.Option(None, help="doc_id, or omit for all"),
    all_docs: bool = typer.Option(False, "--all", help="Diff every document (default)"),
) -> None:
    """Compute section-level changes between consecutive versions (deterministic, no LLM)."""
    settings = get_settings()
    with warehouse(settings.warehouse_path) as con:
        reports = diff_all(con, doc)
        for r in reports:
            counts = con.execute(
                "SELECT change_type, count(*) FROM changes WHERE from_version = ? "
                "AND to_version = ? GROUP BY 1 ORDER BY 1",
                [r.from_version, r.to_version],
            ).fetchall()
            summary = ", ".join(f"{n} {t}" for t, n in counts) or "no changes"
            console.print(f"{r.from_version} -> {r.to_version}: {summary} ({r.new} new)")
    console.print(f"[green]{sum(r.new for r in reports)} new changes[/green]")


@app.command()
def snapshot(
    out: Annotated[Path, typer.Option(help="Output folder")] = DEFAULT_SNAPSHOT_DIR,
    site_url: str = typer.Option("https://github.com/", help="Link used in the RSS feed"),
    upload: bool = typer.Option(False, help="Upload to HF_DATASET_REPO using HF_TOKEN"),
) -> None:
    """Export warehouse + RSS feed for the dashboard; optionally upload to Hugging Face."""
    import os

    from regtracker.app.publish import export_snapshot, upload_snapshot

    settings = get_settings()
    files = export_snapshot(settings.warehouse_path, out, site_url)
    for f in files:
        console.print(f"wrote {f} ({f.stat().st_size // 1024} KB)")
    if upload:
        repo, token = os.environ.get("HF_DATASET_REPO"), os.environ.get("HF_TOKEN")
        if not repo or not token:
            raise typer.BadParameter("set HF_DATASET_REPO and HF_TOKEN to upload")
        console.print(f"[green]Uploaded:[/green] {upload_snapshot(out, repo, token)}")


@app.command("fixture-db", hidden=True)
def fixture_db(
    out: Annotated[Path, typer.Option(help="Output path")] = DEFAULT_FIXTURE_DB,
) -> None:
    """Build a small warehouse from tests/fixtures (no network); used by CI and dbt tests."""
    build_fixture_db(out)
    console.print(f"[green]Fixture warehouse ready:[/green] {out}")


@app.command()
def enrich(
    model: str | None = typer.Option(None, help="Model id (default: summary model in configs)"),
    prompt_version: str = typer.Option(
        DEFAULT_PROMPT_VERSION, help="Prompt file in enrich/prompts"
    ),
    limit: int | None = typer.Option(None, help="Enrich at most N changes this run"),
    retry_failed: bool = typer.Option(False, help="Also retry changes whose last attempt failed"),
    ids_file: Annotated[
        Path | None,
        typer.Option(
            help="Only these changes: a CSV with a change_id column (e.g. the labeled eval set) "
            "or a text file with one id per line"
        ),
    ] = None,
) -> None:
    """Explain detected changes with the LLM (resumable, cached, budget-aware)."""
    change_ids = read_change_ids(ids_file) if ids_file else None
    settings = get_settings()
    config = load_llm_config(settings)
    chosen = model or config.summary_model
    with warehouse(settings.warehouse_path) as con:
        llm = OpenAICompatibleLLM(settings, config, con)
        report = enrich_pending(
            con,
            llm,
            config,
            chosen,
            prompt_version,
            limit=limit,
            retry_failed=retry_failed,
            change_ids=change_ids,
        )
    console.print(
        f"{chosen} {prompt_version}: {report.pending} pending, {report.succeeded} succeeded, "
        f"{report.failed} failed, {report.llm_calls} LLM calls, {report.tokens} tokens"
    )
    if report.stopped_reason:
        console.print(f"[yellow]Stopped early:[/yellow] {report.stopped_reason}")


@app.command()
def index(
    history: bool = typer.Option(False, help="Also index older versions (flagged not latest)"),
) -> None:
    """Chunk the latest version of each document and embed the chunks (cached by text hash)."""
    from regtracker.index.embed import E5Embedder
    from regtracker.index.stage import build_index
    from regtracker.rag.answer import load_rag_config

    settings = get_settings()
    rag = load_rag_config()
    with warehouse(settings.warehouse_path) as con:
        report = build_index(con, E5Embedder(), rag.chunk_max_tokens, include_history=history)
    console.print(
        f"[green]{report.chunks} chunks[/green] from {report.sections} sections "
        f"({report.embedded} newly embedded, the rest from cache)"
    )


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question about the tracked legal texts"),
    doc: str | None = typer.Option(None, help="Restrict to one doc_id"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Show retrieved passages only"),
) -> None:
    """Answer a question with citations (refuses when the evidence is weak)."""
    from regtracker.index.embed import E5Embedder
    from regtracker.index.search import Filters, SearchIndex
    from regtracker.rag.answer import Answerer, load_rag_config, source_urls

    settings = get_settings()
    rag = load_rag_config()
    with warehouse(settings.warehouse_path) as con:
        llm_config = load_llm_config(settings)
        llm = None if no_llm else OpenAICompatibleLLM(settings, llm_config, con)
        answerer = Answerer(
            SearchIndex.load(con), E5Embedder(), llm, llm_config.summary_model,
            source_urls(con), rag,
        )  # fmt: skip
        result = answerer.ask(question, Filters(doc_ids=(doc,) if doc else ()))

    console.print(f"[bold]{result.status}[/bold] (confidence: {result.confidence})")
    if result.answer:
        console.print(result.answer)
        for c in result.citations:
            console.print(f"  [{c.n}] {c.breadcrumb}  {c.source_url}")
    if result.note:
        console.print(f"[yellow]{result.note}[/yellow]")
    if not result.answer:
        for n, h in enumerate(result.retrieved, start=1):
            console.print(f"  [{n}] {h.breadcrumb} (cosine {h.cosine:.3f})")


if __name__ == "__main__":
    app()
