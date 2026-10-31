"""Deterministic section-level diff between two versions of the same document.

No LLM is involved: what changed is decided here, by key matching and hashes. The LLM may later
explain these changes, never discover them.
"""

import hashlib
import html
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

ChangeType = Literal["added", "removed", "modified", "renumbered"]

RENUMBER_THRESHOLD = 0.9
_TOKEN = re.compile(r"\s+|[^\s]+")


@dataclass(frozen=True)
class SectionText:
    section_key: str
    section_type: str
    text: str
    text_hash: str


@dataclass(frozen=True)
class Change:
    section_key: str  # key in the new version (old key for `removed`)
    old_section_key: str | None
    section_type: str
    change_type: ChangeType
    old_text: str | None
    new_text: str | None
    similarity: float | None
    diff_html: str | None


def similarity(old: str, new: str) -> float:
    """0..1 word-level similarity."""
    return SequenceMatcher(None, old.split(), new.split(), autojunk=False).ratio()


def diff_html(old: str, new: str) -> str:
    """Word-level diff with escaped text: `<del>` for removed words, `<ins>` for inserted ones."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    out: list[str] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(html.escape("".join(a[i1:i2])))
            continue
        if op in ("delete", "replace"):
            out.append(f"<del>{html.escape(''.join(a[i1:i2]))}</del>")
        if op in ("insert", "replace"):
            out.append(f"<ins>{html.escape(''.join(b[j1:j2]))}</ins>")
    return "".join(out)


def _match_renumbered(
    removed: list[SectionText], added: list[SectionText]
) -> list[tuple[SectionText, SectionText, float]]:
    """Greedy best-first pairing of removed and added sections of the same type above threshold."""
    candidates = [
        (similarity(r.text, a.text), i, j)
        for i, r in enumerate(removed)
        for j, a in enumerate(added)
        if r.section_type == a.section_type
    ]
    pairs: list[tuple[SectionText, SectionText, float]] = []
    used_r: set[int] = set()
    used_a: set[int] = set()
    for score, i, j in sorted(candidates, key=lambda c: (-c[0], c[1], c[2])):
        if score < RENUMBER_THRESHOLD:
            break
        if i in used_r or j in used_a:
            continue
        used_r.add(i)
        used_a.add(j)
        pairs.append((removed[i], added[j], score))
    return pairs


def diff_sections(old: list[SectionText], new: list[SectionText]) -> list[Change]:
    """Changes needed to go from `old` to `new`, in new-document order then removals."""
    old_by_key = {s.section_key: s for s in old}
    new_by_key = {s.section_key: s for s in new}

    removed = [s for s in old if s.section_key not in new_by_key]
    added = [s for s in new if s.section_key not in old_by_key]
    renumbered = _match_renumbered(removed, added)
    renumbered_old = {r.section_key for r, _, _ in renumbered}
    renumbered_new = {a.section_key: (r, score) for r, a, score in renumbered}

    changes: list[Change] = []
    for s in new:
        if s.section_key in renumbered_new:
            r, score = renumbered_new[s.section_key]
            changes.append(
                Change(
                    s.section_key,
                    r.section_key,
                    s.section_type,
                    "renumbered",
                    r.text,
                    s.text,
                    score,
                    diff_html(r.text, s.text),
                )
            )
        elif s.section_key not in old_by_key:
            changes.append(
                Change(s.section_key, None, s.section_type, "added", None, s.text, None, None)
            )
        elif old_by_key[s.section_key].text_hash != s.text_hash:
            o = old_by_key[s.section_key]
            changes.append(
                Change(
                    s.section_key,
                    s.section_key,
                    s.section_type,
                    "modified",
                    o.text,
                    s.text,
                    similarity(o.text, s.text),
                    diff_html(o.text, s.text),
                )
            )
    for o in removed:
        if o.section_key not in renumbered_old:
            changes.append(
                Change(
                    o.section_key,
                    o.section_key,
                    o.section_type,
                    "removed",
                    o.text,
                    None,
                    None,
                    None,
                )
            )
    return changes


def change_id(doc_id: str, from_version: str, to_version: str, change: Change) -> str:
    """Deterministic id, so rerunning the diff never creates duplicates."""
    raw = "|".join(
        [
            doc_id,
            from_version,
            to_version,
            change.change_type,
            change.old_section_key or "",
            change.section_key,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
