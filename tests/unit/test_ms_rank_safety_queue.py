from __future__ import annotations

from pathlib import Path

from experiments.scripts.ms_rank_safety_queue import (
    A13B_CONFIG,
    available_a13b_datasets,
    compute_workload_at_recall,
    external_headline_decision,
    partition_a13b_results,
    select_v3_ranker,
)


def test_verified_work_counts_auto_includes_before_queue_review() -> None:
    result = compute_workload_at_recall(
        auto_include_count=5,
        auto_include_tp=4,
        n_includes=4,
        target_recall=0.985,
        ranked_queue_ids=["q1", "q2"],
        true_include_ids={"q1", "q2"},
    )

    assert result.reachable is True
    assert result.queue_prefix == 0
    assert result.queue_only_work == 0
    assert result.verified_work == 5


def test_workload_walks_ranked_safety_queue_until_target_is_reached() -> None:
    result = compute_workload_at_recall(
        auto_include_count=3,
        auto_include_tp=1,
        n_includes=4,
        target_recall=0.985,
        ranked_queue_ids=["n1", "tp2", "n2", "tp3", "tp4"],
        true_include_ids={"tp2", "tp3", "tp4"},
    )

    assert result.reachable is True
    assert result.queue_prefix == 5
    assert result.queue_only_work == 5
    assert result.verified_work == 8


def test_unreachable_when_queue_exhausted_before_target() -> None:
    result = compute_workload_at_recall(
        auto_include_count=2,
        auto_include_tp=0,
        n_includes=3,
        target_recall=0.985,
        ranked_queue_ids=["n1", "tp1"],
        true_include_ids={"tp1"},
    )

    assert result.reachable is False
    assert result.queue_prefix is None
    assert result.queue_only_work is None
    assert result.verified_work is None


def test_partition_puts_human_review_and_exclude_in_safety_queue() -> None:
    partition = partition_a13b_results([
        {"record_id": "auto-inc-tp", "decision": "INCLUDE", "true_label": 1},
        {"record_id": "auto-inc-fp", "decision": "INCLUDE", "true_label": 0},
        {"record_id": "hr-tp", "decision": "HUMAN_REVIEW", "true_label": 1},
        {"record_id": "exc-fn", "decision": "EXCLUDE", "true_label": 1},
    ])

    assert partition.auto_include_ids == {"auto-inc-tp", "auto-inc-fp"}
    assert partition.safety_queue_ids == {"hr-tp", "exc-fn"}
    assert partition.true_include_ids == {"auto-inc-tp", "hr-tp", "exc-fn"}
    assert partition.auto_include_tp == 1
    assert partition.auto_include_count == 2


def test_select_v3_ranker_prefers_fusion_within_two_percent() -> None:
    selected = select_v3_ranker({
        "lexical": 100.0,
        "llm": 110.0,
        "fusion": 101.0,
    })

    assert selected.rank_name == "fusion"
    assert selected.reason == "fusion_within_2pct"


def test_select_v3_ranker_falls_back_when_fusion_more_than_five_percent_worse() -> None:
    selected = select_v3_ranker({
        "lexical": 100.0,
        "llm": 120.0,
        "fusion": 106.0,
    })

    assert selected.rank_name == "lexical"
    assert selected.reason == "fusion_more_than_5pct_worse"


def test_available_datasets_require_a13b_json_suffix(tmp_path: Path) -> None:
    (tmp_path / "ready").mkdir()
    (tmp_path / "ready" / f"{A13B_CONFIG}.json").write_text("{}\n")
    (tmp_path / "missing_suffix").mkdir()
    (tmp_path / "missing_suffix" / A13B_CONFIG).write_text("{}\n")

    assert available_a13b_datasets(
        ["ready", "missing_suffix", "absent"],
        results_dir=tmp_path,
    ) == ["ready"]


def test_external_headline_decision_requires_all_preregistered_gates() -> None:
    rows = [
        {
            "selected_reachable_0985": True,
            "selected_verified_work_0985": 10,
            "asreview_elas_u4_records_0985": 20,
        }
        for _ in range(30)
    ]
    rows.extend([
        {
            "selected_reachable_0985": False,
            "selected_verified_work_0985": None,
            "asreview_elas_u4_records_0985": 20,
        }
        for _ in range(3)
    ])

    decision = external_headline_decision(rows)

    assert decision["dominates_asreview"] is False
    assert decision["reachable_count"] == 30
    assert decision["wins_count"] == 30
    assert decision["passes_reachability"] is False


def test_external_headline_decision_can_pass_when_all_gates_pass() -> None:
    rows = [
        {
            "selected_reachable_0985": True,
            "selected_verified_work_0985": 10,
            "asreview_elas_u4_records_0985": 20,
        }
        for _ in range(33)
    ]

    decision = external_headline_decision(rows)

    assert decision["dominates_asreview"] is True
    assert decision["reachable_count"] == 33
    assert decision["wins_count"] == 33
    assert decision["passes_pooled"] is True
