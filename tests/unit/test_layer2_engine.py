"""Tests for the RuleEngine orchestrator (Layer 2)."""
from __future__ import annotations

from metascreener.core.enums import Decision, StudyType
from metascreener.core.models import (
    ModelOutput,
    PICOAssessment,
    PICOCriteria,
    Record,
    ReviewCriteria,
)
from metascreener.module1_screening.layer2.rule_engine import RuleEngine


def _make_output(
    decision: Decision = Decision.INCLUDE,
    pico_assessment: dict[str, PICOAssessment] | None = None,
) -> ModelOutput:
    return ModelOutput(
        model_id="test",
        decision=decision,
        score=0.9,
        confidence=0.9,
        rationale="test",
        pico_assessment=pico_assessment or {},
    )


def test_default_rules_loaded() -> None:
    """RuleEngine loads all 7 default rules (4 hard + 3 soft)."""
    engine = RuleEngine()
    assert len(engine.rules) == 7


def test_hard_violation_detected(
    sample_record_include: Record,
    amr_review_criteria: ReviewCriteria,
) -> None:
    """Editorial study type triggers a hard violation."""
    record = sample_record_include.model_copy(
        update={"study_type": StudyType.EDITORIAL}
    )
    engine = RuleEngine()
    result = engine.check(record, amr_review_criteria, [_make_output()])
    assert result.has_hard_violation


def test_no_violations_clean(
    sample_record_include: Record,
    amr_review_criteria: ReviewCriteria,
) -> None:
    """Clean record with matching outputs produces no violations."""
    outputs = [
        _make_output(
            pico_assessment={
                "population": PICOAssessment(match=True, evidence="ok"),
                "intervention": PICOAssessment(match=True, evidence="ok"),
                "outcome": PICOAssessment(match=True, evidence="ok"),
            }
        ),
    ]
    engine = RuleEngine()
    result = engine.check(sample_record_include, amr_review_criteria, outputs)
    assert not result.has_hard_violation
    assert result.total_penalty == 0.0


def test_soft_penalty_accumulated() -> None:
    """Population + outcome mismatch accumulates penalty > 0."""
    outputs = [
        _make_output(
            pico_assessment={
                "population": PICOAssessment(match=False, evidence="no"),
                "outcome": PICOAssessment(match=False, evidence="no"),
            }
        ),
    ]
    engine = RuleEngine()
    criteria = ReviewCriteria(framework="pico")
    record = Record(title="Test")
    result = engine.check(record, criteria, outputs)
    assert not result.has_hard_violation
    assert result.total_penalty > 0
    assert len(result.soft_violations) >= 1


def test_empty_rules_no_violations(
    sample_record_include: Record,
    amr_review_criteria: ReviewCriteria,
) -> None:
    """RuleEngine with empty rules produces no violations."""
    engine = RuleEngine(rules=[])
    result = engine.check(
        sample_record_include, amr_review_criteria, [_make_output()]
    )
    assert not result.has_hard_violation
    assert result.total_penalty == 0.0


def test_accepts_pico_criteria(
    sample_record_include: Record,
    amr_criteria: PICOCriteria,
) -> None:
    """RuleEngine auto-converts PICOCriteria to ReviewCriteria."""
    engine = RuleEngine()
    result = engine.check(
        sample_record_include, amr_criteria, [_make_output()]
    )
    assert not result.has_hard_violation


def test_check_accepts_optional_stage() -> None:
    """check() should accept an optional stage parameter."""
    from metascreener.core.models import Record, ReviewCriteria, RuleCheckResult
    from metascreener.core.enums import CriteriaFramework
    from metascreener.module1_screening.layer2.rule_engine import RuleEngine

    engine = RuleEngine()
    record = Record(title="Test record")
    criteria = ReviewCriteria(framework=CriteriaFramework.PICO)
    result = engine.check(record, criteria, [], stage="ta")
    assert isinstance(result, RuleCheckResult)
