from __future__ import annotations

from experiments.scripts.ms_rank_rank_all import (
    compute_rank_all_workload_at_recall,
    select_v4_ranker,
)


def test_rank_all_workload_reviews_until_target_recall() -> None:
    result = compute_rank_all_workload_at_recall(
        n_records=4,
        n_includes=2,
        target_recall=0.5,
        ranked_ids=["n1", "tp1", "n2", "tp2"],
        true_include_ids={"tp1", "tp2"},
    )

    assert result.reachable is True
    assert result.work == 2
    assert result.wss == 0.5


def test_rank_all_workload_requires_full_prefix_for_high_recall() -> None:
    result = compute_rank_all_workload_at_recall(
        n_records=4,
        n_includes=2,
        target_recall=0.985,
        ranked_ids=["n1", "tp1", "n2", "tp2"],
        true_include_ids={"tp1", "tp2"},
    )

    assert result.reachable is True
    assert result.work == 4
    assert result.wss == 0.0


def test_rank_all_workload_is_unreachable_when_positive_missing_from_ranking() -> None:
    result = compute_rank_all_workload_at_recall(
        n_records=4,
        n_includes=2,
        target_recall=0.985,
        ranked_ids=["n1", "tp1", "n2"],
        true_include_ids={"tp1", "tp2"},
    )

    assert result.reachable is False
    assert result.work is None
    assert result.wss is None


def test_select_v4_ranker_prefers_fusion_within_two_percent() -> None:
    selected = select_v4_ranker({
        "lexical": 100.0,
        "llm": 105.0,
        "fusion": 101.0,
    })

    assert selected.rank_name == "fusion"
    assert selected.reason == "fusion_within_2pct"


def test_select_v4_ranker_falls_back_when_fusion_more_than_five_percent_worse() -> None:
    selected = select_v4_ranker({
        "lexical": 100.0,
        "llm": 110.0,
        "fusion": 106.0,
    })

    assert selected.rank_name == "lexical"
    assert selected.reason == "fusion_more_than_5pct_worse"
