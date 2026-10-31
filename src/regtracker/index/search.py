"""Hybrid retrieval: Okapi BM25 + cosine similarity over E5 embeddings, fused with RRF.

BM25 is implemented here rather than with DuckDB's FTS extension, which must be downloaded at
runtime (breaks offline CI and the hosted demo); see ADR-003. The corpus is small, so both
rankings are computed in memory.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Literal

import duckdb
import numpy as np
from numpy.typing import NDArray

from regtracker.index.embed import Embedder, query

Mode = Literal["hybrid", "bm25", "vector"]
RRF_K = 60
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in",
        "is", "it", "its", "of", "on", "or", "shall", "that", "the", "this", "to", "which",
        "with", "what", "does", "do", "how", "who", "when", "where", "must", "any",
    }
)  # fmt: skip


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg_len = (sum(self.len) / len(docs)) if docs else 0.0
        df: Counter[str] = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query_tokens: list[str]) -> NDArray[np.float64]:
        out = np.zeros(len(self.tf))
        for i, tf in enumerate(self.tf):
            norm = self.k1 * (1 - self.b + self.b * self.len[i] / (self.avg_len or 1))
            out[i] = sum(
                self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + norm)
                for t in query_tokens
                if t in tf
            )
        return out


@dataclass(frozen=True)
class Filters:
    doc_ids: tuple[str, ...] = ()
    section_types: tuple[str, ...] = ()
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    section_id: str
    doc_id: str
    version_date: date
    section_key: str
    section_type: str
    breadcrumb: str
    text: str
    score: float  # RRF score in hybrid mode, else the single ranking's score
    bm25: float
    cosine: float


class SearchIndex:
    def __init__(self, rows: list[tuple[object, ...]], embeddings: NDArray[np.float32]) -> None:
        self.rows = rows
        self.embeddings = embeddings
        self.bm25 = BM25([tokenize(str(r[7])) for r in rows])

    @classmethod
    def load(cls, con: duckdb.DuckDBPyConnection, include_history: bool = False) -> "SearchIndex":
        rows = con.execute(
            "SELECT chunk_id, section_id, doc_id, version_date, section_key, section_type, "
            "breadcrumb, text, embedding FROM chunks WHERE is_latest OR ? ORDER BY chunk_id",
            [include_history],
        ).fetchall()
        matrix = np.array([r[8] for r in rows], dtype=np.float32).reshape(len(rows), -1)
        return cls([r[:8] for r in rows], matrix)

    def _mask(self, f: Filters) -> NDArray[np.bool_]:
        def keep(row: tuple[object, ...]) -> bool:
            doc, vdate, stype = row[2], row[3], row[5]
            return not (
                (f.doc_ids and doc not in f.doc_ids)
                or (f.section_types and stype not in f.section_types)
                or (f.date_from and vdate < f.date_from)  # type: ignore[operator]
                or (f.date_to and vdate > f.date_to)  # type: ignore[operator]
            )

        return np.array([keep(r) for r in self.rows], dtype=bool)

    def search(
        self,
        text: str,
        embedder: Embedder | None,
        k: int = 5,
        mode: Mode = "hybrid",
        filters: Filters = Filters(),  # noqa: B008 - frozen dataclass, safe default
        candidates: int = 50,
    ) -> list[Hit]:
        if not self.rows:
            return []
        mask = self._mask(filters)
        bm25 = self.bm25.scores(tokenize(text))
        if mode != "bm25":
            if embedder is None:
                raise ValueError(f"mode {mode!r} needs an embedder")
            qv = embedder.embed([query(text)])[0]
            cosine = self.embeddings @ qv
        else:
            cosine = np.zeros(len(self.rows))

        def ranked(scores: NDArray[np.floating]) -> list[int]:
            order = [int(i) for i in np.argsort(-scores, kind="stable") if mask[i]]
            return order[:candidates]

        if mode == "bm25":
            order, final = ranked(bm25), bm25
        elif mode == "vector":
            order, final = ranked(cosine), cosine
        else:
            fused: dict[int, float] = {}
            for ranking in (ranked(bm25), ranked(cosine)):
                for rank, i in enumerate(ranking):
                    fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
            order = sorted(fused, key=lambda i: (-fused[i], i))
            final = np.zeros(len(self.rows))
            for i, s in fused.items():
                final[i] = s
        if mode == "bm25":
            order = [i for i in order if bm25[i] > 0]  # no lexical match is not a result

        return [self._hit(i, float(final[i]), float(bm25[i]), float(cosine[i])) for i in order[:k]]

    def _hit(self, i: int, score: float, bm25: float, cosine: float) -> Hit:
        chunk_id, section_id, doc_id, vdate, key, stype, crumb, text = self.rows[i]
        return Hit(
            str(chunk_id), str(section_id), str(doc_id), vdate,  # type: ignore[arg-type]
            str(key), str(stype), str(crumb), str(text), score, bm25, cosine,
        )  # fmt: skip
