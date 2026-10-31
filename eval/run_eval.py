"""Evaluation driver. Writes eval/reports/results.json and eval/reports/summary.md.

    python eval/run_eval.py --suite all --out eval/reports/
    python eval/run_eval.py --suite answers --with-llm      # spends LLM budget

Suites: retrieval (modes x chunk sizes), gate (refusal threshold), classification
(enrichments vs eval/datasets/changes_labeled.csv), system (tokens, latency, shadow cost),
answers (end-to-end with the LLM; optional). Numbers are reported as measured, never rounded up.
Labels with status "draft" were proposed by an LLM and are not human gold; results on them are
marked provisional.
"""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from regtracker.common.config import get_settings
from regtracker.common.db import init_schema
from regtracker.enrich.schemas import SECTORS, TOPICS
from regtracker.evaluation.metrics import (
    best_threshold,
    gate_accuracy,
    impact_metrics,
    multilabel_f1,
    retrieval_metrics,
)
from regtracker.index.embed import E5Embedder, embed_passages_cached
from regtracker.index.search import Hit, SearchIndex
from regtracker.index.stage import collect_chunks

DATASETS = Path("eval/datasets")
CHUNK_SIZES = (200, 300, 400)
MODES = ("bm25", "vector", "hybrid")


def load_qa() -> list[dict[str, Any]]:
    lines = (DATASETS / "qa_set.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def ranked_sections(hits: list[Hit]) -> list[str]:
    """Section-level ranking (first occurrence of each section) as "doc:section_key"."""
    seen: list[str] = []
    for h in hits:
        key = f"{h.doc_id}:{h.section_key}"
        if key not in seen:
            seen.append(key)
    return seen


def build_indexes(con: duckdb.DuckDBPyConnection, embedder: E5Embedder) -> dict[int, SearchIndex]:
    indexes = {}
    for size in CHUNK_SIZES:
        _, chunks = collect_chunks(con, size)
        vectors, misses = embed_passages_cached(con, embedder, [c.text for c, _ in chunks])
        print(f"chunk size {size}: {len(chunks)} chunks ({misses} newly embedded)")
        indexes[size] = SearchIndex.from_chunks(chunks, vectors)
    return indexes


def suite_retrieval(
    indexes: dict[int, SearchIndex], embedder: E5Embedder, qa: list[dict[str, Any]]
) -> dict[str, Any]:
    in_scope = [q for q in qa if q["in_scope"]]
    results: dict[str, Any] = {}
    for size, index in indexes.items():
        for mode in MODES:
            for split in ("dev", "test", "all"):
                subset = [q for q in in_scope if split == "all" or q["split"] == split]
                runs = [
                    (
                        ranked_sections(index.search(q["question"], embedder, 20, mode)),
                        set(q["gold"]),
                    )
                    for q in subset
                ]
                results[f"{mode}@{size}/{split}"] = retrieval_metrics(runs)
    return results


def suite_gate(
    index: SearchIndex, embedder: E5Embedder, qa: list[dict[str, Any]]
) -> dict[str, Any]:
    """Tune the refusal threshold on dev (best cosine of hybrid top-5), report on test."""
    scores: dict[str, dict[str, list[float]]] = {s: {"in": [], "out": []} for s in ("dev", "test")}
    per_question = []
    for q in qa:
        hits = index.search(q["question"], embedder, 5, "hybrid")
        best = max((h.cosine for h in hits), default=0.0)
        scores[q["split"]]["in" if q["in_scope"] else "out"].append(best)
        per_question.append(
            {"id": q["id"], "in_scope": q["in_scope"], "best_cosine": round(best, 4)}
        )
    threshold, dev_acc = best_threshold(scores["dev"]["in"], scores["dev"]["out"])
    return {
        "threshold_tuned_on_dev": threshold,
        "dev": gate_accuracy(threshold, scores["dev"]["in"], scores["dev"]["out"]),
        "test": gate_accuracy(threshold, scores["test"]["in"], scores["test"]["out"]),
        "per_question": per_question,
    }


def suite_classification(
    con: duckdb.DuckDBPyConnection, model: str, prompt_version: str
) -> dict[str, Any]:
    path = DATASETS / "changes_labeled.csv"
    if not path.exists():
        return {"skipped": "eval/datasets/changes_labeled.csv not found"}
    with path.open(encoding="utf-8", newline="") as f:
        labels = list(csv.DictReader(f))
    predicted = {
        r[0]: r[1:]
        for r in con.execute(
            "SELECT change_id, topics, sectors, impact FROM enrichments "
            "WHERE status = 'success' AND model = ? AND prompt_version = ?",
            [model, prompt_version],
        ).fetchall()
    }
    rows = [r for r in labels if r["change_id"] in predicted]
    if not rows:
        return {"skipped": f"no labeled changes enriched by {model} {prompt_version}"}
    split = lambda s: {x.strip() for x in s.split("|") if x.strip()}  # noqa: E731
    gold_topics = [split(r["topics"]) for r in rows]
    gold_sectors = [split(r["sectors"]) for r in rows]
    statuses = {r.get("status", "draft") for r in rows}
    return {
        "model": model,
        "prompt_version": prompt_version,
        "n": len(rows),
        "label_status": sorted(statuses),
        "provisional": statuses != {"verified"},
        "topics": _f1_json(
            multilabel_f1(gold_topics, [set(predicted[r["change_id"]][0]) for r in rows], TOPICS)
        ),
        "sectors": _f1_json(
            multilabel_f1(gold_sectors, [set(predicted[r["change_id"]][1]) for r in rows], SECTORS)
        ),
        "impact": impact_metrics(
            [r["impact"] for r in rows], [predicted[r["change_id"]][2] for r in rows]
        ),
        "primary_topic_accuracy": sum(
            r["topics"].split("|")[0].strip() in predicted[r["change_id"]][0][:1] for r in rows
        )
        / len(rows),
    }


def _f1_json(result: dict[str, Any]) -> dict[str, Any]:
    micro = result["micro"]
    return {
        "micro_precision": micro.precision,
        "micro_recall": micro.recall,
        "micro_f1": micro.f1,
        "macro_f1": result["macro_f1"],
        "per_label_f1": {k: v.f1 for k, v in result["per_label"].items()},
    }


def suite_system(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    rows = con.execute(
        "SELECT model, prompt_version, count(*) FILTER (WHERE status = 'success'), "
        "count(*) FILTER (WHERE status = 'failed'), avg(tokens_in + tokens_out), "
        "median(latency_ms), 1000 * avg(shadow_cost_usd), sum(shadow_cost_usd) "
        "FROM enrichments GROUP BY 1, 2 ORDER BY 1, 2"
    ).fetchall()
    total = con.execute("SELECT count(*) FROM changes").fetchone()
    return {
        "changes_total": total[0] if total else 0,
        "enrichment": [
            {
                "model": m, "prompt_version": pv, "succeeded": ok, "failed": bad,
                "tokens_per_change": tok, "median_latency_ms": lat,
                "shadow_cost_per_1000_changes_usd": cost1000, "shadow_cost_total_usd": total_cost,
            }
            for m, pv, ok, bad, tok, lat, cost1000, total_cost in rows
        ],
    }  # fmt: skip


def suite_answers(
    con: duckdb.DuckDBPyConnection, index: SearchIndex, embedder: E5Embedder,
    qa: list[dict[str, Any]], threshold: float,
) -> dict[str, Any]:  # fmt: skip
    from regtracker.enrich.llm_client import OpenAICompatibleLLM, load_llm_config
    from regtracker.rag.answer import Answerer, RagConfig, load_rag_config, source_urls

    settings = get_settings()
    llm_config = load_llm_config(settings)
    base = load_rag_config()
    config = RagConfig(
        base.top_k, base.chunk_max_tokens, threshold, base.max_question_chars, base.prompt_version
    )
    llm = OpenAICompatibleLLM(settings, llm_config, con)
    answerer = Answerer(index, embedder, llm, llm_config.summary_model, source_urls(con), config)

    records = []
    for q in [q for q in qa if q["split"] == "test"]:
        r = answerer.ask(q["question"])
        cited = {f"{c.section_id.split('@')[0]}:{c.section_id.split('#')[1]}" for c in r.citations}
        records.append({
            "id": q["id"], "in_scope": q["in_scope"], "status": r.status, "answer": r.answer,
            "citations": sorted(cited), "cites_gold": bool(cited & set(q["gold"])),
            "uncited_sentences": r.uncited_sentences, "note": r.note,
        })  # fmt: skip
    answered = [x for x in records if x["status"] == "answered"]
    in_scope = [x for x in records if x["in_scope"]]
    out_scope = [x for x in records if not x["in_scope"]]
    refused = {"not_found", "not_enough_evidence"}
    return {
        "model": llm_config.summary_model,
        "threshold": threshold,
        "n": len(records),
        # Every returned answer passed the validator; rejected ones are counted separately.
        "citation_validity_of_returned_answers": 1.0 if answered else None,
        "rejected_invalid_citations": sum(
            x["status"] == "rejected_invalid_citations" for x in records
        ),
        "in_scope_answered": sum(x["status"] == "answered" for x in in_scope)
        / (len(in_scope) or 1),
        "answers_citing_gold_section": sum(x["cites_gold"] for x in answered if x["in_scope"])
        / (len([x for x in answered if x["in_scope"]]) or 1),
        "out_of_scope_refused": sum(x["status"] in refused for x in out_scope)
        / (len(out_scope) or 1),
        "retrieval_only_fallbacks": sum(x["status"] == "retrieval_only" for x in records),
        "records": records,
    }


def write_summary(results: dict[str, Any], out: Path) -> None:
    lines = [f"# Evaluation summary ({results['generated_at']})", ""]
    if "retrieval" in results:
        lines += [
            "## Retrieval (section level, in-scope questions)",
            "",
            "| Mode @ chunk tokens | split | n | hit@1 | hit@3 | hit@5 | MRR |",
            "|---|---|---|---|---|---|---|",
        ]
        for key, m in results["retrieval"].items():
            setting, split = key.split("/")
            lines.append(
                f"| {setting} | {split} | {int(m['n'])} | {m['hit@1']:.3f} | {m['hit@3']:.3f} | "
                f"{m['hit@5']:.3f} | {m['mrr']:.3f} |"
            )
        lines.append("")
    if "gate" in results:
        g = results["gate"]
        lines += [
            "## Refusal gate",
            "",
            f"Threshold tuned on dev: {g['threshold_tuned_on_dev']:.4f}",
            "",
            "| split | accuracy | in-scope answered | out-of-scope refused |",
            "|---|---|---|---|",
        ]
        for split in ("dev", "test"):
            m = g[split]
            lines.append(
                f"| {split} | {m['accuracy']:.3f} | {m['in_scope_answered']:.3f} "
                f"| {m['out_of_scope_refused']:.3f} |"
            )
        lines.append("")
    if "classification" in results:
        lines += [
            "## Classification",
            "",
            "```json",
            json.dumps(results["classification"], indent=2, default=str),
            "```",
            "",
        ]
    if "system" in results:
        lines += [
            "## System",
            "",
            "```json",
            json.dumps(results["system"], indent=2, default=str),
            "```",
            "",
        ]
    if "answers" in results:
        a = {k: v for k, v in results["answers"].items() if k != "records"}
        lines += [
            "## Answers (test split, real LLM)",
            "",
            "```json",
            json.dumps(a, indent=2, default=str),
            "```",
            "",
        ]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        default="all",
        choices=["all", "retrieval", "gate", "classification", "system", "answers"],
    )
    parser.add_argument("--out", default="eval/reports/")
    parser.add_argument("--with-llm", action="store_true", help="also run the answers suite")
    parser.add_argument("--model", default=None, help="enrichment model to evaluate")
    parser.add_argument("--prompt-version", default="v1")
    args = parser.parse_args()  # fmt: skip

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    con = duckdb.connect(str(settings.warehouse_path))
    init_schema(con)
    qa = load_qa()
    results: dict[str, Any] = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds")}
    wanted = lambda s: args.suite in ("all", s)  # noqa: E731

    needs_index = any(wanted(s) for s in ("retrieval", "gate")) or args.suite == "answers"
    if needs_index:
        embedder = E5Embedder()
        indexes = build_indexes(con, embedder)
    if wanted("retrieval"):
        results["retrieval"] = suite_retrieval(indexes, embedder, qa)
    if wanted("gate") or args.suite == "answers":
        results["gate"] = suite_gate(indexes[300], embedder, qa)
    if wanted("classification"):
        from regtracker.enrich.llm_client import load_llm_config

        model = args.model or load_llm_config(settings).summary_model
        results["classification"] = suite_classification(con, model, args.prompt_version)
    if wanted("system"):
        results["system"] = suite_system(con)
    if args.suite == "answers" or (args.suite == "all" and args.with_llm):
        results["answers"] = suite_answers(
            con, indexes[300], embedder, qa, results["gate"]["threshold_tuned_on_dev"]
        )
    con.close()

    name = "results.json" if args.suite == "all" else f"results_{args.suite}.json"
    (out / name).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    write_summary(results, out)
    print(f"wrote {out / name} and {out / 'summary.md'}")


if __name__ == "__main__":
    main()
