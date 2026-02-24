"""Evaluation orchestrator — compute all metrics with bootstrap CIs.

Reuses Phase 3 calibrators (PlattCalibrator, IsotonicCalibrator,
ThresholdOptimizer) rather than reimplementing calibration.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import ModelOutput, ScreeningDecision
from metascreener.evaluation.metrics import (
    bootstrap_ci,
    compute_auroc,
    compute_calibration_metrics,
    compute_screening_metrics,
)
from metascreener.evaluation.models import (
    AUROCResult,
    BootstrapResult,
    EvaluationReport,
)
from metascreener.module1_screening.layer3.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
)
from metascreener.module1_screening.layer4.threshold_optimizer import (
    ThresholdOptimizer,
    Thresholds,
)

logger = structlog.get_logger(__name__)


class EvaluationRunner:
    """Orchestrate the full evaluation workflow.

    Computes screening metrics, AUROC, calibration metrics, and
    bootstrap CIs.  Delegates to Phase 3 calibrators for threshold
    optimization and score calibration.
    """

    def evaluate_screening(
        self,
        decisions: Sequence[ScreeningDecision],
        gold_labels: dict[str, Decision],
        seed: int = 42,
    ) -> EvaluationReport:
        """Compute all screening metrics with bootstrap CIs.

        Args:
            decisions: List of ScreeningDecision objects.
            gold_labels: Gold standard labels keyed by record_id.
            seed: Bootstrap seed for reproducibility.

        Returns:
            Complete EvaluationReport.
        """
        # Match decisions to labels by record_id
        matched_decisions: list[Decision] = []
        matched_labels: list[Decision] = []
        matched_scores: list[float] = []
        matched_int_labels: list[int] = []

        for dec in decisions:
            if dec.record_id in gold_labels:
                matched_decisions.append(dec.decision)
                matched_labels.append(gold_labels[dec.record_id])
                matched_scores.append(dec.final_score)
                matched_int_labels.append(
                    1 if gold_labels[dec.record_id] == Decision.INCLUDE else 0
                )

        # 1. Screening metrics
        metrics = compute_screening_metrics(matched_decisions, matched_labels)

        # 2. AUROC (only if both classes present)
        try:
            auroc = compute_auroc(matched_scores, matched_int_labels)
        except ValueError:
            auroc = AUROCResult(auroc=0.0, fpr=[0.0, 1.0], tpr=[0.0, 1.0])

        # 3. Calibration metrics
        calibration = compute_calibration_metrics(
            matched_scores, matched_int_labels, n_bins=10
        )

        # 4. Bootstrap CIs for key metrics
        bootstrap_cis = self._compute_bootstrap_cis(
            matched_decisions,
            matched_labels,
            seed=seed,
        )

        # 5. Metadata
        metadata: dict[str, Any] = {
            "n_records": len(matched_decisions),
            "seed": seed,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        logger.info(
            "evaluation_complete",
            n_records=len(matched_decisions),
            sensitivity=metrics.sensitivity,
            specificity=metrics.specificity,
        )

        return EvaluationReport(
            metrics=metrics,
            auroc=auroc,
            calibration=calibration,
            bootstrap_cis=bootstrap_cis,
            metadata=metadata,
        )

    def optimize_thresholds(
        self,
        decisions: Sequence[ScreeningDecision],
        gold_labels: dict[str, Decision],
        min_sensitivity: float = 0.95,
        seed: int = 42,
    ) -> Thresholds:
        """Optimize tau thresholds via Phase 3 ThresholdOptimizer.

        Args:
            decisions: List of ScreeningDecision objects.
            gold_labels: Gold standard labels keyed by record_id.
            min_sensitivity: Minimum sensitivity constraint.
            seed: Random seed.

        Returns:
            Optimized Thresholds.
        """
        validation_data: list[tuple[list[ModelOutput], float, float]] = []
        labels: list[int] = []

        for dec in decisions:
            if dec.record_id in gold_labels:
                validation_data.append(
                    (dec.model_outputs, dec.final_score, dec.ensemble_confidence)
                )
                labels.append(
                    1 if gold_labels[dec.record_id] == Decision.INCLUDE else 0
                )

        optimizer = ThresholdOptimizer()
        return optimizer.optimize(
            validation_data,
            labels,
            seed=seed,
            min_sensitivity=min_sensitivity,
        )

    def run_calibration(
        self,
        decisions: Sequence[ScreeningDecision],
        gold_labels: dict[str, Decision],
        method: str = "platt",
        seed: int = 42,
    ) -> dict[str, PlattCalibrator | IsotonicCalibrator]:
        """Fit calibrators per model using Phase 3 implementations.

        Args:
            decisions: List of ScreeningDecision objects.
            gold_labels: Gold standard labels keyed by record_id.
            method: Calibration method ("platt" or "isotonic").
            seed: Random seed.

        Returns:
            Dict mapping model_id to fitted calibrator.
        """
        # Collect per-model scores and labels
        model_data: dict[str, tuple[list[float], list[int]]] = {}
        for dec in decisions:
            if dec.record_id not in gold_labels:
                continue
            label = 1 if gold_labels[dec.record_id] == Decision.INCLUDE else 0
            for output in dec.model_outputs:
                if output.model_id not in model_data:
                    model_data[output.model_id] = ([], [])
                model_data[output.model_id][0].append(output.score)
                model_data[output.model_id][1].append(label)

        calibrators: dict[str, PlattCalibrator | IsotonicCalibrator] = {}
        for model_id, (scores, model_labels) in model_data.items():
            if len(set(model_labels)) < 2:
                logger.warning(
                    "calibration_single_class",
                    model_id=model_id,
                    n_samples=len(model_labels),
                )
                continue
            if method == "isotonic":
                cal: PlattCalibrator | IsotonicCalibrator = IsotonicCalibrator()
            else:
                cal = PlattCalibrator()
            cal.fit(scores, model_labels, seed=seed)
            calibrators[model_id] = cal

        logger.info(
            "calibration_complete",
            method=method,
            n_models=len(calibrators),
        )

        return calibrators

    def _compute_bootstrap_cis(
        self,
        decisions: list[Decision],
        labels: list[Decision],
        seed: int = 42,
    ) -> dict[str, BootstrapResult]:
        """Compute bootstrap CIs for sensitivity, specificity, precision, f1.

        Args:
            decisions: Predicted screening decisions.
            labels: Ground-truth screening labels.
            seed: Random seed for reproducibility.

        Returns:
            Dict mapping metric name to BootstrapResult.
        """
        cis: dict[str, BootstrapResult] = {}
        data = (decisions, labels)
        n_iter = 1000

        def _sensitivity_fn(sample: tuple[Any, ...]) -> float:
            decs, labs = sample
            m = compute_screening_metrics(list(decs), list(labs))
            return m.sensitivity

        def _specificity_fn(sample: tuple[Any, ...]) -> float:
            decs, labs = sample
            m = compute_screening_metrics(list(decs), list(labs))
            return m.specificity

        def _precision_fn(sample: tuple[Any, ...]) -> float:
            decs, labs = sample
            m = compute_screening_metrics(list(decs), list(labs))
            return m.precision

        def _f1_fn(sample: tuple[Any, ...]) -> float:
            decs, labs = sample
            m = compute_screening_metrics(list(decs), list(labs))
            return m.f1

        for name, fn in [
            ("sensitivity", _sensitivity_fn),
            ("specificity", _specificity_fn),
            ("precision", _precision_fn),
            ("f1", _f1_fn),
        ]:
            try:
                cis[name] = bootstrap_ci(fn, data, n_iter=n_iter, seed=seed)
            except Exception:  # noqa: BLE001
                logger.warning("bootstrap_failed", metric=name)

        return cis
