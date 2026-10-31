"""Parser tests on real Cellar XHTML saved in tests/fixtures/xhtml (see its README)."""

import gzip
import re
from pathlib import Path

import pytest
from lxml import html

from regtracker.parse.xhtml_parser import ParseError, Section, parse_document

FIXTURES = Path(__file__).parent / "fixtures" / "xhtml"


def load(name: str) -> bytes:
    path = FIXTURES / name
    data = path.read_bytes()
    return gzip.decompress(data) if path.suffix == ".gz" else data


def by_key(sections: list[Section]) -> dict[str, Section]:
    return {s.section_key: s for s in sections}


def article_titles(raw: bytes) -> int:
    """Independent count of "Article N" titles, by a different route than the parser."""
    root = html.fromstring(raw, parser=html.HTMLParser(encoding="utf-8"))
    titles = root.xpath('//p[@class="title-article-norm"]')
    return sum(bool(re.match(r"Article\s", t.text_content().strip())) for t in titles)


# Golden counts. ePrivacy (Directive 2002/58/EC) has 21 articles; the 2009 amendment inserted
# Articles 14a and 15a. Other counts are cross-checked against the article titles in the file.
@pytest.mark.parametrize(
    ("fixture", "variant", "articles", "annexes"),
    [
        ("eprivacy_2006-05-03.xhtml", "legacy", 21, 0),
        ("eprivacy_2009-12-19.xhtml", "modern", 23, 0),
        ("eidas_2024-10-18.xhtml.gz", "modern", 82, 7),
        ("eecc_2018-12-17.xhtml.gz", "modern", 127, 13),
        ("avmsd_2010-05-05.xhtml.gz", "legacy", 36, 2),
    ],
)
def test_golden_counts(fixture: str, variant: str, articles: int, annexes: int) -> None:
    raw = load(fixture)
    doc = parse_document(raw)

    assert doc.variant == variant
    assert sum(s.section_type == "article" for s in doc.sections) == articles
    assert sum(s.section_type == "annex" for s in doc.sections) == annexes
    assert article_titles(raw) == articles
    assert [s.position for s in doc.sections] == list(range(len(doc.sections)))
    assert all(s.text for s in doc.sections)


def test_unchanged_articles_hash_identically_across_markup_variants() -> None:
    old = by_key(parse_document(load("eprivacy_2006-05-03.xhtml")).sections)
    new = by_key(parse_document(load("eprivacy_2009-12-19.xhtml")).sections)

    unchanged = {k for k in old if old[k].text_hash == new[k].text_hash}
    # Articles 7-12, 14 and 16-21 were not amended in 2009.
    assert unchanged == {f"art_{n}" for n in [7, 8, 9, 10, 11, 12, 14, 16, 17, 18, 19, 20, 21]}


def test_article_fields_and_clean_text() -> None:
    art = by_key(parse_document(load("eidas_2024-10-18.xhtml.gz")).sections)["art_2"]

    assert (art.number, art.heading) == ("2", "Scope")
    assert art.text.startswith("1. This Regulation applies to electronic identification schemes")
    assert "\n2. This Regulation does not apply" in art.text
    assert art.amended_by == ["32024R1183"]


def test_amendment_markers_and_footnote_refs_are_stripped() -> None:
    doc = parse_document(load("eidas_2024-10-18.xhtml.gz"))
    art26 = by_key(doc.sections)["art_26"]

    assert not any(re.search(r"[▼►◄]", s.text) for s in doc.sections)
    assert art26.text.startswith("An advanced electronic signature shall meet")
    assert "32024R1183" in art26.amended_by  # inline marker still recorded
    assert "Regulation (EU) 2016/679 of the European Parliament and of the Council." in (
        by_key(doc.sections)["art_2"].text
    )  # "(1)" footnote reference removed without leaving "()"


def test_annex_numbers_come_from_titles_not_broken_ids() -> None:
    # In this file Annex IX has id "anx_\xa0I" and Annex X "anx_\xa0".
    doc = parse_document(load("eecc_2018-12-17.xhtml.gz"))
    annexes = [s.section_key for s in doc.sections if s.section_type == "annex"]

    numerals = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]
    assert annexes == [f"annex_{n}" for n in numerals]
    assert by_key(doc.sections)["annex_IX"].heading is not None


def test_legacy_chapter_headings_do_not_leak_into_articles() -> None:
    doc = parse_document(load("avmsd_2010-05-05.xhtml.gz"))

    for s in doc.sections:
        assert not re.search(r"\n(CHAPTER|TITLE|SECTION) [IVXLC]+", s.text), s.section_key
    assert by_key(doc.sections)["art_28"].text.endswith("can be subject to judicial review.")


def test_list_labels_stay_on_their_line() -> None:
    annex = by_key(parse_document(load("eidas_2024-10-18.xhtml.gz")).sections)["annex_I"]
    assert "\n(a) an indication, at least in a form suitable for automated processing" in annex.text


def test_repeal_notice_has_no_sections() -> None:
    doc = parse_document(load("universal_service_2020-12-21_repealed.xhtml"))

    assert doc.variant == "repealed"
    assert doc.sections == []
    assert doc.repealed_by == ["32018L1972"]


def test_document_title() -> None:
    doc = parse_document(load("eprivacy_2009-12-19.xhtml"))
    assert doc.title is not None
    assert doc.title.startswith(
        "DIRECTIVE 2002/58/EC OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL"
    )


def test_unknown_markup_is_an_error() -> None:
    with pytest.raises(ParseError):
        parse_document(b"<html><body><p>nothing here</p></body></html>")


def test_duplicate_keys_are_an_error() -> None:
    raw = b"""<html><body>
      <div id="art_1"><p class="title-article-norm">Article 1</p><p>a</p></div>
      <div id="art_1"><p class="title-article-norm">Article 1</p><p>b</p></div>
    </body></html>"""
    with pytest.raises(ParseError, match="duplicate"):
        parse_document(raw)


def test_headings_have_no_amendment_markers() -> None:
    doc = parse_document(load("eprivacy_2009-12-19.xhtml"))
    assert by_key(doc.sections)["art_4"].heading == "Security of processing"
    assert not any(s.heading and re.search(r"[▼►◄]", s.heading) for s in doc.sections)
