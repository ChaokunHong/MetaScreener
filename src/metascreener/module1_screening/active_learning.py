"""Active learning feedback collector for HCN recalibration.

Collects human feedback on HUMAN_REVIEW decisions and delegates to
existing calibration and weight optimization components for model
recalibration. Uses JSON file storage for persistence.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import (
    CalibrationState,
    HumanFeedback,
    ModelOutput,
)
from metascreener.module1_screening.layer3.calibration import PlattCalibrator
from metascreener.module1_screening.layer3.weight_optimizer import (
    WeightOptimizer,
)

logger = structlog.get_logger(__name__)


class FeedbackCollector:
    """Collects human feedback on HUMAN_REVIEW decisions for recalibration.

    This is an interface/storage layer. The actual recalibration uses
    existing components:
    - PlattCalibrator.fit() for φ_i recalibration
    - WeightOptimizer.fit() for w_i relearning

    Args:
        storage_path: Path for JSON feedback persistence. If None,
            feedback is kept in memory only.
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._feedback: list[dict[str, Any]] = []

        if storage_path is not None and storage_path.exists():
            self._load()

    @property
    def n_feedback(self) -> int:
        """Number of feedback entries collected."""
        return len(self._feedback)

    def add_feedback(
        self,
        feedback: HumanFeedback,
        model_outputs: list[ModelOutput],
    ) -> None:
        """Record human feedback alongside the model outputs it corrects.

        Args:
            feedback: The human reviewer's decision and metadata.
            model_outputs: Model outputs for the same record, used as
                training signal for recalibration.
        """
        entry: dict[str, Any] = {
            "feedback": feedback.model_dump(mode="json"),
            "model_outputs": [
                {
                    "model_id": o.model_id,
                    "score": o.score,
                    "confidence": o.confidence,
                    "decision": o.decision.value,
                }
                for o in model_outputs
            ],
        }
        self._feedback.append(entry)

        logger.info(
            "feedback_added",
            record_id=feedback.record_id,
            decision=feedback.decision.value,
            n_models=len(model_outputs),
            total_feedback=len(self._feedback),
        )

        if self._storage_path is not None:
            self._save()

    def get_training_data(
        self,
    ) -> tuple[list[list[ModelOutput]], list[int]]:
        """Extract training data from collected feedback.

        Returns:
            Tuple of (model_outputs_per_record, labels) suitable for
            PlattCalibrator.fit() and WeightOptimizer.fit().
            Labels: 1 = INCLUDE, 0 = EXCLUDE.
        """
        all_outputs: list[list[ModelOutput]] = []
        labels: list[int] = []

        for entry in self._feedback:
            fb = entry["feedback"]
            decision_str = fb["decision"]
            label = 1 if decision_str == Decision.INCLUDE.value else 0
            labels.append(label)

            outputs = [
                ModelOutput(
                    model_id=o["model_id"],
                    decision=Decision(o["decision"]),
                    score=o["score"],
                    confidence=o["confidence"],
                    rationale="from_feedback",
                )
                for o in entry["model_outputs"]
            ]
            all_outputs.append(outputs)

        return all_outputs, labels

    def recalibrate(self, seed: int = 42) -> dict[str, CalibrationState]:
        """Recalibrate models using collected feedback via Platt scaling.

        Fits a separate PlattCalibrator per model using per-model scores
        and the human-provided labels.

        Args:
            seed: Random seed for reproducibility.

        Returns:
            Dictionary mapping model_id to updated CalibrationState.
        """
        all_outputs, labels = self.get_training_data()
        if not all_outputs:
            return {}

        # Group scores per model
        per_model_scores: dict[str, list[float]] = {}
        per_model_labels: dict[str, list[int]] = {}

        for outputs, label in zip(all_outputs, labels, strict=True):
            for output in outputs:
                mid = output.model_id
                if mid not in per_model_scores:
                    per_model_scores[mid] = []
                    per_model_labels[mid] = []
                per_model_scores[mid].append(output.score)
                per_model_labels[mid].append(label)

        # Fit Platt calibrator per model
        states: dict[str, CalibrationState] = {}
        now = datetime.now(UTC)

        for model_id in per_model_scores:
            scores = per_model_scores[model_id]
            model_labels = per_model_labels[model_id]

            # Need at least 2 samples with both classes for Platt scaling
            unique_labels = set(model_labels)
            if len(scores) < 2 or len(unique_labels) < 2:
                logger.warning(
                    "insufficient_data_for_calibration",
                    model_id=model_id,
                    n_samples=len(scores),
                    n_unique_labels=len(unique_labels),
                )
                states[model_id] = CalibrationState(
                    model_id=model_id,
                    phi=1.0,
                    method="identity",
                    n_samples=len(scores),
                    last_updated=now,
                )
                continue

            calibrator = PlattCalibrator()
            calibrator.fit(scores, model_labels, seed=seed)

            # Derive φ as the average calibrated probability across samples
            calibrated = [calibrator.calibrate(s) for s in scores]
            phi = sum(calibrated) / len(calibrated)
            phi = max(0.1, min(1.0, phi))

            states[model_id] = CalibrationState(
                model_id=model_id,
                phi=phi,
                method="platt",
                n_samples=len(scores),
                last_updated=now,
            )

        logger.info(
            "recalibration_complete",
            n_models=len(states),
            n_samples=len(labels),
        )

        return states

    def relearn_weights(self, seed: int = 42) -> dict[str, float]:
        """Relearn model weights using collected feedback.

        Delegates to WeightOptimizer.fit() which uses SLSQP to minimize
        binary cross-entropy between weighted model scores and labels.

        Args:
            seed: Random seed for reproducibility.

        Returns:
            Dictionary mapping model_id to optimized weight.
            Empty dict if insufficient data.
        """
        all_outputs, labels = self.get_training_data()
        if len(all_outputs) < 2:
            return {}

        unique_labels = set(labels)
        if len(unique_labels) < 2:
            return {}

        optimizer = WeightOptimizer()
        weights = optimizer.fit(all_outputs, labels, seed=seed)

        logger.info(
            "weight_relearning_complete",
            n_samples=len(labels),
            weights=weights,
        )

        return weights

    def _save(self) -> None:
        """Persist feedback to JSON file."""
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps(self._feedback, indent=2, default=str)
        )

    def _load(self) -> None:
        """Load feedback from JSON file."""
        if self._storage_path is None or not self._storage_path.exists():
            return
        try:
            self._feedback = json.loads(self._storage_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "feedback_load_failed",
                path=str(self._storage_path),
            )
            self._feedback = []
