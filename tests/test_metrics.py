import pytest

from regtracker.evaluation.metrics import (
    best_threshold,
    gate_accuracy,
    hit_at_k,
    impact_metrics,
    multilabel_f1,
    reciprocal_rank,
    retrieval_metrics,
)


def test_hit_and_reciprocal_rank() -> None:
    ranked = ["a", "b", "c"]
    assert hit_at_k(ranked, {"b"}, 1) == 0.0
    assert hit_at_k(ranked, {"b"}, 3) == 1.0
    assert reciprocal_rank(ranked, {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(ranked, {"z"}) == 0.0


def test_retrieval_metrics_average() -> None:
    m = retrieval_metrics([(["a", "b"], {"a"}), (["x", "b"], {"b"})])
    assert m["hit@1"] == 0.5 and m["hit@3"] == 1.0 and m["mrr"] == pytest.approx(0.75)


def test_multilabel_f1_micro_and_macro() -> None:
    gold = [{"a"}, {"a", "b"}, {"c"}]
    pred = [{"a"}, {"a"}, {"b"}]
    out = multilabel_f1(gold, pred, ["a", "b", "c"])
    micro = out["micro"]
    assert micro.precision == pytest.approx(2 / 3)  # type: ignore[attr-defined]
    assert micro.recall == pytest.approx(2 / 4)  # type: ignore[attr-defined]
    # per label F1: a = 1.0, b = 0.0, c = 0.0 -> macro over gold labels a, b, c
    assert out["macro_f1"] == pytest.approx(1 / 3)


def test_impact_metrics() -> None:
    out = impact_metrics(["low", "high", "medium"], ["low", "low", "high"])
    assert out["accuracy"] == pytest.approx(1 / 3)
    assert out["within_one"] == pytest.approx(2 / 3)
    assert out["confusion"]["high"]["low"] == 1  # type: ignore[index]


def test_best_threshold_separates_scores() -> None:
    t, acc = best_threshold([0.9, 0.85, 0.8], [0.7, 0.75])
    assert acc == 1.0 and 0.75 < t <= 0.8
    gate = gate_accuracy(t, [0.9, 0.85, 0.8], [0.7, 0.75])
    assert gate == {"accuracy": 1.0, "in_scope_answered": 1.0, "out_of_scope_refused": 1.0}
