import gzip
import random
import shutil
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from regtracker.common.db import connect, init_schema
from regtracker.common.text import sha256_text
from regtracker.diff.article_diff import (
    SectionText,
    change_id,
    diff_html,
    diff_sections,
    similarity,
)
from regtracker.diff.stage import diff_all
from regtracker.parse.stage import parse_pending

FIXTURES = Path(__file__).parent / "fixtures" / "xhtml"

PENALTY = (
    "Member States shall lay down the rules on penalties applicable to infringements of the "
    "national provisions adopted pursuant to this Directive and shall take all measures necessary "
    "to ensure that they are implemented. The penalties provided for must be effective, "
    "proportionate and dissuasive."
)


def sec(key: str, text: str, section_type: str = "article") -> SectionText:
    return SectionText(key, section_type, text, sha256_text(text))


def kinds(changes: list) -> dict[str, str]:  # type: ignore[type-arg]
    return {c.section_key: c.change_type for c in changes}


def test_added_removed_modified() -> None:
    old = [
        sec("art_1", "Scope."),
        sec("art_2", "Fines up to EUR 10 million."),
        sec("art_3", "Gone."),
    ]
    new = [
        sec("art_1", "Scope."),
        sec("art_2", "Fines up to EUR 20 million."),
        sec("art_4", "New."),
    ]

    changes = diff_sections(old, new)

    assert kinds(changes) == {"art_2": "modified", "art_4": "added", "art_3": "removed"}
    modified = next(c for c in changes if c.change_type == "modified")
    assert modified.old_text == "Fines up to EUR 10 million."
    assert modified.similarity is not None and 0 < modified.similarity < 1
    assert "<del>10</del><ins>20</ins>" in (modified.diff_html or "")


def test_cosmetic_differences_are_not_changes() -> None:
    old = [sec("art_1", "The controller’s  duty applies.")]
    new = [sec("art_1", "The controller's duty applies.")]
    assert diff_sections(old, new) == []


def test_identical_versions_have_no_changes() -> None:
    sections = [sec(f"art_{i}", f"text {i}") for i in range(10)]
    assert diff_sections(sections, list(sections)) == []


def test_renumbering_is_detected_instead_of_add_and_remove() -> None:
    old = [sec("art_1", "Scope."), sec("art_15", PENALTY)]
    new = [sec("art_1", "Scope."), sec("art_15a", PENALTY.replace("must be", "shall be"))]

    [change] = diff_sections(old, new)

    assert change.change_type == "renumbered"
    assert (change.old_section_key, change.section_key) == ("art_15", "art_15a")
    assert change.similarity is not None and change.similarity >= 0.9


def test_dissimilar_add_and_remove_are_not_renumbering() -> None:
    old = [sec("art_15", PENALTY)]
    new = [sec("art_16", "Member States shall designate a supervisory authority.")]
    assert kinds(diff_sections(old, new)) == {"art_16": "added", "art_15": "removed"}


def test_renumbering_never_crosses_section_types() -> None:
    old = [sec("art_9", PENALTY)]
    new = [sec("annex_I", PENALTY, "annex")]
    assert kinds(diff_sections(old, new)) == {"annex_I": "added", "art_9": "removed"}


@pytest.mark.parametrize("seed", range(20))
def test_swapping_versions_inverts_changes(seed: int) -> None:
    rng = random.Random(seed)
    words = [
        "member",
        "state",
        "shall",
        "ensure",
        "provider",
        "data",
        "service",
        "fine",
        "authority",
    ]

    def random_version() -> list[SectionText]:
        keys = rng.sample(range(1, 15), k=rng.randint(3, 10))
        return [sec(f"art_{k}", " ".join(rng.choices(words, k=12))) for k in sorted(keys)]

    a, b = random_version(), random_version()

    def inverted(change_type: str, old_key: str | None, new_key: str) -> tuple[str, str]:
        """(change_type, key) the reverse diff must report for a forward change."""
        if change_type == "renumbered":
            return "renumbered", old_key or ""
        return {"added": "removed", "removed": "added"}.get(change_type, change_type), new_key

    forward = {
        inverted(c.change_type, c.old_section_key, c.section_key) for c in diff_sections(a, b)
    }
    backward = {(c.change_type, c.section_key) for c in diff_sections(b, a)}
    assert backward == forward


def test_modified_always_has_different_text() -> None:
    rng = random.Random(7)
    old = [sec(f"art_{i}", f"text {rng.randint(0, 3)}") for i in range(30)]
    new = [sec(f"art_{i}", f"text {rng.randint(0, 3)}") for i in range(30)]
    for c in diff_sections(old, new):
        if c.change_type == "modified":
            assert c.old_text != c.new_text


def test_diff_html_escapes_markup() -> None:
    out = diff_html("a < b", "a <script> b")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_similarity_bounds() -> None:
    assert similarity("a b c", "a b c") == 1.0
    assert similarity("a b c", "x y z") == 0.0


def test_change_id_is_deterministic_and_distinct() -> None:
    [c] = diff_sections([sec("art_1", "a")], [sec("art_1", "b")])
    assert change_id("d", "v1", "v2", c) == change_id("d", "v1", "v2", c)
    assert change_id("d", "v1", "v2", c) != change_id("d", "v2", "v3", c)


# --- stage integration: real ePrivacy pair through parse and diff -----------------------------


@pytest.fixture
def warehouse_with_eprivacy(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(tmp_path / "w.duckdb")
    init_schema(con)
    con.execute("INSERT INTO documents (doc_id, celex_base) VALUES ('eprivacy', '32002L0058')")
    for date, name in [
        ("2006-05-03", "eprivacy_2006-05-03.xhtml"),
        ("2009-12-19", "eprivacy_2009-12-19.xhtml"),
    ]:
        shutil.copy(FIXTURES / name, tmp_path / name)
        con.execute(
            "INSERT INTO document_versions (version_id, doc_id, celex, version_date, source_url, "
            "fetched_at, content_hash, raw_path) VALUES (?, 'eprivacy', ?, ?, 'u', now(), 'h', ?)",
            [f"eprivacy@{date}", f"02002L0058-{date.replace('-', '')}", date, name],
        )
    # A repeal notice must not produce a version pair or "removed" changes.
    repeal = tmp_path / "repealed.xhtml"
    repeal.write_bytes((FIXTURES / "universal_service_2020-12-21_repealed.xhtml").read_bytes())
    con.execute(
        "INSERT INTO document_versions (version_id, doc_id, celex, version_date, source_url, "
        "fetched_at, content_hash, raw_path) VALUES "
        "('eprivacy@2030-01-01', 'eprivacy', 'x', '2030-01-01', 'u', now(), 'h2', 'repealed.xhtml')"
    )
    yield con
    con.close()


def test_parse_and_diff_real_pair(
    warehouse_with_eprivacy: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    con = warehouse_with_eprivacy

    parsed = parse_pending(con, base_dir=tmp_path)
    assert [r.error for r in parsed] == [None, None, None]
    statuses = dict(
        con.execute("SELECT version_id, parse_status FROM document_versions").fetchall()
    )
    assert statuses["eprivacy@2030-01-01"] == "repealed"

    [report] = diff_all(con)
    assert (report.from_version, report.to_version) == (
        "eprivacy@2006-05-03",
        "eprivacy@2009-12-19",
    )
    counts = dict(con.execute("SELECT change_type, count(*) FROM changes GROUP BY 1").fetchall())
    assert counts == {"added": 2, "modified": 8}
    added = {
        r[0]
        for r in con.execute("SELECT section_key FROM changes WHERE change_type='added'").fetchall()
    }
    assert added == {"art_14a", "art_15a"}

    # Reruns change nothing.
    assert parse_pending(con, base_dir=tmp_path) == []
    assert diff_all(con)[0].new == 0
    assert con.execute("SELECT count(*) FROM changes").fetchone() == (10,)


def test_force_reparse_rebuilds_identically(
    warehouse_with_eprivacy: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    con = warehouse_with_eprivacy
    parse_pending(con, base_dir=tmp_path)
    diff_all(con)
    before = con.execute("SELECT change_id FROM changes ORDER BY 1").fetchall()

    parse_pending(con, base_dir=tmp_path, force=True)
    diff_all(con)

    assert con.execute("SELECT change_id FROM changes ORDER BY 1").fetchall() == before


def test_gzip_fixtures_are_valid() -> None:
    for path in FIXTURES.glob("*.gz"):
        assert b"<html" in gzip.decompress(path.read_bytes())[:500]


def test_fixture_db_builds_offline(tmp_path: Path) -> None:
    from regtracker.common.fixture_db import build_fixture_db

    out = tmp_path / "fixture.duckdb"
    build_fixture_db(out, FIXTURES)
    con = duckdb.connect(str(out), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM changes").fetchone() == (10,)
        statuses = sorted(
            r[0] for r in con.execute("SELECT parse_status FROM document_versions").fetchall()
        )
        assert statuses == ["parsed", "parsed", "repealed"]
    finally:
        con.close()
