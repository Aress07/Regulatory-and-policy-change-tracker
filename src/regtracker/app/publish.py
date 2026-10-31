"""Export a read-only snapshot (warehouse + feed) and upload it to a Hugging Face dataset repo."""

import shutil
from pathlib import Path

import duckdb

from regtracker.app.feed import build_feed, validate_feed
from regtracker.app.snapshot import SNAPSHOT_FILE

SNAPSHOT_README = """---
license: other
tags: [eu-law, regulation, change-tracking]
---
# EU Regulation Change Tracker snapshot

DuckDB warehouse (`warehouse.duckdb`) and RSS feed (`feed.xml`) produced by the EU Regulation
Change Tracker pipeline. Legal texts come from the Publications Office of the EU (Cellar /
EUR-Lex); reuse is subject to the EUR-Lex legal notice. Summaries, tags and impact ratings are
AI-generated and may be wrong. **Not legal advice.**
"""


def export_snapshot(warehouse: Path, out_dir: Path, site_url: str) -> list[Path]:
    """Checkpoint and copy the warehouse, build and validate the feed. Returns written files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse))
    try:
        con.execute("CHECKPOINT")  # fold the WAL into the file before copying
        feed = build_feed(con, site_url)
    finally:
        con.close()
    problems = validate_feed(feed)
    if problems:
        raise ValueError(f"feed is invalid: {problems}")

    db_copy = out_dir / SNAPSHOT_FILE
    shutil.copyfile(warehouse, db_copy)
    feed_path = out_dir / "feed.xml"
    feed_path.write_bytes(feed)
    readme = out_dir / "README.md"
    readme.write_text(SNAPSHOT_README, encoding="utf-8")
    return [db_copy, feed_path, readme]


def upload_snapshot(out_dir: Path, repo_id: str, token: str) -> str:
    """Upload the snapshot folder to a dataset repo (created if missing). Returns the commit URL."""
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(repo_id, repo_type="dataset", exist_ok=True, private=False)
    info = api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=str(out_dir),
        commit_message="Update snapshot",
    )
    return str(info)
