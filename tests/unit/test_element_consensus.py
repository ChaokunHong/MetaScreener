"""Tests for element-level consensus aggregation."""
from __future__ import annotations

import pytest

from metascreener.core.enums import ConflictPattern, CriteriaFramework, Decision
from metascreener.core.models import (
    CriteriaElement,
    ElementConsensus,
    ModelOutput,
    PICOAssessment,
    ReviewCriteria,
)
from metascreener.module1_screening.layer3.element_consensus import (
    build_element_consensus,
    classify_conflict,
    compute_ecs,
)


def _make_output(
    model_id: str,
    decision: Decision,
    assessments: dict[str, bool | None],
) -> ModelOutput:
    """Create a ModelOutput helper with explicit element assessments."""
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=0.1 if decision == Decision.EXCLUDE else 0.9,
        confidence=0.9,
        rationale="test",
        element_assessment={
            key: PICOAssessment(match=value, evidence="evidence")
            for key, value in assessments.items()
        },
    )


def test_required_element_mismatch_and_other_match_are_both_recorded() -> None:
    """Consensus should keep both a matching and mismatching required element."""
    criteria = ReviewCriteria(
        framework=CriteriaFramework.PICO,
        elements={
            "population": CriteriaElement(name="Population", include=["adults"]),
            "intervention": CriteriaElement(name="Intervention", include=["drug x"]),
        },
        required_elements=["population", "intervention"],
    )
    outputs = [
        _make_output(
            "m1",
            Decision.EXCLUDE,
            {"population": True, "intervention": False},
        ),
        _make_output(
            "m2",
            Decision.EXCLUDE,
            {"population": True, "intervention": False},
        ),
        _make_output(
            "m3",
            Decision.EXCLUDE,
            {"population": True, "intervention": False},
        ),
        _make_output(
            "m4",
            Decision.EXCLUDE,
            {"population": True, "intervention": False},
        ),
    ]

    consensus = build_element_consensus(criteria, outputs)

    assert consensus["population"].decisive_match is True
    assert consensus["population"].exclusion_relevant is True
    assert consensus["intervention"].decisive_mismatch is True
    assert consensus["intervention"].exclusion_relevant is True


def test_study_design_constraints_create_exclusion_relevant_consensus() -> None:
    """Study design should participate in exclusion gating when configured."""
    criteria = ReviewCriteria(
        framework=CriteriaFramework.PICO,
        elements={
            "population": CriteriaElement(name="Population", include=["adults"]),
            "intervention": CriteriaElement(name="Intervention", include=["drug x"]),
        },
        required_elements=["population", "intervention"],
        study_design_include=["RCT"],
    )
    outputs = [
        _make_output(
            "m1",
            Decision.EXCLUDE,
            {
                "population": True,
                "intervention": True,
                "study_design": False,
            },
        ),
        _make_output(
            "m2",
            Decision.EXCLUDE,
            {
                "population": True,
                "intervention": True,
                "study_design": False,
            },
        ),
        _make_output(
            "m3",
            Decision.EXCLUDE,
            {
                "population": True,
                "intervention": True,
                "study_design": False,
            },
        ),
        _make_output(
            "m4",
            Decision.EXCLUDE,
            {
                "population": True,
                "intervention": True,
                "study_design": False,
            },
        ),
    ]

    consensus = build_element_consensus(criteria, outputs)

    assert "study_design" in consensus
    assert consensus["study_design"].exclusion_relevant is True
    assert consensus["study_design"].decisive_mismatch is True


def test_all_unclear_element_gets_none_support_ratio() -> None:
    """When all models return match=None, support_ratio should be None."""
    criteria = ReviewCriteria(
        framework=CriteriaFramework.PICO,
        elements={
            "population": CriteriaElement(name="Population", include=["adults"]),
            "outcome": CriteriaElement(name="Outcome", include=["mortality"]),
        },
        required_elements=["population", "outcome"],
    )
    outputs = [
        _make_output("m1", Decision.INCLUDE, {"population": True, "outcome": None}),
        _make_output("m2", Decision.INCLUDE, {"population": True, "outcome": None}),
        _make_output("m3", Decision.INCLUDE, {"population": True, "outcome": None}),
    ]
    consensus = build_element_consensus(criteria, outputs)
    assert consensus["population"].support_ratio == 1.0
    assert consensus["outcome"].support_ratio is None
    assert consensus["outcome"].n_unclear == 3
    assert consensus["outcome"].n_match == 0
    assert consensus["outcome"].n_mismatch == 0


# --- ECS computation tests ---


class TestComputeECS:
    """Tests for compute_ecs()."""

    def test_all_elements_agree(self) -> None:
        """All elements matching → ECS ≈ 1.0."""
        consensus = {
            "population": ElementConsensus(
                name="Population", support_ratio=1.0, n_match=4, n_mismatch=0
            ),
            "intervention": ElementConsensus(
                name="Intervention", support_ratio=1.0, n_match=4, n_mismatch=0
            ),
        }
        result = compute_ecs(consensus)
        assert result.score == pytest.approx(1.0)
        assert result.conflict_pattern == ConflictPattern.NONE
        assert result.weak_elements == []

    def test_population_disagreement(self) -> None:
        """Population mismatch → lower ECS + POPULATION_CONFLICT."""
        consensus = {
            "population": ElementConsensus(
                name="Population",
                support_ratio=0.25,
                n_match=1,
                n_mismatch=3,
                decisive_mismatch=True,
            ),
            "intervention": ElementConsensus(
                name="Intervention", support_ratio=1.0, n_match=4, n_mismatch=0
            ),
        }
        result = compute_ecs(consensus)
        assert result.score < 0.8
        assert result.conflict_pattern == ConflictPattern.POPULATION_CONFLICT
        assert "population" in result.weak_elements

    def test_multi_element_conflict(self) -> None:
        """Multiple elements with decisive_mismatch → MULTI_ELEMENT_CONFLICT."""
        consensus = {
            "population": ElementConsensus(
                name="Population",
                support_ratio=0.3,
                n_match=1,
                n_mismatch=3,
                decisive_mismatch=True,
            ),
            "outcome": ElementConsensus(
                name="Outcome",
                support_ratio=0.2,
                n_match=1,
                n_mismatch=3,
                decisive_mismatch=True,
            ),
        }
        result = compute_ecs(consensus)
        assert result.conflict_pattern == ConflictPattern.MULTI_ELEMENT_CONFLICT
        assert "population" in result.weak_elements
        assert "outcome" in result.weak_elements

    def test_custom_weights(self) -> None:
        """Custom element weights should affect the score."""
        consensus = {
            "population": ElementConsensus(
                name="Population", support_ratio=1.0, n_match=4, n_mismatch=0
            ),
            "outcome": ElementConsensus(
                name="Outcome", support_ratio=0.0, n_match=0, n_mismatch=4
            ),
        }
        # High weight on population → high ECS despite outcome mismatch
        result_pop_heavy = compute_ecs(
            consensus, element_weights={"population": 10.0, "outcome": 1.0}
        )
        # High weight on outcome → low ECS
        result_out_heavy = compute_ecs(
            consensus, element_weights={"population": 1.0, "outcome": 10.0}
        )
        assert result_pop_heavy.score > result_out_heavy.score

    def test_empty_consensus(self) -> None:
        """Empty consensus → ECS=0.0."""
        result = compute_ecs({})
        assert result.score == 0.0

    def test_element_scores_populated(self) -> None:
        """Element scores dict should contain per-element support ratios."""
        consensus = {
            "population": ElementConsensus(
                name="Population", support_ratio=0.8
            ),
            "intervention": ElementConsensus(
                name="Intervention", support_ratio=0.6
            ),
        }
        result = compute_ecs(consensus)
        assert result.element_scores["population"] == 0.8
        assert result.element_scores["intervention"] == 0.6


    def test_all_unclear_elements_excluded_from_ecs(self) -> None:
        """Elements with support_ratio=None (all unclear) are skipped in ECS."""
        consensus = {
            "population": ElementConsensus(
                name="Population", support_ratio=1.0, n_match=4, n_mismatch=0
            ),
            "intervention": ElementConsensus(
                name="Intervention", support_ratio=1.0, n_match=4, n_mismatch=0
            ),
            "outcome": ElementConsensus(
                name="Outcome",
                support_ratio=None,
                n_match=0,
                n_mismatch=0,
                n_unclear=4,
            ),
        }
        result = compute_ecs(consensus)
        # Outcome is skipped → ECS = (1.0*1.0 + 1.0*1.0) / (1.0 + 1.0) = 1.0
        assert result.score == pytest.approx(1.0)
        # Outcome should NOT appear in element_scores
        assert "outcome" not in result.element_scores
        assert "outcome" not in result.weak_elements

    def test_all_elements_unclear_returns_zero(self) -> None:
        """All elements unclear → ECS=0.0 (no assessable evidence)."""
        consensus = {
            "population": ElementConsensus(
                name="Population",
                support_ratio=None,
                n_match=0,
                n_mismatch=0,
                n_unclear=4,
            ),
            "intervention": ElementConsensus(
                name="Intervention",
                support_ratio=None,
                n_match=0,
                n_mismatch=0,
                n_unclear=4,
            ),
        }
        result = compute_ecs(consensus)
        assert result.score == 0.0
        assert result.element_scores == {}

    def test_unclear_does_not_dilute_matching_elements(self) -> None:
        """Unclear elements must not pull ECS below the gate threshold."""
        consensus = {
            "population": ElementConsensus(
                name="Population", support_ratio=1.0, n_match=4, n_mismatch=0
            ),
            "intervention": ElementConsensus(
                name="Intervention", support_ratio=1.0, n_match=4, n_mismatch=0
            ),
            "outcome": ElementConsensus(
                name="Outcome",
                support_ratio=None,
                n_match=0,
                n_mismatch=0,
                n_unclear=4,
            ),
            "comparison": ElementConsensus(
                name="Comparison",
                support_ratio=None,
                n_match=0,
                n_mismatch=0,
                n_unclear=4,
            ),
        }
        result = compute_ecs(consensus)
        # 2 matching + 2 unclear → ECS should be 1.0, not diluted
        assert result.score == pytest.approx(1.0)


class TestClassifyConflict:
    """Tests for classify_conflict()."""

    def test_no_conflict(self) -> None:
        consensus = {
            "population": ElementConsensus(
                name="Population", support_ratio=1.0, n_match=4, n_mismatch=0
            ),
        }
        assert classify_conflict(consensus) == ConflictPattern.NONE

    def test_intervention_conflict(self) -> None:
        consensus = {
            "intervention": ElementConsensus(
                name="Intervention",
                support_ratio=0.0,
                n_match=0,
                n_mismatch=4,
                decisive_mismatch=True,
            ),
        }
        assert classify_conflict(consensus) == ConflictPattern.INTERVENTION_CONFLICT

    def test_contradiction_with_low_support(self) -> None:
        """Contradiction + low support_ratio counts as conflict."""
        consensus = {
            "outcome": ElementConsensus(
                name="Outcome",
                support_ratio=0.3,
                n_match=1,
                n_mismatch=2,
                contradiction=True,
            ),
        }
        assert classify_conflict(consensus) == ConflictPattern.OUTCOME_CONFLICT

    def test_contradiction_with_high_support_no_conflict(self) -> None:
        """Contradiction + high support_ratio is NOT a conflict."""
        consensus = {
            "outcome": ElementConsensus(
                name="Outcome",
                support_ratio=0.75,
                n_match=3,
                n_mismatch=1,
                contradiction=True,
            ),
        }
        assert classify_conflict(consensus) == ConflictPattern.NONE
