"""Tests for disagreement classification."""
from __future__ import annotations

from metascreener.core.enums import ConflictPattern, Decision, DisagreementType
from metascreener.core.models import ECSResult, ModelOutput
from metascreener.module1_screening.layer3.disagreement import (
    classify_disagreement,
)


def _make_output(
    model_id: str,
    decision: Decision,
    score: float,
    confidence: float = 0.8,
    error: str | None = None,
) -> ModelOutput:
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=score,
        confidence=confidence,
        rationale="test",
        error=error,
    )


class TestClassifyDisagreement:
    """Tests for classify_disagreement()."""

    def test_unanimous_include(self) -> None:
        """All models agree INCLUDE → CONSENSUS."""
        outputs = [
            _make_output("a", Decision.INCLUDE, 0.8),
            _make_output("b", Decision.INCLUDE, 0.85),
            _make_output("c", Decision.INCLUDE, 0.82),
        ]
        result = classify_disagreement(outputs)
        assert result.disagreement_type == DisagreementType.CONSENSUS
        assert result.severity == 0.0

    def test_unanimous_exclude(self) -> None:
        """All models agree EXCLUDE → CONSENSUS."""
        outputs = [
            _make_output("a", Decision.EXCLUDE, 0.15),
            _make_output("b", Decision.EXCLUDE, 0.2),
            _make_output("c", Decision.EXCLUDE, 0.1),
        ]
        result = classify_disagreement(outputs)
        assert result.disagreement_type == DisagreementType.CONSENSUS
        assert result.severity == 0.0

    def test_decision_split_even(self) -> None:
        """2 INCLUDE + 2 EXCLUDE → DECISION_SPLIT with high severity."""
        outputs = [
            _make_output("a", Decision.INCLUDE, 0.7),
            _make_output("b", Decision.INCLUDE, 0.6),
            _make_output("c", Decision.EXCLUDE, 0.3),
            _make_output("d", Decision.EXCLUDE, 0.35),
        ]
        result = classify_disagreement(outputs)
        assert result.disagreement_type == DisagreementType.DECISION_SPLIT
        assert result.severity > 0.5  # even split → high severity

    def test_decision_split_uneven(self) -> None:
        """3 INCLUDE + 1 EXCLUDE → DECISION_SPLIT with lower severity."""
        outputs = [
            _make_output("a", Decision.INCLUDE, 0.8),
            _make_output("b", Decision.INCLUDE, 0.75),
            _make_output("c", Decision.INCLUDE, 0.7),
            _make_output("d", Decision.EXCLUDE, 0.3),
        ]
        result = classify_disagreement(outputs)
        assert result.disagreement_type == DisagreementType.DECISION_SPLIT
        assert result.severity < 0.8  # uneven split → moderate severity

    def test_score_divergence(self) -> None:
        """Same decision but large score spread → SCORE_DIVERGENCE."""
        outputs = [
            _make_output("a", Decision.INCLUDE, 0.9),
            _make_output("b", Decision.INCLUDE, 0.4),  # large spread
        ]
        result = classify_disagreement(outputs)
        assert result.disagreement_type == DisagreementType.SCORE_DIVERGENCE
        assert result.severity > 0.0

    def test_confidence_mismatch(self) -> None:
        """Same decision, similar scores, large confidence spread."""
        outputs = [
            _make_output("a", Decision.INCLUDE, 0.7, confidence=0.95),
            _make_output("b", Decision.INCLUDE, 0.72, confidence=0.3),
        ]
        result = classify_disagreement(outputs)
        assert result.disagreement_type == DisagreementType.CONFIDENCE_MISMATCH
        assert result.severity > 0.0

    def test_single_model_consensus(self) -> None:
        """Single model → always CONSENSUS."""
        outputs = [_make_output("a", Decision.INCLUDE, 0.8)]
        result = classify_disagreement(outputs)
        assert result.disagreement_type == DisagreementType.CONSENSUS
        assert result.severity == 0.0

    def test_empty_outputs(self) -> None:
        """Empty outputs → CONSENSUS."""
        result = classify_disagreement([])
        assert result.disagreement_type == DisagreementType.CONSENSUS

    def test_errored_outputs_excluded(self) -> None:
        """Errored outputs should not participate."""
        outputs = [
            _make_output("a", Decision.INCLUDE, 0.8),
            _make_output("b", Decision.EXCLUDE, 0.2, error="timeout"),
        ]
        result = classify_disagreement(outputs)
        # Only model "a" is valid → single model → CONSENSUS
        assert result.disagreement_type == DisagreementType.CONSENSUS

    def test_rationale_conflict_same_decision_with_ecs(self) -> None:
        """Same decision + ECS element conflict → RATIONALE_CONFLICT.

        Models agree on INCLUDE but disagree on which PICO elements match.
        This is the primary scenario for rationale conflict detection.
        """
        outputs = [
            _make_output("a", Decision.INCLUDE, 0.8),
            _make_output("b", Decision.INCLUDE, 0.75),
            _make_output("c", Decision.INCLUDE, 0.78),
        ]
        ecs = ECSResult(
            score=0.3,
            conflict_pattern=ConflictPattern.POPULATION_CONFLICT,
        )
        result = classify_disagreement(outputs, ecs_result=ecs)
        assert result.disagreement_type == DisagreementType.RATIONALE_CONFLICT
        assert result.severity > 0.0
        assert result.details["conflict_pattern"] == "population_conflict"

    def test_rationale_conflict_from_ecs_all_human_review(self) -> None:
        """ECS conflict with all HUMAN_REVIEW votes → RATIONALE_CONFLICT."""
        outputs = [
            _make_output("a", Decision.HUMAN_REVIEW, 0.5),
            _make_output("b", Decision.HUMAN_REVIEW, 0.5),
        ]
        ecs = ECSResult(
            score=0.3,
            conflict_pattern=ConflictPattern.POPULATION_CONFLICT,
        )
        result = classify_disagreement(outputs, ecs_result=ecs)
        assert result.disagreement_type == DisagreementType.RATIONALE_CONFLICT
        assert result.severity > 0.0

    def test_score_divergence_takes_priority_over_rationale_conflict(self) -> None:
        """Score spread > threshold wins over ECS conflict (checked first)."""
        outputs = [
            _make_output("a", Decision.INCLUDE, 0.9),
            _make_output("b", Decision.INCLUDE, 0.4),  # spread = 0.5 > 0.4
        ]
        ecs = ECSResult(
            score=0.3,
            conflict_pattern=ConflictPattern.POPULATION_CONFLICT,
        )
        result = classify_disagreement(outputs, ecs_result=ecs)
        assert result.disagreement_type == DisagreementType.SCORE_DIVERGENCE

    def test_all_human_review_no_ecs(self) -> None:
        """All HUMAN_REVIEW with no ECS → CONSENSUS by abstention."""
        outputs = [
            _make_output("a", Decision.HUMAN_REVIEW, 0.5),
            _make_output("b", Decision.HUMAN_REVIEW, 0.5),
        ]
        result = classify_disagreement(outputs)
        assert result.disagreement_type == DisagreementType.CONSENSUS

    def test_details_contain_diagnostics(self) -> None:
        """Result details should contain diagnostic information."""
        outputs = [
            _make_output("a", Decision.INCLUDE, 0.8, confidence=0.9),
            _make_output("b", Decision.EXCLUDE, 0.3, confidence=0.7),
        ]
        result = classify_disagreement(outputs)
        assert "n_valid" in result.details
        assert "score_spread" in result.details
        assert "confidence_spread" in result.details
