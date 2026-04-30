from __future__ import annotations

from experiments.scripts.ms_route_hybrid import (
    HybridRule,
    apply_hybrid_rule,
    find_best_threshold_rule,
)


def test_hybrid_rule_uses_v4_when_greater_than_threshold() -> None:
    rule = HybridRule(feature="auto_exclude_count", op=">", threshold=40.0)

    assert rule.use_v4({"auto_exclude_count": 41.0}) is True
    assert rule.use_v4({"auto_exclude_count": 40.0}) is False


def test_apply_hybrid_rule_returns_matching_work() -> None:
    rule = HybridRule(feature="auto_rate", op=">", threshold=0.1)
    row = {"auto_rate": 0.2, "v3_work": 100.0, "v4_work": 80.0}

    assert apply_hybrid_rule(row, rule) == 80.0


def test_find_best_threshold_rule_uses_only_training_rows() -> None:
    train_rows = [
        {"auto_exclude_count": 10.0, "v3_work": 10.0, "v4_work": 100.0},
        {"auto_exclude_count": 50.0, "v3_work": 100.0, "v4_work": 10.0},
        {"auto_exclude_count": 60.0, "v3_work": 100.0, "v4_work": 10.0},
    ]

    rule = find_best_threshold_rule(train_rows, ["auto_exclude_count"])

    assert rule.feature == "auto_exclude_count"
    assert rule.op == ">"
    assert rule.threshold == 30.0
