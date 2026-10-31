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
from regtracker.enrich.enrich import DEFAULT_PROMPT_VERSION, enrich_pending
from regtracker.enrich.llm_client import OpenAICompatibleLLM, load_llm_config
from regtracker.ingest.fetch import ingest_all
from regtracker.parse.stage import parse_pending

DEFAULT_FIXTURE_DB = Path("data/fixture.duckdb")

app = typer.Typer(help="EU Regulation Change Tracker", no_args_is_help=True)
console = Console()


def _todo(stage: str, week: int) -> None:
    console.print(f"[yellow]{stage}[/yellow] is not implemented yet (planned for week {week}).")
    raise typer.Exit(code=2)


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
) -> None:
    """Explain detected changes with the LLM (resumable, cached, budget-aware)."""
    settings = get_settings()
    config = load_llm_config(settings)
    chosen = model or config.summary_model
    with warehouse(settings.warehouse_path) as con:
        llm = OpenAICompatibleLLM(settings, config, con)
        report = enrich_pending(
            con, llm, config, chosen, prompt_version, limit=limit, retry_failed=retry_failed
        )
    console.print(
        f"{chosen} {prompt_version}: {report.pending} pending, {report.succeeded} succeeded, "
        f"{report.failed} failed, {report.llm_calls} LLM calls, {report.tokens} tokens"
    )
    if report.stopped_reason:
        console.print(f"[yellow]Stopped early:[/yellow] {report.stopped_reason}")


@app.command()
def index() -> None:
    """Chunk and embed sections (week 4)."""
    _todo("index", 4)


if __name__ == "__main__":
    app()
