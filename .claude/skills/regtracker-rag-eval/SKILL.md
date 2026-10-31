---
name: regtracker-rag-eval
description: How to build chunking, embeddings, hybrid search, cited answer generation, refusal gating, and the evaluation harness for the EU Regulation Change Tracker. Use this skill whenever working on embeddings, BM25 plus vector retrieval, RRF, citations, the /ask endpoint, hallucination controls, labeled datasets, hit@k, MRR, F1 or accuracy metrics, experiments, or the evaluation report, even if the user just says "RAG", "search", "eval", or "metrics".
---

# RAG and evaluation

Follow `regtracker-conventions`.

## Chunking and embeddings
- Chunk by structure: article paragraph groups of ~200-400 tokens, never crossing article boundaries. Prefix each chunk with a breadcrumb (`GDPR > Article 17 > Right to erasure`).
- Model: `intfloat/multilingual-e5-small` (384 dims). E5 convention: prefix passages with `passage: ` and queries with `query: `. Cache embeddings by text hash.
- Index only the latest version by default; flag for historical search.

## Hybrid retrieval
DuckDB full-text search (BM25) plus cosine similarity over embeddings, merged with Reciprocal Rank Fusion. Support filters (instrument, date range, section type). Return scores and `section_id`s.

## Answering
- Number the context passages. The model must answer only from them, end every sentence with `[n]`, and reply exactly `NOT_FOUND` when the context lacks the answer.
- **Citation validator:** reject any citation not in the retrieved set; map `[n]` to section_id and official URL.
- **Refusal gate:** if the top retrieval score is under a tuned threshold, skip the LLM and return the closest passages with "not enough evidence".
- Response shape: `answer`, `citations[]`, `confidence`, `retrieved[]`.
- Respect the LLM budget (see `regtracker-enrichment-groq`); on budget exhaustion return retrieval-only results.

## Evaluation
Datasets in `eval/datasets/`: `changes_labeled.csv` (60-100 real changes: topics, sectors, impact, notes), `qa_set.jsonl` (about 40 in-scope questions with gold sections, plus about 10 out-of-scope). Freeze or split dev/test before tuning; keep few-shot examples out. Write a one-page labeling guide first and re-label a 20-item subset a week later to report self-agreement.

| Component | Metrics |
|---|---|
| Diff | precision/recall on a verified sample; renumbering false-positive rate |
| Classification | topic and sector F1 (micro/macro), impact accuracy and within-one-level, confusion matrix |
| Summaries | human faithfulness rating 1-5 on ~20 samples (LLM-as-judge optional, flagged as biased) |
| Retrieval | hit@1/3/5, MRR |
| Answers | citation validity (must be 100%), citation correctness (manual, ~20), refusal accuracy |
| System | tokens/change, latency, shadow cost per 1,000 changes |

Experiments to tabulate: small vs larger model for classification, with vs without few-shot, vector vs BM25 vs hybrid, chunk size 200 vs 400.

`eval/run_eval.py --suite all --out eval/reports/` writes machine-readable results; `docs/eval-report.md` presents tables plus an honest failure analysis and limitations. Report real numbers only; never invent or round up.
