"""Chunking, hybrid search and cited answering, with a fake embedder and fake LLM (offline)."""

import hashlib
import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pytest
from numpy.typing import NDArray

from regtracker.common.fixture_db import build_fixture_db
from regtracker.enrich.llm_client import BudgetExceededError, LLMResult
from regtracker.index.chunk import approx_tokens, breadcrumb, chunk_section
from regtracker.index.embed import embed_passages_cached
from regtracker.index.search import BM25, Filters, SearchIndex, tokenize
from regtracker.index.stage import build_index
from regtracker.rag.answer import (
    Answerer,
    RagConfig,
    parse_citations,
    source_urls,
    uncited_sentences,
)

FIXTURES = Path(__file__).parent / "fixtures" / "xhtml"


class FakeEmbedder:
    """Deterministic bag-of-words hashing into 384 dims, L2-normalized. Counts calls."""

    model_name = "fake-embedder"

    def __init__(self) -> None:
        self.calls = 0
        self.texts = 0

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        self.calls += 1
        self.texts += len(texts)
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in re.findall(
                r"[a-z]+", t.lower().removeprefix("query: ").removeprefix("passage: ")
            ):
                out[i, int(hashlib.md5(tok.encode()).hexdigest(), 16) % 384] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


class FakeLLM:
    def __init__(self, answers: list[str] | None = None, error: Exception | None = None) -> None:
        self.answers = list(answers or [])
        self.error = error
        self.calls: list[list[dict[str, str]]] = []

    def complete_json(
        self, model: str, messages: list[dict[str, str]], prompt_version: str,
        schema: dict[str, Any] | None = None,
    ) -> LLMResult:  # fmt: skip
        self.calls.append(messages)
        if self.error:
            raise self.error
        return LLMResult(json.dumps({"answer": self.answers.pop(0)}), model, 10, 5, 1, False)

    def forget(self, model: str, messages: list[dict[str, str]], prompt_version: str) -> None:
        pass


# --- chunking -------------------------------------------------------------------------------


def test_breadcrumb() -> None:
    assert breadcrumb("GDPR", "article", "17", "Right to erasure") == (
        "GDPR > Article 17 > Right to erasure"
    )
    assert breadcrumb("EECC", "annex", "IX", None) == "EECC > Annex IX"


def test_chunks_respect_budget_and_keep_every_word() -> None:
    paragraphs = [f"{i}. " + " ".join(["word"] * 60) for i in range(1, 11)]
    chunks = chunk_section("v#art_1", "X > Article 1", "\n".join(paragraphs), max_tokens=200)

    assert len(chunks) > 1
    assert all(approx_tokens(c.body) <= 200 for c in chunks)
    assert "\n".join(c.body for c in chunks) == "\n".join(paragraphs)
    assert all(c.text.startswith("X > Article 1\n") for c in chunks)
    assert [c.chunk_id for c in chunks] == [f"v#art_1#c{i}" for i in range(len(chunks))]


def test_overlong_paragraph_is_split() -> None:
    chunks = chunk_section("v#art_1", "X", " ".join(["w"] * 1000), max_tokens=100)
    assert all(approx_tokens(c.body) <= 100 for c in chunks)
    assert sum(len(c.body.split()) for c in chunks) == 1000


# --- search ---------------------------------------------------------------------------------


def test_bm25_prefers_documents_with_rare_query_terms() -> None:
    docs = [tokenize(t) for t in ["fines and penalties apply", "scope of the directive", "fines"]]
    scores = BM25(docs).scores(tokenize("penalties"))
    assert scores.argmax() == 0
    assert scores[1] == 0


@pytest.fixture
def indexed(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    out = tmp_path / "fixture.duckdb"
    build_fixture_db(out, FIXTURES)
    con = duckdb.connect(str(out))
    yield con
    con.close()


def test_index_builds_from_latest_version_and_uses_cache(
    indexed: duckdb.DuckDBPyConnection,
) -> None:
    embedder = FakeEmbedder()
    first = build_index(indexed, embedder, max_tokens=300)
    assert first.chunks > 0 and first.embedded == first.chunks

    versions = {r[0] for r in indexed.execute("SELECT DISTINCT version_id FROM chunks").fetchall()}
    assert versions == {"eprivacy@2009-12-19"}  # latest parsed version only

    texts_before = embedder.texts
    second = build_index(indexed, embedder, max_tokens=300)
    assert second.chunks == first.chunks and second.embedded == 0
    assert embedder.texts == texts_before  # all from cache

    history = build_index(indexed, embedder, include_history=True)
    assert history.chunks > first.chunks


def test_embedding_cache_returns_same_vectors(indexed: duckdb.DuckDBPyConnection) -> None:
    embedder = FakeEmbedder()
    a, misses_a = embed_passages_cached(indexed, embedder, ["alpha beta", "gamma"])
    b, misses_b = embed_passages_cached(indexed, embedder, ["gamma", "alpha beta"])
    assert (misses_a, misses_b) == (2, 0)
    assert np.allclose(a[0], b[1]) and np.allclose(a[1], b[0])


def test_hybrid_search_finds_the_right_article(indexed: duckdb.DuckDBPyConnection) -> None:
    embedder = FakeEmbedder()
    build_index(indexed, embedder)
    index = SearchIndex.load(indexed)

    for mode in ("hybrid", "bm25", "vector"):
        hits = index.search("itemised bills for subscribers", embedder, k=3, mode=mode)
        assert hits[0].section_key == "art_7", mode
        assert hits[0].breadcrumb.endswith("Article 7 > Itemised billing")


def test_filters(indexed: duckdb.DuckDBPyConnection) -> None:
    embedder = FakeEmbedder()
    build_index(indexed, embedder)
    index = SearchIndex.load(indexed)

    assert index.search("subscribers", embedder, filters=Filters(doc_ids=("other",))) == []
    assert index.search("subscribers", embedder, filters=Filters(section_types=("annex",))) == []
    future = Filters(date_from=date(2030, 1, 1))
    assert index.search("subscribers", embedder, filters=future) == []
    assert index.search("subscribers", embedder, filters=Filters(doc_ids=("eprivacy",)))


def test_bm25_mode_returns_nothing_without_lexical_match(
    indexed: duckdb.DuckDBPyConnection,
) -> None:
    embedder = FakeEmbedder()
    build_index(indexed, embedder)
    assert SearchIndex.load(indexed).search("zzzqqq", embedder, mode="bm25") == []


# --- answering ------------------------------------------------------------------------------


def test_parse_citations_and_uncited_sentences() -> None:
    answer = "Bills are itemised [1]. Users may refuse [2, 3]. This has no source."
    assert parse_citations(answer) == [1, 2, 3]
    assert uncited_sentences(answer) == 1


@pytest.fixture
def answerer_parts(
    indexed: duckdb.DuckDBPyConnection,
) -> tuple[SearchIndex, FakeEmbedder, dict[str, str]]:
    embedder = FakeEmbedder()
    build_index(indexed, embedder)
    return SearchIndex.load(indexed), embedder, source_urls(indexed)


def make(parts: Any, llm: Any, min_cosine: float = 0.1) -> Answerer:
    index, embedder, urls = parts
    return Answerer(index, embedder, llm, "m", urls, RagConfig(min_cosine=min_cosine))


def test_answer_with_valid_citations(answerer_parts: Any) -> None:
    llm = FakeLLM(["Subscribers can receive non-itemised bills [1]."])
    result = make(answerer_parts, llm).ask("Can subscribers get non-itemised bills?")

    assert result.status == "answered"
    assert result.citations[0].section_id == result.retrieved[0].section_id
    assert result.citations[0].source_url.endswith("CELEX:02002L0058-20091219")
    context = llm.calls[0][1]["content"]
    assert context.startswith("Context:\n[1] ")


def test_invalid_citation_rejects_the_answer(answerer_parts: Any) -> None:
    llm = FakeLLM(["Bills are itemised [9]."])
    result = make(answerer_parts, llm).ask("Can subscribers get non-itemised bills?")
    assert result.status == "rejected_invalid_citations"
    assert result.answer is None and result.citations == []
    assert result.retrieved  # passages still shown


def test_answer_without_citations_is_rejected(answerer_parts: Any) -> None:
    result = make(answerer_parts, FakeLLM(["Yes, they can."])).ask("Itemised bills?")
    assert result.status == "rejected_invalid_citations"


def test_not_found(answerer_parts: Any) -> None:
    result = make(answerer_parts, FakeLLM(["NOT_FOUND"])).ask("Itemised bills?")
    assert result.status == "not_found" and result.answer is None


def test_refusal_gate_skips_the_llm(answerer_parts: Any) -> None:
    llm = FakeLLM(["should not be used [1]."])
    result = make(answerer_parts, llm, min_cosine=0.99).ask("What is the capital of France?")
    assert result.status == "not_enough_evidence"
    assert llm.calls == []
    assert result.note and "below the threshold" in result.note


def test_budget_exhaustion_degrades_to_retrieval_only(answerer_parts: Any) -> None:
    llm = FakeLLM(error=BudgetExceededError("over"))
    result = make(answerer_parts, llm).ask("Itemised bills?")
    assert result.status == "retrieval_only" and result.retrieved


def test_question_length_is_limited(answerer_parts: Any) -> None:
    with pytest.raises(ValueError):
        make(answerer_parts, FakeLLM()).ask("x" * 501)
    with pytest.raises(ValueError):
        make(answerer_parts, FakeLLM()).ask("   ")


def test_repealed_instruments_are_not_indexed_by_default(
    indexed: duckdb.DuckDBPyConnection,
) -> None:
    # Pretend ePrivacy was repealed after its 2009 version.
    indexed.execute(
        "INSERT INTO document_versions (version_id, doc_id, celex, version_date, source_url, "
        "fetched_at, content_hash, raw_path, parse_status) VALUES ('eprivacy@2030-01-01', "
        "'eprivacy', 'x', '2030-01-01', 'u', now(), 'h', 'r', 'repealed')"
    )
    assert build_index(indexed, FakeEmbedder()).chunks == 0
    assert build_index(indexed, FakeEmbedder(), include_history=True).chunks > 0
