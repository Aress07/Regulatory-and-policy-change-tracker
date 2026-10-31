"""Structural chunking: paragraph groups inside one section, never crossing section boundaries."""

from dataclasses import dataclass

from regtracker.common.text import sha256_text

DEFAULT_MAX_TOKENS = 300


def approx_tokens(text: str) -> int:
    """~4/3 tokens per English word; good enough for sizing chunks."""
    return (len(text.split()) * 4 + 2) // 3


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    section_id: str
    breadcrumb: str
    body: str

    @property
    def text(self) -> str:
        """What is indexed and shown: breadcrumb line, then the paragraphs."""
        return f"{self.breadcrumb}\n{self.body}"

    @property
    def text_hash(self) -> str:
        return sha256_text(self.text)


def breadcrumb(doc_name: str, section_type: str, number: str, heading: str | None) -> str:
    label = f"{'Annex' if section_type == 'annex' else 'Article'} {number}"
    return " > ".join(part for part in (doc_name, label, heading) if part)


def chunk_section(
    section_id: str, crumb: str, text: str, max_tokens: int = DEFAULT_MAX_TOKENS
) -> list[Chunk]:
    """Group paragraphs up to `max_tokens`; a single overlong paragraph is split by words."""
    pieces: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if approx_tokens(paragraph) <= max_tokens:
            pieces.append(paragraph)
            continue
        step = max(max_tokens * 3 // 4, 1)  # words per piece
        pieces.extend(" ".join(words[i : i + step]) for i in range(0, len(words), step))

    groups: list[list[str]] = [[]]
    size = 0
    for piece in pieces:
        n = approx_tokens(piece)
        if groups[-1] and size + n > max_tokens:
            groups.append([])
            size = 0
        groups[-1].append(piece)
        size += n
    return [
        Chunk(f"{section_id}#c{i}", section_id, crumb, "\n".join(group))
        for i, group in enumerate(groups)
        if group
    ]
