"""Build a small warehouse from the saved XHTML fixtures (no network), for CI and dbt tests."""

import hashlib
import shutil
from pathlib import Path

from regtracker.common.db import warehouse
from regtracker.common.runs import log_run, new_run_id, utcnow
from regtracker.diff.stage import diff_all
from regtracker.parse.stage import parse_pending

FIXTURE_DIR = Path("tests/fixtures/xhtml")

# (doc_id, celex_base, doc_type, version_date, celex_version, fixture file)
FIXTURE_VERSIONS = [
    ("eprivacy", "32002L0058", "directive", "2006-05-03", "02002L0058-20060503",
     "eprivacy_2006-05-03.xhtml"),
    ("eprivacy", "32002L0058", "directive", "2009-12-19", "02002L0058-20091219",
     "eprivacy_2009-12-19.xhtml"),
    ("universal_service", "32002L0022", "directive", "2020-12-21", "02002L0022-20201221",
     "universal_service_2020-12-21_repealed.xhtml"),
]  # fmt: skip


def build_fixture_db(out: Path, fixture_dir: Path = FIXTURE_DIR) -> None:
    """Create `out` from scratch: documents, versions, sections and changes from fixtures."""
    if out.exists():
        out.unlink()
    raw_dir = out.parent / "fixture_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    with warehouse(out) as con:
        run_id, started = new_run_id(), utcnow()
        for doc_id, celex_base, doc_type, date, celex, name in FIXTURE_VERSIONS:
            raw_path = raw_dir / name
            shutil.copy(fixture_dir / name, raw_path)
            con.execute(
                "INSERT INTO documents (doc_id, celex_base, doc_type) VALUES (?, ?, ?) "
                "ON CONFLICT DO NOTHING",
                [doc_id, celex_base, doc_type],
            )
            con.execute(
                "INSERT INTO document_versions (version_id, doc_id, celex, version_date, "
                "source_url, fetched_at, content_hash, raw_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    f"{doc_id}@{date}",
                    doc_id,
                    celex,
                    date,
                    f"http://publications.europa.eu/resource/celex/{celex}",
                    utcnow(),
                    hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                    raw_path.as_posix(),
                ],
            )
        log_run(
            con,
            run_id=run_id,
            stage="ingest:fixtures",
            started_at=started,
            finished_at=utcnow(),
            status="success",
            rows_in=len(FIXTURE_VERSIONS),
            rows_out=len(FIXTURE_VERSIONS),
        )
        parse_pending(con)
        diff_all(con)
