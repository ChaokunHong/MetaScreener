"""Unit tests for ReviewCriteria → BooleanQuery conversion."""
from __future__ import annotations


def test_build_from_pico_criteria():
    from metascreener.core.models import PICOCriteria
    from metascreener.module0_retrieval.query.builder import build_query

    criteria = PICOCriteria(
        research_question="Effect of metformin on diabetes",
        population_include=["adults", "type 2 diabetes"],
        intervention_include=["metformin"],
        outcome_primary=["HbA1c", "mortality"],
    )
    q = build_query(criteria)
    pop_texts = [t.text for t in q.population.terms]
    assert "adults" in pop_texts
    assert "type 2 diabetes" in pop_texts
    int_texts = [t.text for t in q.intervention.terms]
    assert "metformin" in int_texts


def test_build_from_review_criteria():
    from metascreener.core.enums import CriteriaFramework
    from metascreener.core.models import ReviewCriteria
    from metascreener.core.models_base import CriteriaElement
    from metascreener.module0_retrieval.query.builder import build_query

    criteria = ReviewCriteria(
        framework=CriteriaFramework.PICO,
        research_question="Effect of X on Y",
        elements={
            "population": CriteriaElement(name="Population", include=["elderly", "aged 65+"]),
            "intervention": CriteriaElement(name="Intervention", include=["exercise"]),
            "outcome": CriteriaElement(name="Outcome", include=["fall risk"]),
        },
        required_elements=["population", "intervention", "outcome"],
    )
    q = build_query(criteria)
    assert len(q.population.terms) == 2
    assert len(q.intervention.terms) == 1


def test_build_with_exclusions():
    from metascreener.core.enums import CriteriaFramework
    from metascreener.core.models import ReviewCriteria
    from metascreener.core.models_base import CriteriaElement
    from metascreener.module0_retrieval.query.builder import build_query

    criteria = ReviewCriteria(
        framework=CriteriaFramework.PICO,
        elements={
            "population": CriteriaElement(
                name="Population", include=["humans"], exclude=["animals", "in vitro"]
            )
        },
        required_elements=["population"],
        study_design_exclude=["editorial", "letter"],
    )
    q = build_query(criteria)
    excl_texts = [t.text for t in q.exclusions.terms]
    assert "animals" in excl_texts
    assert "editorial" in excl_texts


def test_build_empty_criteria():
    from metascreener.core.enums import CriteriaFramework
    from metascreener.core.models import ReviewCriteria
    from metascreener.module0_retrieval.query.builder import build_query

    criteria = ReviewCriteria(framework=CriteriaFramework.PICO, elements={}, required_elements=[])
    q = build_query(criteria)
    assert len(q.population.terms) == 0
