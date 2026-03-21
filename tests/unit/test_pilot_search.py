"""Tests for PilotSearcher: MeSH-aware PubMed query builder."""
from __future__ import annotations

import pytest

from metascreener.api.schemas import MeSHValidationResult
from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, ReviewCriteria
from metascreener.criteria.pilot_search import PilotSearcher


def _make_criteria(
    population: list[str] | None = None,
    intervention: list[str] | None = None,
    population_exclude: list[str] | None = None,
) -> ReviewCriteria:
    """Helper: build a ReviewCriteria with given element terms."""
    elements: dict[str, CriteriaElement] = {}
    if population is not None:
        elements["population"] = CriteriaElement(
            name="Population",
            include=population,
            exclude=population_exclude or [],
        )
    if intervention is not None:
        elements["intervention"] = CriteriaElement(
            name="Intervention",
            include=intervention,
        )
    return ReviewCriteria(framework=CriteriaFramework.PICO, elements=elements)


# ---------------------------------------------------------------------------
# Test 1 — basic PICO query structure
# ---------------------------------------------------------------------------


def test_build_query_basic_pico() -> None:
    """Query must contain all terms, OR within each element, AND between them."""
    criteria = _make_criteria(
        population=["adults", "elderly patients"],
        intervention=["antibiotics"],
    )
    searcher = PilotSearcher()
    query = searcher.build_pubmed_query(criteria)

    # Both population terms appear
    assert "adults" in query
    assert "elderly patients" in query
    # Intervention term appears
    assert "antibiotics" in query
    # OR connects terms within same element
    assert "OR" in query
    # AND connects different elements
    assert "AND" in query


# ---------------------------------------------------------------------------
# Test 2 — empty elements are skipped
# ---------------------------------------------------------------------------


def test_build_query_skips_empty_elements() -> None:
    """Elements with no include terms must be omitted; no AND in a single-group query."""
    criteria = ReviewCriteria(
        framework=CriteriaFramework.PICO,
        elements={
            "population": CriteriaElement(
                name="Population",
                include=["adults"],
            ),
            "intervention": CriteriaElement(
                name="Intervention",
                include=[],  # empty — must be skipped
            ),
        },
    )
    searcher = PilotSearcher()
    query = searcher.build_pubmed_query(criteria)

    # Only one element group → no AND needed
    assert "AND" not in query
    assert "adults" in query


# ---------------------------------------------------------------------------
# Test 3 — MeSH-aware tagging
# ---------------------------------------------------------------------------


def test_build_query_mesh_aware() -> None:
    """Valid MeSH terms get [MeSH Terms] tag; non-MeSH terms are just quoted."""
    criteria = _make_criteria(
        population=["adults", "elderly patients"],
    )
    mesh_results = [
        MeSHValidationResult(term="adults", is_valid=True, mesh_uid="D000328"),
        MeSHValidationResult(term="elderly patients", is_valid=False),
    ]
    searcher = PilotSearcher()
    query = searcher.build_pubmed_query(criteria, mesh_results=mesh_results)

    assert '"adults"[MeSH Terms]' in query
    # Non-MeSH terms are unquoted to let PubMed ATM auto-expand
    assert "elderly patients" in query
    assert '"elderly patients"[MeSH Terms]' not in query
    assert '"elderly patients"' not in query  # no quotes


# ---------------------------------------------------------------------------
# Test 4 — exclude terms do NOT appear in the query
# ---------------------------------------------------------------------------


def test_build_query_excludes_not_in_query() -> None:
    """Exclude terms from a CriteriaElement must not appear in the built query."""
    criteria = _make_criteria(
        population=["adults"],
        population_exclude=["children", "neonates"],
    )
    searcher = PilotSearcher()
    query = searcher.build_pubmed_query(criteria)

    assert "children" not in query
    assert "neonates" not in query
    assert "adults" in query


# ---------------------------------------------------------------------------
# Test 5 — PubMed URL construction
# ---------------------------------------------------------------------------


def test_pubmed_url_construction() -> None:
    """_build_pubmed_url must return a valid PubMed URL containing the domain."""
    searcher = PilotSearcher()
    url = searcher._build_pubmed_url('("adults"[MeSH Terms]) AND ("antibiotics")')

    assert "pubmed.ncbi.nlm.nih.gov" in url
