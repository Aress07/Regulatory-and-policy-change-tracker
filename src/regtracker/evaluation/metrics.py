"""Evaluation metrics. Pure functions, unit-tested; the eval driver is eval/run_eval.py."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

IMPACT_ORDER = {"low": 0, "medium": 1, "high": 2}


def hit_at_k(ranked: Sequence[str], gold: set[str], k: int) -> float:
    return float(any(r in gold for r in ranked[:k]))


def reciprocal_rank(ranked: Sequence[str], gold: set[str]) -> float:
    for i, r in enumerate(ranked, start=1):
        if r in gold:
            return 1.0 / i
    return 0.0


def retrieval_metrics(runs: list[tuple[Sequence[str], set[str]]]) -> dict[str, float]:
    """hit@1/3/5 and MRR averaged over (ranked section ids, gold ids) pairs."""
    n = len(runs) or 1
    return {
        "n": float(len(runs)),
        "hit@1": sum(hit_at_k(r, g, 1) for r, g in runs) / n,
        "hit@3": sum(hit_at_k(r, g, 3) for r, g in runs) / n,
        "hit@5": sum(hit_at_k(r, g, 5) for r, g in runs) / n,
        "mrr": sum(reciprocal_rank(r, g) for r, g in runs) / n,
    }


@dataclass(frozen=True)
class F1:
    precision: float
    recall: float
    f1: float


def _f1(tp: int, fp: int, fn: int) -> F1:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return F1(p, r, 2 * p * r / (p + r) if p + r else 0.0)


def multilabel_f1(
    gold: list[set[str]], predicted: list[set[str]], labels: Sequence[str]
) -> dict[str, object]:
    """Micro and macro F1 for multi-label sets; macro averages over labels present in gold."""
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    for g, p in zip(gold, predicted, strict=True):
        for label in p & g:
            tp[label] += 1
        for label in p - g:
            fp[label] += 1
        for label in g - p:
            fn[label] += 1
    micro = _f1(sum(tp.values()), sum(fp.values()), sum(fn.values()))
    present = [lab for lab in labels if tp[lab] + fn[lab] > 0]
    per_label = {
        lab: _f1(tp[lab], fp[lab], fn[lab]) for lab in labels if tp[lab] + fp[lab] + fn[lab]
    }
    macro = sum(per_label[lab].f1 for lab in present) / len(present) if present else 0.0
    return {"micro": micro, "macro_f1": macro, "per_label": per_label}


def impact_metrics(gold: list[str], predicted: list[str]) -> dict[str, object]:
    """Accuracy, within-one-level accuracy and a confusion matrix (rows = gold)."""
    n = len(gold) or 1
    exact = sum(g == p for g, p in zip(gold, predicted, strict=True)) / n
    within = (
        sum(
            abs(IMPACT_ORDER[g] - IMPACT_ORDER[p]) <= 1
            for g, p in zip(gold, predicted, strict=True)
        )
        / n
    )
    levels = list(IMPACT_ORDER)
    matrix = {g: {p: 0 for p in levels} for g in levels}
    for g, p in zip(gold, predicted, strict=True):
        matrix[g][p] += 1
    return {"n": len(gold), "accuracy": exact, "within_one": within, "confusion": matrix}


def best_threshold(
    in_scope_scores: list[float], out_scope_scores: list[float]
) -> tuple[float, float]:
    """Threshold maximizing accuracy of "answer if score >= t" (in-scope answered, out-of-scope
    refused). Ties go to the highest threshold (refuse more). Returns (threshold, accuracy)."""
    candidates = sorted(set(in_scope_scores) | set(out_scope_scores))
    total = len(in_scope_scores) + len(out_scope_scores) or 1
    best = (candidates[0] if candidates else 0.0, -1.0)
    for t in candidates:
        correct = sum(s >= t for s in in_scope_scores) + sum(s < t for s in out_scope_scores)
        acc = correct / total
        if acc > best[1] or (acc == best[1] and t > best[0]):
            best = (t, acc)
    return best


def gate_accuracy(
    threshold: float, in_scope_scores: list[float], out_scope_scores: list[float]
) -> dict[str, float]:
    answered = sum(s >= threshold for s in in_scope_scores)
    refused = sum(s < threshold for s in out_scope_scores)
    total = len(in_scope_scores) + len(out_scope_scores) or 1
    return {
        "accuracy": (answered + refused) / total,
        "in_scope_answered": answered / (len(in_scope_scores) or 1),
        "out_of_scope_refused": refused / (len(out_scope_scores) or 1),
    }
