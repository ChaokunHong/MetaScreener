from __future__ import annotations

from experiments.scripts.binary_frontier import (
    binary_metrics,
    threshold_decisions,
)


def test_binary_metrics_counts_include_as_positive() -> None:
    metrics = binary_metrics(
        true_labels=[1, 1, 0, 0],
        pred_include=[True, False, True, False],
    )

    assert metrics["tp"] == 1
    assert metrics["fn"] == 1
    assert metrics["fp"] == 1
    assert metrics["tn"] == 1
    assert metrics["sensitivity"] == 0.5
    assert metrics["specificity"] == 0.5
    assert metrics["auto_rate"] == 1.0


def test_threshold_decisions_include_when_score_reaches_threshold() -> None:
    assert threshold_decisions([0.1, 0.5, 0.9], threshold=0.5) == [
        False,
        True,
        True,
    ]
