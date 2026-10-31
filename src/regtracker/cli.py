"""CLI entry point. One command per pipeline stage; stages are implemented week by week."""

import typer
from rich.console import Console

from regtracker.common.config import get_settings, load_instruments
from regtracker.common.db import TABLES, warehouse

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
def ingest(doc: str = typer.Option(None, help="doc_id, or omit for all")) -> None:
    """Discover and download versions (week 1)."""
    _todo("ingest", 1)


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
