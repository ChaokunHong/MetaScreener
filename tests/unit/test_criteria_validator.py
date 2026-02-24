"""Tests for criteria validator (rule-based and LLM quality checks)."""
from __future__ import annotations

import pytest

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, QualityScore, ReviewCriteria
from metascreener.criteria.validator import CriteriaValidator
from metascreener.llm.adapters.mock import MockLLMAdapter


def _make_criteria(**kwargs: object) -> ReviewCriteria:
    """Helper to create ReviewCriteria with defaults."""
    defaults: dict[str, object] = {
        "framework": CriteriaFramework.PICO,
        "elements": {
            "population": CriteriaElement(name="Population", include=["adults"]),
            "intervention": CriteriaElement(name="Intervention", include=["drug X"]),
        },
        "required_elements": ["population", "intervention"],
        "study_design_include": ["RCT"],
    }
    defaults.update(kwargs)
    return ReviewCriteria(**defaults)


class TestRuleValidation:
    """Tests for rule-based validation (Layer 1, no LLM)."""

    def test_contradiction_date_range(self) -> None:
        """date_from > date_to should be detected as a contradiction."""
        criteria = _make_criteria(date_from="2020", date_to="2015")
        issues = CriteriaValidator.validate_rules(criteria)
        assert any("date" in i.message.lower() for i in issues)
        assert any(i.severity == "error" for i in issues)

    def test_overlap_include_exclude(self) -> None:
        """Same term in include and exclude should be detected."""
        criteria = _make_criteria(
            elements={
                "population": CriteriaElement(
                    name="Population",
                    include=["adults", "elderly"],
                    exclude=["adults"],  # overlaps with include
                ),
            },
        )
        issues = CriteriaValidator.validate_rules(criteria)
        assert any("overlap" in i.message.lower() for i in issues)

    def test_incomplete_required_element(self) -> None:
        """Required element with empty include list should be flagged."""
        criteria = _make_criteria(
            elements={
                "population": CriteriaElement(name="Population", include=[]),
                "intervention": CriteriaElement(
                    name="Intervention", include=["drug X"]
                ),
            },
            required_elements=["population", "intervention"],
        )
        issues = CriteriaValidator.validate_rules(criteria)
        assert any(
            "incomplete" in i.message.lower() or "empty" in i.message.lower()
            for i in issues
        )

    def test_too_broad_no_include(self) -> None:
        """No include terms in any element should be flagged as too broad."""
        criteria = _make_criteria(
            elements={
                "population": CriteriaElement(name="Population", include=[]),
                "intervention": CriteriaElement(name="Intervention", include=[]),
            },
        )
        issues = CriteriaValidator.validate_rules(criteria)
        assert any("broad" in i.message.lower() for i in issues)

    def test_valid_criteria_no_issues(self) -> None:
        """Well-formed criteria should produce no issues."""
        criteria = _make_criteria()
        issues = CriteriaValidator.validate_rules(criteria)
        assert len(issues) == 0


class TestLLMValidation:
    """Tests for LLM-based quality assessment (Layer 2)."""

    @pytest.mark.asyncio
    async def test_validate_quality_returns_score(self) -> None:
        """LLM quality assessment should return a valid QualityScore."""
        adapter = MockLLMAdapter(
            model_id="mock-quality",
            response_json={
                "total": 78,
                "completeness": 85,
                "precision": 60,
                "consistency": 90,
                "actionability": 75,
                "suggestions": ["Define age threshold"],
            },
        )
        criteria = _make_criteria()
        score = await CriteriaValidator.validate_quality(criteria, adapter)
        assert isinstance(score, QualityScore)
        assert score.total == 78
        assert score.completeness == 85
        assert len(score.suggestions) == 1


class TestFullValidation:
    """Tests for the combined validate() method."""

    @pytest.mark.asyncio
    async def test_validate_rules_only(self) -> None:
        """validate() without backend should only return rule issues."""
        criteria = _make_criteria(date_from="2020", date_to="2015")
        issues, quality = await CriteriaValidator.validate(criteria, backend=None)
        assert len(issues) > 0
        assert quality is None

    @pytest.mark.asyncio
    async def test_validate_with_backend(self) -> None:
        """validate() with backend should return both rules and quality."""
        adapter = MockLLMAdapter(
            model_id="mock-quality",
            response_json={
                "total": 80,
                "completeness": 80,
                "precision": 80,
                "consistency": 80,
                "actionability": 80,
                "suggestions": [],
            },
        )
        criteria = _make_criteria()
        issues, quality = await CriteriaValidator.validate(criteria, backend=adapter)
        assert len(issues) == 0
        assert quality is not None
        assert quality.total == 80
