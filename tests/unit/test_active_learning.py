"""Tests for active learning feedback collector."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.core.enums import Decision
from metascreener.core.models import HumanFeedback, ModelOutput
from metascreener.module1_screening.active_learning import FeedbackCollector


def _make_output(
    model_id: str,
    decision: Decision,
    score: float,
    confidence: float = 0.8,
) -> ModelOutput:
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=score,
        confidence=confidence,
        rationale="test",
    )


def _make_feedback(
    record_id: str,
    decision: Decision,
) -> HumanFeedback:
    return HumanFeedback(
        record_id=record_id,
        decision=decision,
        reviewer_id="tester",
    )


class TestFeedbackCollector:
    """Tests for FeedbackCollector."""

    def test_add_and_count(self) -> None:
        """Adding feedback increments count."""
        collector = FeedbackCollector()
        assert collector.n_feedback == 0

        outputs = [_make_output("m1", Decision.INCLUDE, 0.8)]
        fb = _make_feedback("r1", Decision.INCLUDE)
        collector.add_feedback(fb, outputs)

        assert collector.n_feedback == 1

    def test_multiple_feedback(self) -> None:
        """Multiple feedback entries tracked correctly."""
        collector = FeedbackCollector()
        for i in range(5):
            outputs = [_make_output("m1", Decision.INCLUDE, 0.7 + i * 0.05)]
            fb = _make_feedback(f"r{i}", Decision.INCLUDE)
            collector.add_feedback(fb, outputs)
        assert collector.n_feedback == 5

    def test_get_training_data_format(self) -> None:
        """Training data returns correct format."""
        collector = FeedbackCollector()
        outputs_inc = [
            _make_output("m1", Decision.INCLUDE, 0.8),
            _make_output("m2", Decision.INCLUDE, 0.7),
        ]
        outputs_exc = [
            _make_output("m1", Decision.EXCLUDE, 0.2),
            _make_output("m2", Decision.EXCLUDE, 0.3),
        ]

        collector.add_feedback(
            _make_feedback("r1", Decision.INCLUDE), outputs_inc
        )
        collector.add_feedback(
            _make_feedback("r2", Decision.EXCLUDE), outputs_exc
        )

        all_outputs, labels = collector.get_training_data()
        assert len(all_outputs) == 2
        assert len(labels) == 2
        assert labels[0] == 1  # INCLUDE → 1
        assert labels[1] == 0  # EXCLUDE → 0
        assert len(all_outputs[0]) == 2  # 2 models per record
        assert all_outputs[0][0].model_id == "m1"

    def test_get_training_data_empty(self) -> None:
        """Empty collector returns empty training data."""
        collector = FeedbackCollector()
        all_outputs, labels = collector.get_training_data()
        assert all_outputs == []
        assert labels == []

    def test_recalibrate_with_sufficient_data(self) -> None:
        """Recalibration produces CalibrationState for each model."""
        collector = FeedbackCollector()

        # Add enough diverse feedback for Platt fitting
        for i in range(10):
            score = 0.3 + i * 0.05
            decision = Decision.INCLUDE if i >= 5 else Decision.EXCLUDE
            outputs = [
                _make_output("m1", decision, score),
                _make_output("m2", decision, score + 0.1),
            ]
            fb = _make_feedback(f"r{i}", decision)
            collector.add_feedback(fb, outputs)

        states = collector.recalibrate(seed=42)
        assert "m1" in states
        assert "m2" in states
        assert states["m1"].method == "platt"
        assert states["m2"].method == "platt"
        assert states["m1"].n_samples == 10
        assert 0.0 <= states["m1"].phi <= 1.0

    def test_recalibrate_empty(self) -> None:
        """Empty collector returns empty calibration states."""
        collector = FeedbackCollector()
        states = collector.recalibrate()
        assert states == {}

    def test_recalibrate_single_class(self) -> None:
        """Single-class feedback returns identity calibration."""
        collector = FeedbackCollector()
        for i in range(5):
            outputs = [_make_output("m1", Decision.INCLUDE, 0.8)]
            fb = _make_feedback(f"r{i}", Decision.INCLUDE)
            collector.add_feedback(fb, outputs)

        states = collector.recalibrate()
        assert "m1" in states
        assert states["m1"].method == "identity"

    def test_relearn_weights(self) -> None:
        """Weight relearning returns weights for each model."""
        collector = FeedbackCollector()

        for i in range(10):
            decision = Decision.INCLUDE if i >= 5 else Decision.EXCLUDE
            outputs = [
                _make_output("m1", decision, 0.9 if decision == Decision.INCLUDE else 0.1),
                _make_output("m2", decision, 0.7 if decision == Decision.INCLUDE else 0.3),
            ]
            fb = _make_feedback(f"r{i}", decision)
            collector.add_feedback(fb, outputs)

        weights = collector.relearn_weights(seed=42)
        assert "m1" in weights
        assert "m2" in weights
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_relearn_weights_insufficient_data(self) -> None:
        """Weight relearning with <2 samples returns empty."""
        collector = FeedbackCollector()
        outputs = [_make_output("m1", Decision.INCLUDE, 0.8)]
        collector.add_feedback(_make_feedback("r1", Decision.INCLUDE), outputs)

        weights = collector.relearn_weights()
        assert weights == {}

    def test_relearn_weights_single_class(self) -> None:
        """Weight relearning with single class returns empty."""
        collector = FeedbackCollector()
        for i in range(5):
            outputs = [_make_output("m1", Decision.INCLUDE, 0.8)]
            collector.add_feedback(
                _make_feedback(f"r{i}", Decision.INCLUDE), outputs
            )

        weights = collector.relearn_weights()
        assert weights == {}

    def test_persistence_save_load(self, tmp_path: Path) -> None:
        """Feedback persists across collector instances."""
        storage = tmp_path / "feedback.json"

        collector1 = FeedbackCollector(storage_path=storage)
        outputs = [
            _make_output("m1", Decision.INCLUDE, 0.8),
            _make_output("m2", Decision.INCLUDE, 0.7),
        ]
        collector1.add_feedback(
            _make_feedback("r1", Decision.INCLUDE), outputs
        )
        collector1.add_feedback(
            _make_feedback("r2", Decision.EXCLUDE),
            [_make_output("m1", Decision.EXCLUDE, 0.2)],
        )
        assert collector1.n_feedback == 2

        # Load in new instance
        collector2 = FeedbackCollector(storage_path=storage)
        assert collector2.n_feedback == 2

        # Training data round-trips correctly
        all_outputs, labels = collector2.get_training_data()
        assert len(all_outputs) == 2
        assert labels == [1, 0]

    def test_persistence_nonexistent_path(self, tmp_path: Path) -> None:
        """Non-existent storage path creates file on first save."""
        storage = tmp_path / "subdir" / "feedback.json"
        collector = FeedbackCollector(storage_path=storage)
        outputs = [_make_output("m1", Decision.INCLUDE, 0.8)]
        collector.add_feedback(_make_feedback("r1", Decision.INCLUDE), outputs)

        assert storage.exists()

    def test_persistence_corrupted_file(self, tmp_path: Path) -> None:
        """Corrupted JSON file handled gracefully."""
        storage = tmp_path / "feedback.json"
        storage.write_text("not valid json{{{")

        collector = FeedbackCollector(storage_path=storage)
        assert collector.n_feedback == 0

    def test_in_memory_only(self) -> None:
        """No storage_path means in-memory only."""
        collector = FeedbackCollector()
        outputs = [_make_output("m1", Decision.INCLUDE, 0.8)]
        collector.add_feedback(_make_feedback("r1", Decision.INCLUDE), outputs)
        assert collector.n_feedback == 1
