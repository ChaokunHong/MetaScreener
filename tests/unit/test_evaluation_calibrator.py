"""Tests for EvaluationRunner orchestrator."""
from __future__ import annotations

from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import ModelOutput, ScreeningDecision
from metascreener.evaluation.calibrator import EvaluationRunner
from metascreener.evaluation.models import BootstrapResult, EvaluationReport
from metascreener.module1_screening.layer3.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
)
from metascreener.module1_screening.layer4.threshold_optimizer import Thresholds


def _make_model_output(
    model_id: str = "test-model",
    decision: Decision = Decision.INCLUDE,
    score: float = 0.9,
) -> ModelOutput:
    """Helper to create a ModelOutput."""
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=score,
        confidence=0.9,
        rationale="test rationale",
    )


def _make_decisions(
    pairs: list[tuple[Decision, float]],
    *,
    model_outputs: list[ModelOutput] | None = None,
) -> list[ScreeningDecision]:
    """Helper to create ScreeningDecision objects."""
    results = []
    for i, (dec, score) in enumerate(pairs):
        results.append(
            ScreeningDecision(
                record_id=f"r{i}",
                stage=ScreeningStage.TITLE_ABSTRACT,
                decision=dec,
                tier=Tier.ONE,
                final_score=score,
                ensemble_confidence=0.9,
                model_outputs=model_outputs or [],
            )
        )
    return results


class TestEvaluateScreening:
    """Tests for EvaluationRunner.evaluate_screening."""

    def test_returns_evaluation_report(self) -> None:
        """Perfect predictions produce perfect metrics."""
        decisions = _make_decisions([
            (Decision.INCLUDE, 0.9),
            (Decision.INCLUDE, 0.8),
            (Decision.EXCLUDE, 0.1),
            (Decision.EXCLUDE, 0.2),
        ])
        gold = {
            "r0": Decision.INCLUDE,
            "r1": Decision.INCLUDE,
            "r2": Decision.EXCLUDE,
            "r3": Decision.EXCLUDE,
        }
        runner = EvaluationRunner()
        report = runner.evaluate_screening(decisions, gold, seed=42)

        assert isinstance(report, EvaluationReport)
        assert report.metrics.sensitivity == 1.0
        assert report.metrics.specificity == 1.0

    def test_bootstrap_cis_populated(self) -> None:
        """Bootstrap CIs are computed for key screening metrics."""
        decisions = _make_decisions(
            [(Decision.INCLUDE, 0.9)] * 10
            + [(Decision.EXCLUDE, 0.1)] * 10,
        )
        gold = {f"r{i}": Decision.INCLUDE for i in range(10)}
        gold.update({f"r{i}": Decision.EXCLUDE for i in range(10, 20)})

        runner = EvaluationRunner()
        report = runner.evaluate_screening(decisions, gold, seed=42)

        assert "sensitivity" in report.bootstrap_cis
        assert "specificity" in report.bootstrap_cis
        assert "precision" in report.bootstrap_cis
        assert "f1" in report.bootstrap_cis
        for ci in report.bootstrap_cis.values():
            assert isinstance(ci, BootstrapResult)
            assert ci.ci_lower <= ci.point <= ci.ci_upper

    def test_metadata_has_timestamp_and_seed(self) -> None:
        """Report metadata includes seed, timestamp, and record count."""
        decisions = _make_decisions([
            (Decision.INCLUDE, 0.9),
            (Decision.EXCLUDE, 0.1),
        ])
        gold = {"r0": Decision.INCLUDE, "r1": Decision.EXCLUDE}

        report = EvaluationRunner().evaluate_screening(
            decisions, gold, seed=123,
        )

        assert report.metadata["seed"] == 123
        assert "timestamp" in report.metadata
        assert report.metadata["n_records"] == 2

    def test_evaluate_with_no_include(self) -> None:
        """All-exclude gold labels produce zero n_include."""
        decisions = _make_decisions([(Decision.EXCLUDE, 0.1)] * 4)
        gold = {f"r{i}": Decision.EXCLUDE for i in range(4)}

        report = EvaluationRunner().evaluate_screening(decisions, gold, seed=42)

        assert report.metrics.n_include == 0

    def test_seed_reproducibility(self) -> None:
        """Same seed produces identical bootstrap CIs."""
        decisions = _make_decisions(
            [(Decision.INCLUDE, 0.9)] * 10
            + [(Decision.EXCLUDE, 0.1)] * 10,
        )
        gold = {f"r{i}": Decision.INCLUDE for i in range(10)}
        gold.update({f"r{i}": Decision.EXCLUDE for i in range(10, 20)})

        r1 = EvaluationRunner().evaluate_screening(decisions, gold, seed=42)
        r2 = EvaluationRunner().evaluate_screening(decisions, gold, seed=42)

        for key in r1.bootstrap_cis:
            assert r1.bootstrap_cis[key].ci_lower == r2.bootstrap_cis[key].ci_lower
            assert r1.bootstrap_cis[key].ci_upper == r2.bootstrap_cis[key].ci_upper

    def test_unmatched_records_skipped(self) -> None:
        """Records without gold labels are excluded from evaluation."""
        decisions = _make_decisions([
            (Decision.INCLUDE, 0.9),
            (Decision.INCLUDE, 0.8),
            (Decision.EXCLUDE, 0.1),
        ])
        # Only provide gold labels for r0 and r2
        gold = {"r0": Decision.INCLUDE, "r2": Decision.EXCLUDE}

        report = EvaluationRunner().evaluate_screening(decisions, gold, seed=42)

        assert report.metadata["n_records"] == 2
        assert report.metrics.n_total == 2


class TestOptimizeThresholds:
    """Tests for EvaluationRunner.optimize_thresholds."""

    def test_returns_valid_thresholds(self) -> None:
        """Optimized thresholds maintain ordering tau_high > tau_mid > tau_low."""
        outputs = [
            _make_model_output("m1", Decision.INCLUDE, 0.9),
            _make_model_output("m2", Decision.INCLUDE, 0.85),
        ]
        decisions = _make_decisions(
            [(Decision.INCLUDE, 0.9)] * 20
            + [(Decision.EXCLUDE, 0.1)] * 20,
            model_outputs=outputs,
        )
        gold = {f"r{i}": Decision.INCLUDE for i in range(20)}
        gold.update({f"r{i}": Decision.EXCLUDE for i in range(20, 40)})

        runner = EvaluationRunner()
        thresholds = runner.optimize_thresholds(decisions, gold, seed=42)

        assert isinstance(thresholds, Thresholds)
        assert thresholds.tau_high > thresholds.tau_mid > thresholds.tau_low


class TestRunCalibration:
    """Tests for EvaluationRunner.run_calibration."""

    def test_platt_calibration(self) -> None:
        """Platt calibration returns fitted calibrators per model."""
        outputs_inc = [
            _make_model_output("model_a", Decision.INCLUDE, 0.9),
            _make_model_output("model_b", Decision.INCLUDE, 0.85),
        ]
        outputs_exc = [
            _make_model_output("model_a", Decision.EXCLUDE, 0.1),
            _make_model_output("model_b", Decision.EXCLUDE, 0.15),
        ]
        decisions = []
        for i in range(10):
            decisions.append(
                ScreeningDecision(
                    record_id=f"r{i}",
                    stage=ScreeningStage.TITLE_ABSTRACT,
                    decision=Decision.INCLUDE,
                    tier=Tier.ONE,
                    final_score=0.9,
                    ensemble_confidence=0.9,
                    model_outputs=outputs_inc,
                )
            )
        for i in range(10, 20):
            decisions.append(
                ScreeningDecision(
                    record_id=f"r{i}",
                    stage=ScreeningStage.TITLE_ABSTRACT,
                    decision=Decision.EXCLUDE,
                    tier=Tier.ONE,
                    final_score=0.1,
                    ensemble_confidence=0.9,
                    model_outputs=outputs_exc,
                )
            )

        gold = {f"r{i}": Decision.INCLUDE for i in range(10)}
        gold.update({f"r{i}": Decision.EXCLUDE for i in range(10, 20)})

        runner = EvaluationRunner()
        calibrators = runner.run_calibration(
            decisions, gold, method="platt", seed=42,
        )

        assert "model_a" in calibrators
        assert "model_b" in calibrators
        assert isinstance(calibrators["model_a"], PlattCalibrator)
        assert calibrators["model_a"].is_fitted

    def test_isotonic_calibration(self) -> None:
        """Isotonic calibration returns fitted IsotonicCalibrator instances."""
        outputs_inc = [_make_model_output("model_x", Decision.INCLUDE, 0.9)]
        outputs_exc = [_make_model_output("model_x", Decision.EXCLUDE, 0.1)]
        decisions = []
        for i in range(10):
            decisions.append(
                ScreeningDecision(
                    record_id=f"r{i}",
                    stage=ScreeningStage.TITLE_ABSTRACT,
                    decision=Decision.INCLUDE,
                    tier=Tier.ONE,
                    final_score=0.9,
                    ensemble_confidence=0.9,
                    model_outputs=outputs_inc,
                )
            )
        for i in range(10, 20):
            decisions.append(
                ScreeningDecision(
                    record_id=f"r{i}",
                    stage=ScreeningStage.TITLE_ABSTRACT,
                    decision=Decision.EXCLUDE,
                    tier=Tier.ONE,
                    final_score=0.1,
                    ensemble_confidence=0.9,
                    model_outputs=outputs_exc,
                )
            )
        gold = {f"r{i}": Decision.INCLUDE for i in range(10)}
        gold.update({f"r{i}": Decision.EXCLUDE for i in range(10, 20)})

        calibrators = EvaluationRunner().run_calibration(
            decisions, gold, method="isotonic", seed=42,
        )

        assert "model_x" in calibrators
        assert isinstance(calibrators["model_x"], IsotonicCalibrator)
        assert calibrators["model_x"].is_fitted

    def test_single_class_skipped(self) -> None:
        """Models with only one class in gold labels are skipped."""
        outputs = [_make_model_output("model_z", Decision.INCLUDE, 0.9)]
        decisions = _make_decisions(
            [(Decision.INCLUDE, 0.9)] * 5,
            model_outputs=outputs,
        )
        gold = {f"r{i}": Decision.INCLUDE for i in range(5)}

        calibrators = EvaluationRunner().run_calibration(
            decisions, gold, method="platt", seed=42,
        )

        assert len(calibrators) == 0
