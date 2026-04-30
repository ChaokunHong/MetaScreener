"""Unit tests for the Layer 3.5 regime-aware meta-calibrator."""

from __future__ import annotations

import math

import pytest

from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import (
    ECSResult,
    ElementConsensus,
    ModelOutput,
    PICOAssessment,
    RuleCheckResult,
    ScreeningDecision,
)
from metascreener.module1_screening.layer3.meta_calibrator import MetaCalibrator


def _make_model_output(model_id: str, decision: Decision, match: bool) -> ModelOutput:
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=0.8 if decision == Decision.INCLUDE else 0.2,
        confidence=0.9,
        rationale="mock",
        element_assessment={
            "population": PICOAssessment(match=match, evidence="ev"),
        },
        parse_quality=1.0,
    )


def _make_decision(
    *,
    p_include: float,
    models_called: int,
    sprt_early_stop: bool,
    decisions: list[Decision],
    population_match: bool,
) -> ScreeningDecision:
    model_outputs = [
        _make_model_output(f"m-{idx}", decision, population_match)
        for idx, decision in enumerate(decisions)
    ]
    element_consensus = {
        "population": ElementConsensus(
            name="Population",
            required=True,
            exclusion_relevant=True,
            n_match=models_called if population_match else 0,
            n_mismatch=0 if population_match else models_called,
            n_unclear=0,
            support_ratio=1.0 if population_match else 0.0,
        )
    }
    ecs_result = ECSResult(
        score=0.9 if population_match else 0.1,
        eas_score=1.0,
        element_scores={"population": 1.0 if population_match else 0.0},
    )
    return ScreeningDecision(
        record_id="r1",
        stage=ScreeningStage.TITLE_ABSTRACT,
        decision=Decision.INCLUDE,
        tier=Tier.ONE,
        final_score=p_include,
        ensemble_confidence=0.9,
        model_outputs=model_outputs,
        rule_result=RuleCheckResult(),
        element_consensus=element_consensus,
        ecs_result=ecs_result,
        p_include=p_include,
        q_include=p_include,
        esas_score=0.4,
        glad_difficulty=0.8,
        sprt_early_stop=sprt_early_stop,
        models_called=models_called,
    )


def _features(
    *,
    p_include: float,
    models_called: float,
    sprt_early_stop: float,
    ecs_final: float,
    eas_score: float,
    esas_score: float,
    glad_difficulty: float,
    vote_entropy: float,
    n_hard_rules_triggered: float,
    max_element_mismatch: float,
) -> dict[str, float]:
    p_clip = min(max(p_include, 1e-6), 1 - 1e-6)
    return {
        "p_include": p_include,
        "logit_p_include": math.log(p_clip / (1.0 - p_clip)),
        "models_called": models_called,
        "sprt_early_stop": sprt_early_stop,
        "ecs_final": ecs_final,
        "eas_score": eas_score,
        "esas_score": esas_score,
        "glad_difficulty": glad_difficulty,
        "vote_entropy": vote_entropy,
        "n_hard_rules_triggered": n_hard_rules_triggered,
        "max_element_mismatch": max_element_mismatch,
    }


def test_extract_features_from_screening_decision() -> None:
    calibrator = MetaCalibrator()
    decision = _make_decision(
        p_include=0.2,
        models_called=2,
        sprt_early_stop=True,
        decisions=[Decision.INCLUDE, Decision.EXCLUDE],
        population_match=False,
    )

    features = calibrator.extract_features(decision)

    assert features["p_include"] == pytest.approx(0.2)
    assert features["models_called"] == pytest.approx(2.0)
    assert features["sprt_early_stop"] == pytest.approx(1.0)
    assert features["ecs_final"] == pytest.approx(0.1)
    assert features["eas_score"] == pytest.approx(1.0)
    assert features["esas_score"] == pytest.approx(0.4)
    assert features["glad_difficulty"] == pytest.approx(0.8)
    assert features["vote_entropy"] == pytest.approx(1.0)
    assert features["max_element_mismatch"] == pytest.approx(1.0)


def test_predict_falls_back_to_raw_p_include_when_unfitted() -> None:
    calibrator = MetaCalibrator()
    features = _features(
        p_include=0.37,
        models_called=2.0,
        sprt_early_stop=1.0,
        ecs_final=0.2,
        eas_score=1.0,
        esas_score=0.1,
        glad_difficulty=1.0,
        vote_entropy=0.5,
        n_hard_rules_triggered=0.0,
        max_element_mismatch=0.6,
    )

    assert calibrator.predict(features, "2model") == pytest.approx(0.37)


def test_update_fits_both_regimes() -> None:
    calibrator = MetaCalibrator(min_samples_to_fit=4, regularization_C=0.1)

    labelled_records = [
        {
            "true_label": 0,
            "ipw_weight": 1.0,
            "meta_regime": "2model",
            "meta_features": _features(
                p_include=0.90,
                models_called=2.0,
                sprt_early_stop=1.0,
                ecs_final=0.95,
                eas_score=1.0,
                esas_score=0.6,
                glad_difficulty=0.9,
                vote_entropy=0.0,
                n_hard_rules_triggered=0.0,
                max_element_mismatch=0.0,
            ),
        },
        {
            "true_label": 0,
            "ipw_weight": 1.0,
            "meta_regime": "2model",
            "meta_features": _features(
                p_include=0.82,
                models_called=2.0,
                sprt_early_stop=1.0,
                ecs_final=0.88,
                eas_score=1.0,
                esas_score=0.4,
                glad_difficulty=0.8,
                vote_entropy=0.0,
                n_hard_rules_triggered=0.0,
                max_element_mismatch=0.1,
            ),
        },
        {
            "true_label": 1,
            "ipw_weight": 1.0,
            "meta_regime": "2model",
            "meta_features": _features(
                p_include=0.04,
                models_called=2.0,
                sprt_early_stop=1.0,
                ecs_final=0.08,
                eas_score=1.0,
                esas_score=0.1,
                glad_difficulty=1.0,
                vote_entropy=0.0,
                n_hard_rules_triggered=0.0,
                max_element_mismatch=0.9,
            ),
        },
        {
            "true_label": 1,
            "ipw_weight": 1.0,
            "meta_regime": "2model",
            "meta_features": _features(
                p_include=0.10,
                models_called=2.0,
                sprt_early_stop=1.0,
                ecs_final=0.12,
                eas_score=1.0,
                esas_score=0.2,
                glad_difficulty=1.0,
                vote_entropy=0.0,
                n_hard_rules_triggered=0.0,
                max_element_mismatch=0.8,
            ),
        },
        {
            "true_label": 0,
            "ipw_weight": 1.0,
            "meta_regime": "4model",
            "meta_features": _features(
                p_include=0.95,
                models_called=4.0,
                sprt_early_stop=0.0,
                ecs_final=0.96,
                eas_score=0.95,
                esas_score=0.7,
                glad_difficulty=0.85,
                vote_entropy=0.0,
                n_hard_rules_triggered=0.0,
                max_element_mismatch=0.0,
            ),
        },
        {
            "true_label": 0,
            "ipw_weight": 1.0,
            "meta_regime": "4model",
            "meta_features": _features(
                p_include=0.75,
                models_called=4.0,
                sprt_early_stop=0.0,
                ecs_final=0.85,
                eas_score=0.9,
                esas_score=0.5,
                glad_difficulty=0.8,
                vote_entropy=0.3,
                n_hard_rules_triggered=0.0,
                max_element_mismatch=0.1,
            ),
        },
        {
            "true_label": 1,
            "ipw_weight": 1.0,
            "meta_regime": "4model",
            "meta_features": _features(
                p_include=0.02,
                models_called=4.0,
                sprt_early_stop=0.0,
                ecs_final=0.05,
                eas_score=0.9,
                esas_score=0.2,
                glad_difficulty=1.0,
                vote_entropy=0.0,
                n_hard_rules_triggered=0.0,
                max_element_mismatch=1.0,
            ),
        },
        {
            "true_label": 1,
            "ipw_weight": 1.0,
            "meta_regime": "4model",
            "meta_features": _features(
                p_include=0.18,
                models_called=4.0,
                sprt_early_stop=0.0,
                ecs_final=0.18,
                eas_score=0.8,
                esas_score=0.2,
                glad_difficulty=1.0,
                vote_entropy=0.8,
                n_hard_rules_triggered=0.0,
                max_element_mismatch=0.7,
            ),
        },
    ]

    calibrator.update(labelled_records)

    assert calibrator.is_fitted["2model"] is True
    assert calibrator.is_fitted["4model"] is True

    q_two_positive = calibrator.predict(labelled_records[0]["meta_features"], "2model")
    q_two_negative = calibrator.predict(labelled_records[2]["meta_features"], "2model")
    q_four_positive = calibrator.predict(labelled_records[4]["meta_features"], "4model")
    q_four_negative = calibrator.predict(labelled_records[6]["meta_features"], "4model")

    assert q_two_positive > q_two_negative
    assert q_four_positive > q_four_negative
