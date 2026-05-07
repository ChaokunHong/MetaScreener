from __future__ import annotations

from pathlib import Path

from experiments.scripts.asreview_vs_a13b_comparison import (
    paired_wilcoxon_workload,
    write_markdown_report,
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


def test_markdown_report_discloses_wilcoxon_direction_and_prereg_threshold(
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "report.md"
    summary = {
        "headline_R": 0.985,
        "verdict": "asr_dominates",
        "n_datasets_compared": 31,
        "n_datasets_below_R": 2,
        "a13b_wins_count": 6,
        "a13b_wins_pct": 6 / 31,
        "pooled": {
            "a13b_hr_count": 42_962,
            "asr_nb_records": 24_880.4,
            "asr_u4_records": 17_333.4,
            "asr_best": 17_227.8,
            "delta": 25_734.2,
            "n_total": 55_818,
        },
        "wilcoxon_workload": {
            "a13b_greater_workload": {
                "p_value": 2.806633710861206e-05,
            },
            "two_sided": {
                "p_value": 5.613267421722412e-05,
            },
        },
    }

    write_markdown_report(out_path=out_path, summary=summary)

    text = out_path.read_text()
    assert "Headline interpretation uses `a13b_greater_workload` only" in text
    assert "No multiple-comparison correction is applied" in text
    assert "pre-registered in §4.3" in text
    assert "The dominance rules are asymmetric by design" in text
