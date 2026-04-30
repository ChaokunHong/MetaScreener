"""Tests for experiment-result metrics and integrity checks."""
from __future__ import annotations

import pytest
from experiments.scripts.run_ablation import (
    compute_quick_metrics,
    compute_ranking_wss95,
    validate_result_payload,
)


def test_auto_rate_uses_committed_decisions_not_tiers() -> None:
    """Auto-rate must mean records with a final INCLUDE/EXCLUDE decision."""
    results = [
        {
            "record_id": "r1",
            "true_label": 1,
            "decision": "HUMAN_REVIEW",
            "tier": 1,
            "models_called": 1,
        },
        {
            "record_id": "r2",
            "true_label": 0,
            "decision": "EXCLUDE",
            "tier": 3,
            "models_called": 3,
        },
        {
            "record_id": "r3",
            "true_label": 1,
            "decision": "INCLUDE",
            "tier": 3,
            "models_called": 3,
        },
    ]

    metrics = compute_quick_metrics(results)

    assert metrics["auto_rate"] == pytest.approx(2 / 3)
    assert metrics["decision_auto_rate"] == pytest.approx(2 / 3)
    assert metrics["tier_auto_rate"] == pytest.approx(1 / 3)
    assert metrics["human_review_rate"] == pytest.approx(1 / 3)
    assert metrics["decision_counts"] == {
        "INCLUDE": 1,
        "EXCLUDE": 1,
        "HUMAN_REVIEW": 1,
    }


def test_sensitivity_is_na_when_dataset_has_no_positive_labels() -> None:
    """Recall is undefined, not zero, when TP+FN is zero."""
    results = [
        {
            "record_id": "r1",
            "true_label": 0,
            "decision": "EXCLUDE",
            "tier": 1,
            "models_called": 2,
        },
        {
            "record_id": "r2",
            "true_label": 0,
            "decision": "HUMAN_REVIEW",
            "tier": 3,
            "models_called": 2,
        },
    ]

    metrics = compute_quick_metrics(results)

    assert metrics["tp"] == 0
    assert metrics["fn"] == 0
    assert metrics["sensitivity"] is None
    assert metrics["specificity"] == pytest.approx(1 / 2)


def test_compute_ranking_wss95_from_score_field() -> None:
    results = [
        {"record_id": "r1", "true_label": 1, "ecs_final": 0.90},
        {"record_id": "r2", "true_label": 0, "ecs_final": 0.80},
        {"record_id": "r3", "true_label": 1, "ecs_final": 0.70},
        {"record_id": "r4", "true_label": 0, "ecs_final": 0.10},
    ]

    assert compute_ranking_wss95(results, "ecs_final") == pytest.approx(0.20)


def test_validate_result_payload_catches_count_mismatch() -> None:
    payload = {
        "n_records": 3,
        "n_valid": 3,
        "n_errors": 0,
        "metrics": {"n": 2},
        "results": [
            {"decision": "INCLUDE", "models_called": 1},
            {"decision": "EXCLUDE", "models_called": 1},
            {"decision": "HUMAN_REVIEW", "models_called": 1},
        ],
        "errors": [],
    }

    issues = validate_result_payload(payload)

    assert any("metrics.n" in issue for issue in issues)


def test_validate_result_payload_accepts_consistent_payload() -> None:
    payload = {
        "n_records": 2,
        "n_valid": 1,
        "n_errors": 1,
        "metrics": {"n": 1},
        "results": [
            {"decision": "INCLUDE", "models_called": 1},
            {"decision": "ERROR", "models_called": 0},
        ],
        "errors": [{"record_id": "r2", "error": "temporary"}],
    }

    assert validate_result_payload(payload) == []
