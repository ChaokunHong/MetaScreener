"""Tests for chunk heterogeneity metric."""
from __future__ import annotations

from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import ElementConsensus, ScreeningDecision
from metascreener.module1_screening.chunk_heterogeneity import (
    _count_conflicting_elements,
    _variance,
    compute_chunk_heterogeneity,
)


def _make_chunk_decision(
    decision: Decision = Decision.INCLUDE,
    score: float = 0.8,
    confidence: float = 0.9,
    element_consensus: dict[str, ElementConsensus] | None = None,
) -> ScreeningDecision:
    """Helper to create a chunk ScreeningDecision."""
    return ScreeningDecision(
        record_id="chunk_test",
        stage=ScreeningStage.FULL_TEXT,
        decision=decision,
        tier=Tier.ONE,
        final_score=score,
        ensemble_confidence=confidence,
        element_consensus=element_consensus or {},
    )


class TestComputeChunkHeterogeneity:
    """Tests for compute_chunk_heterogeneity()."""

    def test_single_chunk_returns_none(self) -> None:
        """Heterogeneity is undefined for a single chunk."""
        decisions = [_make_chunk_decision()]
        assert compute_chunk_heterogeneity(decisions) is None

    def test_empty_returns_none(self) -> None:
        """Heterogeneity is undefined for zero chunks."""
        assert compute_chunk_heterogeneity([]) is None

    def test_unanimous_low_heterogeneity(self) -> None:
        """All chunks agree with similar scores → low heterogeneity."""
        decisions = [
            _make_chunk_decision(Decision.INCLUDE, score=0.85, confidence=0.90),
            _make_chunk_decision(Decision.INCLUDE, score=0.80, confidence=0.88),
            _make_chunk_decision(Decision.INCLUDE, score=0.82, confidence=0.91),
        ]
        result = compute_chunk_heterogeneity(decisions)
        assert result is not None
        assert result.heterogeneity_level == "low"
        assert result.decision_agreement == 1.0
        assert result.heterogeneity_score < 0.30

    def test_split_high_heterogeneity(self) -> None:
        """Half INCLUDE, half EXCLUDE with divergent scores + element conflicts → high."""
        ec_match = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
            "intervention": ElementConsensus(
                name="Int", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
            "outcome": ElementConsensus(
                name="Out", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
        }
        ec_mismatch = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
            "intervention": ElementConsensus(
                name="Int", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
            "outcome": ElementConsensus(
                name="Out", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
        }
        decisions = [
            _make_chunk_decision(Decision.INCLUDE, score=0.95, confidence=0.95,
                                 element_consensus=ec_match),
            _make_chunk_decision(Decision.EXCLUDE, score=0.05, confidence=0.10,
                                 element_consensus=ec_mismatch),
            _make_chunk_decision(Decision.INCLUDE, score=0.90, confidence=0.90,
                                 element_consensus=ec_match),
            _make_chunk_decision(Decision.EXCLUDE, score=0.10, confidence=0.15,
                                 element_consensus=ec_mismatch),
        ]
        result = compute_chunk_heterogeneity(decisions)
        assert result is not None
        assert result.heterogeneity_level == "high"
        assert result.decision_agreement == 0.5
        assert result.heterogeneity_score >= 0.60

    def test_moderate_heterogeneity(self) -> None:
        """3/4 agreement with high score variance + element conflicts → moderate."""
        ec_match = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
            "intervention": ElementConsensus(
                name="Int", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
        }
        ec_mismatch = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
            "intervention": ElementConsensus(
                name="Int", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
        }
        decisions = [
            _make_chunk_decision(Decision.INCLUDE, score=0.95, confidence=0.95,
                                 element_consensus=ec_match),
            _make_chunk_decision(Decision.INCLUDE, score=0.85, confidence=0.85,
                                 element_consensus=ec_match),
            _make_chunk_decision(Decision.INCLUDE, score=0.15, confidence=0.20,
                                 element_consensus=ec_mismatch),
            _make_chunk_decision(Decision.EXCLUDE, score=0.05, confidence=0.10,
                                 element_consensus=ec_mismatch),
        ]
        result = compute_chunk_heterogeneity(decisions)
        assert result is not None
        assert result.decision_agreement == 0.75
        assert result.heterogeneity_level in ("moderate", "high")

    def test_decision_agreement_math(self) -> None:
        """Verify the decision_agreement fraction calculation."""
        decisions = [
            _make_chunk_decision(Decision.INCLUDE),
            _make_chunk_decision(Decision.INCLUDE),
            _make_chunk_decision(Decision.EXCLUDE),
        ]
        result = compute_chunk_heterogeneity(decisions)
        assert result is not None
        # 2/3 agree on INCLUDE
        assert abs(result.decision_agreement - 2.0 / 3.0) < 0.01

    def test_score_variance_math(self) -> None:
        """Verify variance formula with known values."""
        decisions = [
            _make_chunk_decision(score=0.0),
            _make_chunk_decision(score=1.0),
        ]
        result = compute_chunk_heterogeneity(decisions)
        assert result is not None
        # Var([0.0, 1.0]) = 0.25
        assert abs(result.score_variance - 0.25) < 0.001

    def test_conflicting_elements_detected(self) -> None:
        """Elements with match in one chunk and mismatch in another."""
        ec_match = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
        }
        ec_mismatch = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
        }
        decisions = [
            _make_chunk_decision(element_consensus=ec_match),
            _make_chunk_decision(element_consensus=ec_mismatch),
        ]
        result = compute_chunk_heterogeneity(decisions)
        assert result is not None
        assert result.conflicting_elements >= 1

    def test_composite_weights_sum_to_one(self) -> None:
        """Verify composite weights approximately sum to 1.0."""
        from metascreener.module1_screening.chunk_heterogeneity import (
            _W_AGREEMENT,
            _W_CONF_VAR,
            _W_CONFLICTS,
            _W_SCORE_VAR,
        )

        total = _W_AGREEMENT + _W_SCORE_VAR + _W_CONF_VAR + _W_CONFLICTS
        assert abs(total - 1.0) < 0.001


class TestVariance:
    """Tests for the _variance helper."""

    def test_variance_empty(self) -> None:
        assert _variance([]) == 0.0

    def test_variance_single(self) -> None:
        assert _variance([5.0]) == 0.0

    def test_variance_identical(self) -> None:
        assert _variance([3.0, 3.0, 3.0]) == 0.0

    def test_variance_known(self) -> None:
        # Var([1, 2, 3]) = ((1-2)^2 + (2-2)^2 + (3-2)^2) / 3 = 2/3
        v = _variance([1.0, 2.0, 3.0])
        assert abs(v - 2.0 / 3.0) < 0.001


class TestConflictingElements:
    """Tests for _count_conflicting_elements."""

    def test_no_consensus_data(self) -> None:
        decisions = [_make_chunk_decision(), _make_chunk_decision()]
        assert _count_conflicting_elements(decisions) == 0

    def test_all_matching(self) -> None:
        ec = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=3, n_mismatch=0, n_unclear=0,
            ),
        }
        decisions = [
            _make_chunk_decision(element_consensus=ec),
            _make_chunk_decision(element_consensus=ec),
        ]
        assert _count_conflicting_elements(decisions) == 0

    def test_conflicting(self) -> None:
        ec1 = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=2, n_mismatch=0, n_unclear=0,
            ),
        }
        ec2 = {
            "population": ElementConsensus(
                name="Pop", required=True, exclusion_relevant=True,
                n_match=0, n_mismatch=2, n_unclear=0,
            ),
        }
        decisions = [
            _make_chunk_decision(element_consensus=ec1),
            _make_chunk_decision(element_consensus=ec2),
        ]
        assert _count_conflicting_elements(decisions) == 1
