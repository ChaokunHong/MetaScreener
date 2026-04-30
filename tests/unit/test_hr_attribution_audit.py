from __future__ import annotations

from experiments.scripts import hr_attribution_audit as audit


def _hr_row(
    *,
    true_label: int = 0,
    p_include: float = 0.001,
    ecs_final: float = 0.2,
    exclude_certainty_passes: bool = False,
    expected_loss: dict[str, float] | None = None,
) -> dict[str, object]:
    return {
        "scope": "all",
        "record_id": "r1",
        "true_label": true_label,
        "decision": "HUMAN_REVIEW",
        "p_include": p_include,
        "ecs_final": ecs_final,
        "exclude_certainty_passes": exclude_certainty_passes,
        "models_called": 2,
        "sprt_early_stop": True,
        "expected_loss": expected_loss
        or {"include": 0.999, "exclude": 0.05, "human_review": 5.0},
    }


def test_infer_attribution_identifies_loss_optimal_hr() -> None:
    row = _hr_row(
        expected_loss={"include": 6.0, "exclude": 7.0, "human_review": 5.0}
    )

    attr = audit.infer_attribution(row)

    assert attr.proposed_direction == "none_hr_loss_optimal"
    assert attr.primary_cause == "loss_hr_optimal"


def test_infer_attribution_marks_exclude_certainty_blocker() -> None:
    attr = audit.infer_attribution(_hr_row(exclude_certainty_passes=False))

    assert attr.proposed_direction == "EXCLUDE"
    assert attr.primary_cause == "exclude_blocked_by_exclude_certainty"
    assert attr.ec_failed is True


def test_infer_attribution_marks_include_low_ecs_blocker() -> None:
    row = _hr_row(
        ecs_final=0.2,
        expected_loss={"include": 0.1, "exclude": 10.0, "human_review": 5.0},
    )

    attr = audit.infer_attribution(row)

    assert attr.proposed_direction == "INCLUDE"
    assert attr.primary_cause == "include_blocked_by_low_ecs"
    assert attr.ecs_direction_conflict is True


def test_release_sweep_reports_extra_fn_and_auto_gain() -> None:
    rows = [
        {
            **_hr_row(true_label=0, exclude_certainty_passes=True),
            "proposed_direction": "EXCLUDE",
            "asreview_mean_rank_percentile": 0.9,
            "asreview_tail_missing_fraction": 0.0,
        },
        {
            **_hr_row(true_label=1, exclude_certainty_passes=True),
            "record_id": "r2",
            "proposed_direction": "EXCLUDE",
            "asreview_mean_rank_percentile": 0.9,
            "asreview_tail_missing_fraction": 0.0,
        },
    ]
    baseline = {
        "all": {
            "n": 2,
            "n_pos": 1,
            "baseline_fn": 0,
            "baseline_sensitivity": 1.0,
            "baseline_auto_rate": 0.0,
            "baseline_human_review_rate": 1.0,
        }
    }

    rules = audit.sweep_release_rules(rows, baseline)
    matching = [
        r
        for r in rules
        if r["scope"] == "all"
        and r["p_include_max"] == 0.002
        and r["ecs_max"] == 0.2
        and r["exclude_certainty_policy"] == "require_pass"
        and r["model_policy"] == "any"
        and r["asreview_rank_min"] == 0.8
    ]

    assert matching
    assert matching[0]["selected_hr"] == 2
    assert matching[0]["selected_true_includes_extra_fn"] == 1
    assert matching[0]["new_sensitivity"] == 0.0
