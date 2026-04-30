"""Tests for external result metrics-v2 migration."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from experiments.scripts.migrate_metrics_v2 import (
    discover_external_result_paths,
    migrate_payload,
)


def test_migrate_payload_recomputes_auto_rate_without_touching_results() -> None:
    payload = {
        "config": "a13b_coverage_rule",
        "dataset": "Cohen_Test",
        "n_records": 3,
        "n_valid": 3,
        "n_errors": 0,
        "metrics": {
            "n": 3,
            "sensitivity": 1.0,
            "specificity": 0.0,
            "auto_rate": 1.0,
            "tier_counts": {"1": 1, "3": 2},
        },
        "false_negatives": [],
        "errors": [],
        "results": [
            {
                "record_id": "r1",
                "true_label": 1,
                "decision": "HUMAN_REVIEW",
                "tier": 1,
                "models_called": 1,
                "sprt_early_stop": False,
                "ecs_final": 0.9,
                "p_include": 0.9,
                "final_score": 0.9,
            },
            {
                "record_id": "r2",
                "true_label": 0,
                "decision": "EXCLUDE",
                "tier": 3,
                "models_called": 3,
                "sprt_early_stop": False,
                "ecs_final": 0.1,
                "p_include": 0.1,
                "final_score": 0.1,
            },
            {
                "record_id": "r3",
                "true_label": 1,
                "decision": "INCLUDE",
                "tier": 3,
                "models_called": 3,
                "sprt_early_stop": False,
                "ecs_final": 0.8,
                "p_include": 0.8,
                "final_score": 0.8,
            },
        ],
    }
    original_results = copy.deepcopy(payload["results"])

    migrated, row = migrate_payload(payload, Path("experiments/results/Cohen_Test/a13b.json"))

    assert migrated["results"] == original_results
    assert migrated["metrics_schema_version"] == 2
    assert migrated["metrics"]["auto_rate"] == pytest.approx(2 / 3)
    assert migrated["metrics"]["decision_auto_rate"] == pytest.approx(2 / 3)
    assert migrated["metrics"]["tier_auto_rate"] == pytest.approx(1 / 3)
    assert migrated["metrics"]["legacy_tier_auto_rate"] == pytest.approx(1 / 3)
    assert migrated["metrics"]["auto_rate_definition"] == (
        "decision_auto_rate: decision in INCLUDE/EXCLUDE among valid results"
    )
    assert row["old_auto_rate"] == pytest.approx(1.0)
    assert row["new_decision_auto_rate"] == pytest.approx(2 / 3)
    assert row["delta_auto_rate"] == pytest.approx(-1 / 3)


def test_migrate_payload_is_idempotent_and_preserves_original_auto_rate() -> None:
    payload = {
        "config": "a13b_coverage_rule",
        "dataset": "Cohen_Test",
        "n_records": 1,
        "n_valid": 1,
        "n_errors": 0,
        "metrics": {"n": 1, "auto_rate": 1.0},
        "false_negatives": [],
        "errors": [],
        "results": [
            {
                "record_id": "r1",
                "true_label": 1,
                "decision": "HUMAN_REVIEW",
                "tier": 1,
                "models_called": 1,
                "sprt_early_stop": False,
                "ecs_final": 0.9,
                "p_include": 0.9,
                "final_score": 0.9,
            },
        ],
    }

    migrated_once, _ = migrate_payload(payload, Path("experiments/results/Cohen_Test/a13b.json"))
    migrated_once = json.loads(json.dumps(migrated_once))
    migrated_twice, row = migrate_payload(
        migrated_once,
        Path("experiments/results/Cohen_Test/a13b.json"),
    )

    assert migrated_twice == migrated_once
    assert row["old_auto_rate"] == pytest.approx(1.0)
    assert row["new_decision_auto_rate"] == pytest.approx(0.0)
    assert row["delta_auto_rate"] == pytest.approx(-1.0)


def test_migrate_payload_marks_sensitivity_na_when_no_positive_labels() -> None:
    payload = {
        "config": "a13b_coverage_rule",
        "dataset": "CLEF_NoLabels",
        "n_records": 2,
        "n_valid": 2,
        "n_errors": 0,
        "metrics": {"n": 2, "sensitivity": 0.0, "auto_rate": 1.0},
        "false_negatives": [],
        "errors": [],
        "results": [
            {
                "record_id": "r1",
                "true_label": 0,
                "decision": "EXCLUDE",
                "tier": 1,
                "models_called": 2,
                "sprt_early_stop": True,
                "ecs_final": 0.1,
                "p_include": 0.1,
                "final_score": 0.1,
            },
            {
                "record_id": "r2",
                "true_label": 0,
                "decision": "HUMAN_REVIEW",
                "tier": 3,
                "models_called": 2,
                "sprt_early_stop": True,
                "ecs_final": 0.6,
                "p_include": 0.6,
                "final_score": 0.6,
            },
        ],
    }

    migrated, row = migrate_payload(
        payload,
        Path("experiments/results/CLEF_NoLabels/a13b.json"),
    )

    assert migrated["metrics"]["tp"] == 0
    assert migrated["metrics"]["fn"] == 0
    assert migrated["metrics"]["sensitivity"] is None
    assert row["sensitivity"] is None


def test_discover_external_result_paths_filters_to_cohen_and_clef(tmp_path: Path) -> None:
    for rel in [
        "Cohen_Test/a1.json",
        "CLEF_CD000001/a1.json",
        "Muthu_2021/a1.json",
        "_failed/CLEF_CD000001/a1.json",
        "benchmark_summary.json",
    ]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"results": []}))

    found = [p.relative_to(tmp_path).as_posix() for p in discover_external_result_paths(tmp_path)]

    assert found == [
        "CLEF_CD000001/a1.json",
        "Cohen_Test/a1.json",
    ]
