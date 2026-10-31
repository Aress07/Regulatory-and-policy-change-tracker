"""Parse Cellar consolidated-text XHTML into sections (articles, annexes, recitals).

Two markup variants are supported (see `docs/sources.md`):
- `modern` (CONVEX 9.x): articles are `div#art_N`, annexes `div#anx_X`, headings in `.eli-title`.
- `legacy` (CONVEX 5.x): a flat body; each article starts at `p.title-article-norm` and runs until
  the next one, a separator, or the footnotes.

Amendment markers (e.g. "▼M2" linking to the amending act's CELEX) and footnote references are
removed from the text; the amending CELEX numbers are kept per section in `amended_by`.
Consolidated texts carry no recitals, but `div#rct_N` is parsed if present.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from lxml import html
from lxml.html import HtmlElement

from regtracker.common.text import normalize_text, sha256_text

SectionType = Literal["article", "annex", "recital"]
Variant = Literal["modern", "legacy", "repealed"]

_BLOCK_TAGS = {"p", "div", "table", "tr", "li", "ul", "ol", "h1", "h2", "h3", "h4", "br", "hr"}
_INLINE_CLASSES = {"inline-element", "grid-list-column-1", "list", "no-parag"}
_MARKER_CLASSES = {"modref", "arrow"}
_ARTICLE_ID = re.compile(r"^art_(\d+[a-z]*)$")
_ANNEX_ID = re.compile(r"^anx_\s*([A-Za-z0-9]+)$")  # some 2018 texts use "anx_\xa0I"
_RECITAL_ID = re.compile(r"^rct_(\d+)$")
_ANNEX_TITLE = re.compile(r"^ANNEX\s+([IVXLC]+|\d+[a-z]?)\b", re.IGNORECASE)
_ARTICLE_TITLE = re.compile(r"^Article\s+(\d+\s*[a-z]*)$", re.IGNORECASE)
_EMPTY_PARENS = re.compile(r"\s*\(\s*\)")  # left behind by removed footnote references
_BASE_MARKER = re.compile(r"^[▼►◄]?\s*B$")
# Consolidation markers: ▼B (base act), ►M2 (amendment), ►C1 (corrigendum), ►A1 (accession), ◄.
_MARKER = re.compile(r"[▼►]\s*[A-Z]\d*|◄")
_LABEL = re.compile(r"^(\(?[0-9]{1,3}[a-z]?[.)]|\([a-z]{1,2}\)|\([ivxlc]{1,6}\)|[a-z][.)]|[—–-])$")
_BREAK = "\x1e"  # paragraph separator used while walking the tree


class ParseError(Exception):
    """The document does not look like any supported markup variant."""


@dataclass
class Section:
    section_key: str  # art_5 | annex_III | rct_12
    section_type: SectionType
    number: str
    heading: str | None
    text: str  # normalized paragraphs joined by "\n"
    position: int
    amended_by: list[str] = field(default_factory=list)

    @property
    def text_hash(self) -> str:
        return sha256_text(self.text)


@dataclass
class ParsedDocument:
    title: str | None
    variant: Variant
    sections: list[Section]
    repealed_by: list[str] = field(default_factory=list)


def _classes(el: HtmlElement) -> set[str]:
    return set((el.get("class") or "").split())


def _is_footnote_ref(el: HtmlElement) -> bool:
    return el.tag == "a" and (el.get("href") or "").startswith("#E")


def _amendments(el: HtmlElement) -> list[str]:
    """CELEX numbers of amending acts referenced by markers inside `el` (base act excluded).

    Markers appear both as `p.modref` blocks and inline (`<a title="CELEX: INSERTED">►M2</a>`).
    """
    found: list[str] = []
    for link in el.iter("a"):
        label = normalize_text(link.text_content())
        if not _MARKER.fullmatch(label) or _BASE_MARKER.match(label):
            continue
        celex = (link.get("title") or "").split(":")[0].strip()
        if celex and celex not in found:
            found.append(celex)
    return found


def _lines(el: HtmlElement, skip: set[str] | None = None) -> list[str]:
    """Visible text of `el` as normalized lines; drops markers, footnote refs, `skip` classes."""
    skip = (skip or set()) | _MARKER_CLASSES
    parts: list[str] = []

    def walk(node: HtmlElement) -> None:
        if not isinstance(node.tag, str):  # comments, processing instructions
            parts.append(node.tail or "")
            return
        classes = _classes(node)
        if classes & skip or _is_footnote_ref(node):
            parts.append(node.tail or "")
            return
        block = node.tag in _BLOCK_TAGS and not (classes & _INLINE_CLASSES)
        if block:
            parts.append(_BREAK)
        parts.append(node.text or "")
        for child in node:
            walk(child)
        if block:
            parts.append(_BREAK)
        parts.append(node.tail or "")

    walk(el)
    parts.pop()  # the element's own tail is not part of it
    # Source newlines are just pretty-printing; only _BREAK separates paragraphs.
    pieces = (
        normalize_text(_EMPTY_PARENS.sub("", _MARKER.sub("", p)))
        for p in "".join(parts).split(_BREAK)
    )
    return _merge_labels([p for p in pieces if p])


def _merge_labels(lines: list[str]) -> list[str]:
    """Join a bare list label ("1.", "(a)", "—") with the line it labels."""
    merged: list[str] = []
    pending: str | None = None
    for line in lines:
        if _LABEL.match(line):
            pending = f"{pending} {line}" if pending else line
            continue
        merged.append(f"{pending} {line}" if pending else line)
        pending = None
    if pending:
        merged.append(pending)
    return merged


def _document_title(root: HtmlElement) -> str | None:
    first = root.xpath('//p[contains(concat(" ", @class, " "), " title-doc-first ")]')
    last = root.xpath('//p[contains(concat(" ", @class, " "), " title-doc-last ")]')
    if not first:
        return None
    parts = [normalize_text(p.text_content()) for p in [*first, *last]]
    return " ".join(p for p in parts if p) or None


def _text_of(lines: list[str]) -> str:
    return "\n".join(lines)


def _annex_number(el: HtmlElement) -> str | None:
    """Annex number from its visible title, e.g. "ANNEX IX" -> "IX"; None if untitled/unnumbered."""
    titles = el.xpath('.//p[starts-with(@class, "title-annex-1")][1]')
    if not titles:
        return None
    m = _ANNEX_TITLE.match(normalize_text(titles[0].text_content()))
    return m.group(1).upper() if m else None


def _parse_modern(root: HtmlElement) -> list[Section]:
    sections: list[Section] = []
    for el in root.iter("div"):
        el_id = el.get("id") or ""
        if m := _ARTICLE_ID.match(el_id):
            if any(_ANNEX_ID.match(a.get("id") or "") for a in el.iterancestors("div")):
                continue  # article text quoted inside an annex
            number = m.group(1)
            heading_el = el.xpath('./div[contains(concat(" ", @class, " "), " eli-title ")]')
            heading = normalize_text(heading_el[0].text_content()) if heading_el else None
            body = _lines(el, skip={"title-article-norm", "eli-title"})
            sections.append(
                Section(
                    f"art_{number}",
                    "article",
                    number,
                    heading or None,
                    _text_of(body),
                    0,
                    _amendments(el),
                )
            )
        elif el_id.startswith("anx_"):
            # Ids are unreliable in some texts (Annex IX of 02018L1972-20181217 is "anx_\xa0I"),
            # so the visible title wins; the id is only a fallback.
            number = _annex_number(el) or ""
            if not number and (m := _ANNEX_ID.match(el_id)):
                number = m.group(1)
            if not number:
                raise ParseError(f"cannot determine annex number for id {el_id!r}")
            subtitle = el.xpath(
                './/p[starts-with(@class, "title-annex-2") '
                'or starts-with(@class, "title-gr-seq-level-1")][1]'
            )
            heading = normalize_text(subtitle[0].text_content()) if subtitle else None
            body = _lines(el, skip={"title-annex-1", "separator-annex"})
            sections.append(
                Section(
                    f"annex_{number}",
                    "annex",
                    number,
                    heading or None,
                    _text_of(body),
                    0,
                    _amendments(el),
                )
            )
        elif m := _RECITAL_ID.match(el_id):
            number = m.group(1)
            body = [re.sub(r"^\(\d+\)\s*", "", line) for line in _lines(el)]
            sections.append(
                Section(f"rct_{number}", "recital", number, None, _text_of(body), 0, [])
            )
    return sections


@dataclass
class _Open:
    """A legacy section being collected: its kind, number, heading and body blocks."""

    section_type: SectionType
    number: str
    heading: str | None = None
    blocks: list[HtmlElement] = field(default_factory=list)


def _parse_legacy(root: HtmlElement) -> list[Section]:
    """Walk the flat body. Articles and annexes start at their titles; chapter/section headings
    (`title-division-*`) end the current article; separators and footnotes end the document."""
    body = root.xpath("//body")[0]
    sections: list[Section] = []
    current: _Open | None = None
    seen_article = False

    def close() -> None:
        if current is None:
            return
        lines = [line for b in current.blocks for line in _lines(b)]
        amended = [c for b in current.blocks for c in _amendments(b)]
        prefix = "art" if current.section_type == "article" else "annex"
        sections.append(
            Section(
                f"{prefix}_{current.number}",
                current.section_type,
                current.number,
                current.heading,
                _text_of(lines),
                0,
                list(dict.fromkeys(amended)),
            )
        )

    for child in body:
        if not isinstance(child.tag, str):
            continue
        classes = _classes(child)
        if any(c.startswith("separator") for c in classes) or "footnote" in classes:
            if seen_article and "separator-annex" not in classes:
                break  # end of the enacting terms and annexes
            continue
        if "title-article-norm" in classes:
            m = _ARTICLE_TITLE.match(normalize_text(child.text_content()))
            if not m:
                raise ParseError(f"unrecognised article title: {child.text_content()!r}")
            close()
            current, seen_article = _Open("article", m.group(1).replace(" ", "")), True
        elif any(c.startswith("title-annex-1") for c in classes):
            m = _ANNEX_TITLE.match(normalize_text(child.text_content()))
            close()
            current = _Open("annex", m.group(1).upper() if m else str(len(sections) + 1))
        elif any(c.startswith("title-division") for c in classes):
            close()  # chapter/section headings belong to no article
            current = None
        elif current is not None:
            if (
                current.section_type == "article"
                and "stitle-article-norm" in classes
                and current.heading is None
                and not current.blocks
            ):
                current.heading = normalize_text(child.text_content())
            else:
                current.blocks.append(child)
    close()
    return sections


def detect_variant(root: HtmlElement) -> Literal["modern", "legacy"]:
    if root.xpath('//div[starts-with(@id, "art_")]'):
        return "modern"
    if root.xpath('//body/p[@class="title-article-norm"]'):
        return "legacy"
    raise ParseError("no articles found in either supported markup variant")


def repealed_by(root: HtmlElement) -> list[str] | None:
    """CELEX numbers of the repealing acts if this is a repeal notice (no text), else None."""
    for heading in root.xpath('//p[contains(concat(" ", @class, " "), " hd-modifiers ")]'):
        if not normalize_text(heading.text_content()).lower().startswith("repealed by"):
            continue
        table = heading.getnext()
        links = table.iter("a") if table is not None else iter(())
        return [
            href.rsplit("/", 1)[-1]
            for a in links
            if "/resource/celex/" in (href := a.get("href") or "")
        ]
    return None


def parse_document(raw: bytes) -> ParsedDocument:
    """Parse raw XHTML bytes (UTF-8) into ordered sections with unique keys.

    A repeal notice (consolidated "version" that only says the act was repealed) yields no
    sections, variant `repealed`, and the repealing acts in `repealed_by`.
    """
    root = html.fromstring(raw, parser=html.HTMLParser(encoding="utf-8"))
    has_articles = bool(
        root.xpath('//div[starts-with(@id, "art_")] | //body/p[@class="title-article-norm"]')
    )
    if not has_articles and (repealers := repealed_by(root)) is not None:
        return ParsedDocument(_document_title(root), "repealed", [], repealers)
    variant = detect_variant(root)
    sections = _parse_modern(root) if variant == "modern" else _parse_legacy(root)

    seen: set[str] = set()
    for position, section in enumerate(sections):
        if section.section_key in seen:
            raise ParseError(f"duplicate section key {section.section_key}")
        seen.add(section.section_key)
        section.position = position
    return ParsedDocument(_document_title(root), variant, sections)
