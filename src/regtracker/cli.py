"""CLI entry point. One command per pipeline stage; stages are implemented week by week."""

import typer
from rich.console import Console

from regtracker.common.config import get_settings, load_instruments
from regtracker.common.db import TABLES, warehouse
from regtracker.common.http import PoliteClient
from regtracker.ingest.fetch import ingest_all

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
def parse() -> None:
    """Parse raw XHTML into sections (week 2)."""
    _todo("parse", 2)


@app.command()
def diff() -> None:
    """Compute article-level changes between versions (week 2)."""
    _todo("diff", 2)


@app.command()
def enrich() -> None:
    """LLM enrichment of changes (week 3)."""
    _todo("enrich", 3)


@app.command()
def index() -> None:
    """Chunk and embed sections (week 4)."""
    _todo("index", 4)


if __name__ == "__main__":
    app()
