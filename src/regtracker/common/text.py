"""Text normalization and hashing. Hash ONLY normalized text (see conventions)."""

import hashlib
import re
import unicodedata

_QUOTES = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
}
_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """NFC, normalized quotes, NBSP -> space, collapsed whitespace."""
    text = unicodedata.normalize("NFC", text)
    for src, dst in _QUOTES.items():
        text = text.replace(src, dst)
    text = text.replace("\u00a0", " ")
    return _WS.sub(" ", text).strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
