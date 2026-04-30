from __future__ import annotations

from experiments.scripts.asreview_vs_a13b_comparison import (
    paired_wilcoxon_workload,
)


def test_paired_wilcoxon_labels_workload_direction() -> None:
    a13b_costs = [100, 120, 140, 160, 180, 200]
    asreview_costs = [20, 30, 40, 50, 60, 70]

    result = paired_wilcoxon_workload(a13b_costs, asreview_costs)

    assert result is not None
    assert result["a13b_greater_workload"]["alternative"] == "greater"
    assert result["a13b_less_workload"]["alternative"] == "less"
    assert result["two_sided"]["alternative"] == "two-sided"
    assert result["a13b_greater_workload"]["p_value"] < 0.05
    assert result["a13b_less_workload"]["p_value"] > 0.95


def test_paired_wilcoxon_requires_minimum_pairs() -> None:
    assert paired_wilcoxon_workload([1, 2, 3], [1, 1, 1]) is None
