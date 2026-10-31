"""Embeddings with intfloat/multilingual-e5-small, cached in DuckDB by (model, text hash)."""

from typing import Protocol

import duckdb
import numpy as np
from numpy.typing import NDArray

from regtracker.common.text import sha256_text

E5_MODEL = "intfloat/multilingual-e5-small"
DIM = 384


class Embedder(Protocol):
    model_name: str

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        """L2-normalized vectors for already-prefixed texts."""
        ...


class E5Embedder:
    """sentence-transformers E5. Callers add the `passage: ` / `query: ` prefixes."""

    def __init__(self, model_name: str = E5_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device="cpu")

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        vectors = self._model.encode(
            texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)


def passage(text: str) -> str:
    return f"passage: {text}"


def query(text: str) -> str:
    return f"query: {text}"


def embed_passages_cached(
    con: duckdb.DuckDBPyConnection, embedder: Embedder, texts: list[str]
) -> tuple[NDArray[np.float32], int]:
    """Embeddings for `texts` (in order), computing only cache misses. Returns (vectors, misses)."""
    hashes = [sha256_text(t) for t in texts]
    cached: dict[str, list[float]] = {}
    if hashes:
        rows = con.execute(
            "SELECT text_hash, embedding FROM embedding_cache "
            "WHERE model = ? AND text_hash IN (SELECT unnest(?::VARCHAR[]))",
            [embedder.model_name, list(set(hashes))],
        ).fetchall()
        cached = {h: e for h, e in rows}

    missing = [(h, t) for h, t in dict(zip(hashes, texts, strict=True)).items() if h not in cached]
    if missing:
        vectors = embedder.embed([passage(t) for _, t in missing])
        con.executemany(
            "INSERT INTO embedding_cache (model, text_hash, embedding) VALUES (?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [
                [embedder.model_name, h, v.tolist()]
                for (h, _), v in zip(missing, vectors, strict=True)
            ],
        )
        cached.update({h: v.tolist() for (h, _), v in zip(missing, vectors, strict=True)})

    matrix = np.array([cached[h] for h in hashes], dtype=np.float32).reshape(len(hashes), DIM)
    return matrix, len(missing)
