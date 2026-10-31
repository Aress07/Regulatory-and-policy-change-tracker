"""Cited question answering over the latest legal texts.

Guarantees:
- The LLM sees only retrieved passages and must cite them as [n].
- Refusal gate: weak retrieval (best cosine below `min_cosine`) never reaches the LLM.
- Citation validator: an answer citing any passage outside the retrieved set is rejected.
- Degrades to retrieval-only results when the LLM is unavailable or over budget.
"""

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import duckdb
import yaml

from regtracker.enrich.llm_client import LLM, BudgetExceededError
from regtracker.index.embed import Embedder
from regtracker.index.search import Filters, Hit, Mode, SearchIndex

RAG_CONFIG_PATH = Path("configs/rag.yml")
_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")
EURLEX = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:"

Status = Literal[
    "answered",
    "not_found",
    "not_enough_evidence",
    "rejected_invalid_citations",
    "retrieval_only",
]


@dataclass(frozen=True)
class RagConfig:
    top_k: int = 5
    chunk_max_tokens: int = 300
    min_cosine: float = 0.80
    max_question_chars: int = 500
    prompt_version: str = "qa-v1"


def load_rag_config(path: Path = RAG_CONFIG_PATH) -> RagConfig:
    return RagConfig(**yaml.safe_load(path.read_text(encoding="utf-8")))


def answer_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }


def load_prompt(version: str) -> str:
    return (resources.files("regtracker.rag") / "prompts" / f"{version}.md").read_text(
        encoding="utf-8"
    )


@dataclass(frozen=True)
class Citation:
    n: int
    section_id: str
    breadcrumb: str
    source_url: str


@dataclass
class AskResult:
    question: str
    status: Status
    answer: str | None
    citations: list[Citation]
    confidence: Literal["high", "medium", "low", "none"]
    retrieved: list[Hit]
    note: str | None = None
    uncited_sentences: int = 0
    tokens: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def parse_citations(answer: str) -> list[int]:
    """All cited passage numbers in order of first appearance; handles [1] and [1, 2]."""
    seen: list[int] = []
    for group in _CITATION.findall(answer):
        for n in (int(x) for x in group.split(",")):
            if n not in seen:
                seen.append(n)
    return seen


def uncited_sentences(answer: str) -> int:
    return sum(1 for s in _SENTENCE.split(answer.strip()) if s and not _CITATION.search(s))


def build_context(hits: list[Hit]) -> str:
    return "\n\n".join(f"[{n}] {h.text}" for n, h in enumerate(hits, start=1))


def source_urls(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """version_id -> official EUR-Lex link of that consolidated version."""
    rows = con.execute("SELECT version_id, celex FROM document_versions").fetchall()
    return {vid: EURLEX + celex for vid, celex in rows}


class Answerer:
    def __init__(
        self,
        index: SearchIndex,
        embedder: Embedder,
        llm: LLM | None,
        model: str,
        urls: dict[str, str],
        config: RagConfig | None = None,
    ) -> None:
        self.index, self.embedder, self.llm, self.model = index, embedder, llm, model
        self.urls = urls
        self.config = config or RagConfig()
        self.prompt = load_prompt(self.config.prompt_version)

    def _url(self, hit: Hit) -> str:
        return self.urls.get(hit.section_id.split("#", 1)[0], "")

    def ask(
        self,
        question: str,
        filters: Filters = Filters(),  # noqa: B008 - frozen dataclass, safe default
        mode: Mode = "hybrid",
    ) -> AskResult:
        question = question.strip()
        if not question or len(question) > self.config.max_question_chars:
            raise ValueError(f"question must be 1-{self.config.max_question_chars} characters")

        hits = self.index.search(question, self.embedder, self.config.top_k, mode, filters)
        best = max((h.cosine for h in hits), default=0.0)
        if not hits or best < self.config.min_cosine:
            return AskResult(
                question, "not_enough_evidence", None, [], "none", hits,
                note=f"best similarity {best:.3f} is below the threshold "
                f"{self.config.min_cosine:.2f}; showing the closest passages instead",
            )  # fmt: skip
        if self.llm is None:
            return AskResult(question, "retrieval_only", None, [], "none", hits, "LLM disabled")

        messages = [
            {"role": "system", "content": self.prompt},
            {
                "role": "user",
                "content": f"Context:\n{build_context(hits)}\n\nQuestion: {question}",
            },
        ]
        try:
            result = self.llm.complete_json(
                self.model, messages, self.config.prompt_version, answer_schema()
            )
            answer = str(json.loads(result.content)["answer"]).strip()
        except BudgetExceededError:
            return AskResult(
                question, "retrieval_only", None, [], "none", hits,
                note="daily LLM budget reached; showing the most relevant passages",
            )  # fmt: skip
        except Exception as exc:  # rate limit, outage, malformed output: degrade, don't fail
            return AskResult(
                question, "retrieval_only", None, [], "none", hits,
                note=f"answer generation unavailable ({type(exc).__name__}); showing passages",
            )  # fmt: skip
        tokens = result.tokens_in + result.tokens_out

        if answer == "NOT_FOUND":
            return AskResult(
                question, "not_found", None, [], "none", hits,
                note="the retrieved passages do not answer this question", tokens=tokens,
            )  # fmt: skip

        cited = parse_citations(answer)
        invalid = [n for n in cited if not 1 <= n <= len(hits)]
        if not cited or invalid:
            return AskResult(
                question, "rejected_invalid_citations", None, [], "none", hits,
                note=f"answer rejected: invalid citations {invalid}" if invalid
                else "answer rejected: no citations",
                tokens=tokens,
            )  # fmt: skip

        citations = [
            Citation(n, hits[n - 1].section_id, hits[n - 1].breadcrumb, self._url(hits[n - 1]))
            for n in cited
        ]
        uncited = uncited_sentences(answer)
        margin = best - self.config.min_cosine
        confidence: Literal["high", "medium", "low"] = (
            "high" if uncited == 0 and margin >= 0.03 else "medium" if uncited == 0 else "low"
        )
        return AskResult(
            question, "answered", answer, citations, confidence, hits,
            uncited_sentences=uncited, tokens=tokens,
        )  # fmt: skip
