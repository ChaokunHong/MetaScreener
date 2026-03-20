"""Tests for DedupMerger with union-find and pairwise edge voting."""
from __future__ import annotations

import pytest

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, ReviewCriteria
from metascreener.criteria.dedup_merger import (
    DedupMerger,
    UnionFind,
    aggregate_dedup_edges,
    compute_dedup_quorum,
)
from metascreener.criteria.models import DedupResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_criteria(**element_kwargs: dict) -> ReviewCriteria:
    """Build a minimal ReviewCriteria with given elements."""
    elements = {}
    for key, kw in element_kwargs.items():
        kw.setdefault("name", key.capitalize())
        elements[key] = CriteriaElement(**kw)
    return ReviewCriteria(
        framework=CriteriaFramework.PICO,
        research_question="test question",
        elements=elements,
    )


def _make_round2_evals(
    *model_edges: tuple[str, list[dict]],
) -> dict[str, dict]:
    """Build round2_evals from (model_id, [edge_dict, ...]) tuples.

    Each edge_dict has keys: element, polarity, term_a, term_b,
    is_duplicate (bool), preferred (str).
    """
    evals: dict[str, dict] = {}
    for model_id, edges in model_edges:
        evals[model_id] = {"dedup_edges": edges}
    return evals


def _make_term_origin(
    mapping: dict[str, dict[str, dict[str, list[str]]]],
) -> dict[str, dict[str, dict[str, list[str]]]]:
    """Passthrough helper for readability."""
    return mapping


# ---------------------------------------------------------------------------
# TestUnionFind
# ---------------------------------------------------------------------------

class TestUnionFind:
    """Union-Find with path compression and union by rank."""

    def test_singleton(self) -> None:
        uf = UnionFind()
        assert uf.find("a") == "a"

    def test_union_same_component(self) -> None:
        uf = UnionFind()
        uf.union("a", "b")
        assert uf.find("a") == uf.find("b")

    def test_transitive_union(self) -> None:
        uf = UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")
        assert uf.find("a") == uf.find("c")

    def test_components(self) -> None:
        uf = UnionFind()
        uf.union("a", "b")
        uf.union("c", "d")
        comps = uf.components()
        assert len(comps) == 2
        assert {"a", "b"} in comps
        assert {"c", "d"} in comps

    def test_no_cross_component_merge(self) -> None:
        uf = UnionFind()
        uf.union("a", "b")
        uf.union("c", "d")
        assert uf.find("a") != uf.find("c")


# ---------------------------------------------------------------------------
# TestComputeDedupQuorum
# ---------------------------------------------------------------------------

class TestComputeDedupQuorum:
    """Quorum = max(2, ceil(n_models * fraction))."""

    def test_four_models_half(self) -> None:
        assert compute_dedup_quorum(4, 0.5) == 2

    def test_three_models_half(self) -> None:
        assert compute_dedup_quorum(3, 0.5) == 2

    def test_four_models_seventy_five(self) -> None:
        assert compute_dedup_quorum(4, 0.75) == 3

    def test_floor_min_two(self) -> None:
        assert compute_dedup_quorum(1, 0.5) == 2

    def test_large_pool(self) -> None:
        assert compute_dedup_quorum(10, 0.5) == 5


# ---------------------------------------------------------------------------
# TestAggregateEdges
# ---------------------------------------------------------------------------

class TestAggregateEdges:
    """Edge aggregation with canonical key ordering."""

    def test_basic_aggregation(self) -> None:
        evals = _make_round2_evals(
            ("m1", [{"element": "population", "polarity": "include",
                      "term_a": "adults", "term_b": "adult patients",
                      "is_duplicate": True, "preferred": "adults"}]),
            ("m2", [{"element": "population", "polarity": "include",
                      "term_a": "adults", "term_b": "adult patients",
                      "is_duplicate": True, "preferred": "adults"}]),
        )
        edges = aggregate_dedup_edges(evals)
        key = ("population", "include", "adult patients", "adults")
        assert key in edges
        assert edges[key]["votes"] == 2

    def test_canonical_key_order(self) -> None:
        """Reversed term order should produce the same canonical key."""
        evals = _make_round2_evals(
            ("m1", [{"element": "population", "polarity": "include",
                      "term_a": "zebra", "term_b": "alpha",
                      "is_duplicate": True, "preferred": "alpha"}]),
        )
        edges = aggregate_dedup_edges(evals)
        key = ("population", "include", "alpha", "zebra")
        assert key in edges


# ---------------------------------------------------------------------------
# TestDedupMergerApply
# ---------------------------------------------------------------------------

class TestDedupMergerApply:
    """Full DedupMerger.merge() integration tests."""

    def test_dedup_replaces_terms(self) -> None:
        """Duplicate terms are replaced with canonical and deduplicated."""
        criteria = _make_criteria(
            population={"include": ["adults", "adult patients"],
                        "exclude": ["children"]},
        )
        evals = _make_round2_evals(
            ("m1", [{"element": "population", "polarity": "include",
                      "term_a": "adults", "term_b": "adult patients",
                      "is_duplicate": True, "preferred": "adults"}]),
            ("m2", [{"element": "population", "polarity": "include",
                      "term_a": "adults", "term_b": "adult patients",
                      "is_duplicate": True, "preferred": "adults"}]),
        )
        origin = _make_term_origin({
            "population": {
                "include": {"adults": ["m1", "m2"], "adult patients": ["m1"]},
                "exclude": {"children": ["m1", "m2"]},
            }
        })
        merger = DedupMerger(dedup_quorum_fraction=0.5)
        result = merger.merge(criteria, evals, origin)

        assert isinstance(result, DedupResult)
        pop = result.criteria.elements["population"]
        assert "adults" in pop.include
        assert "adult patients" not in pop.include
        assert "children" in pop.exclude

    def test_sub_quorum_goes_to_ambiguity(self) -> None:
        """Below-quorum edges produce ambiguity flags, not merges."""
        criteria = _make_criteria(
            population={"include": ["adults", "adult patients"],
                        "exclude": []},
        )
        # Only 1 model votes — below quorum of 2
        evals = _make_round2_evals(
            ("m1", [{"element": "population", "polarity": "include",
                      "term_a": "adults", "term_b": "adult patients",
                      "is_duplicate": True, "preferred": "adults"}]),
        )
        origin = _make_term_origin({
            "population": {
                "include": {"adults": ["m1"], "adult patients": ["m1"]},
                "exclude": {},
            }
        })
        merger = DedupMerger(dedup_quorum_fraction=0.5)
        result = merger.merge(criteria, evals, origin)

        pop = result.criteria.elements["population"]
        # Both terms survive since merge was not confirmed
        assert "adults" in pop.include
        assert "adult patients" in pop.include
        # Ambiguity flag generated
        flags = pop.ambiguity_flags
        assert any("possible duplicate" in f for f in flags)

    def test_element_quality_median(self) -> None:
        """element_quality is median of per-model mean scores * 10."""
        criteria = _make_criteria(
            population={"include": ["adults"], "exclude": []},
        )
        evals: dict[str, dict] = {
            "m1": {
                "dedup_edges": [],
                "quality": {"population": {"precision": 0.8, "completeness": 0.6, "actionability": 0.7}},
            },
            "m2": {
                "dedup_edges": [],
                "quality": {"population": {"precision": 0.9, "completeness": 0.9, "actionability": 0.9}},
            },
        }
        origin = _make_term_origin({
            "population": {"include": {"adults": ["m1", "m2"]}, "exclude": {}},
        })
        merger = DedupMerger(dedup_quorum_fraction=0.5)
        result = merger.merge(criteria, evals, origin)

        # m1 mean = (0.8+0.6+0.7)/3 = 0.7  -> 7
        # m2 mean = (0.9+0.9+0.9)/3 = 0.9  -> 9
        # median([7,9]) = 8
        assert result.quality_scores.get("population") == 8

    def test_low_agreement_term_flagged(self) -> None:
        """Term from only 1 of N models gets low-agreement flag."""
        criteria = _make_criteria(
            population={"include": ["adults", "elderly"],
                        "exclude": []},
        )
        # Provide evals from 3 models (no edges, just presence)
        evals = _make_round2_evals(
            ("m1", []),
            ("m2", []),
            ("m3", []),
        )
        origin = _make_term_origin({
            "population": {
                "include": {"adults": ["m1", "m2", "m3"], "elderly": ["m3"]},
                "exclude": {},
            }
        })
        merger = DedupMerger(dedup_quorum_fraction=0.5)
        result = merger.merge(criteria, evals, origin)

        pop = result.criteria.elements["population"]
        assert any("low agreement" in f and "elderly" in f for f in pop.ambiguity_flags)

    def test_transitive_leak_prevented(self) -> None:
        """Dedup only merges within confirmed edges, no transitive leak
        through sub-quorum edges."""
        criteria = _make_criteria(
            population={"include": ["A", "B", "C"], "exclude": []},
        )
        # A~B confirmed (2 votes), B~C only 1 vote (sub-quorum)
        evals = _make_round2_evals(
            ("m1", [
                {"element": "population", "polarity": "include",
                 "term_a": "A", "term_b": "B",
                 "is_duplicate": True, "preferred": "A"},
                {"element": "population", "polarity": "include",
                 "term_a": "B", "term_b": "C",
                 "is_duplicate": True, "preferred": "B"},
            ]),
            ("m2", [
                {"element": "population", "polarity": "include",
                 "term_a": "A", "term_b": "B",
                 "is_duplicate": True, "preferred": "A"},
            ]),
        )
        origin = _make_term_origin({
            "population": {
                "include": {"A": ["m1", "m2"], "B": ["m1", "m2"], "C": ["m1"]},
                "exclude": {},
            }
        })
        merger = DedupMerger(dedup_quorum_fraction=0.5)
        result = merger.merge(criteria, evals, origin)

        pop = result.criteria.elements["population"]
        # A and B merged into A; C survives separately
        assert "A" in pop.include
        assert "B" not in pop.include
        assert "C" in pop.include

    def test_model_votes_preserved(self) -> None:
        """model_votes on each element must not be modified."""
        votes = {"adults": 0.75, "exclude:children": 1.0}
        criteria = _make_criteria(
            population={"include": ["adults"], "exclude": ["children"],
                        "model_votes": votes},
        )
        evals = _make_round2_evals()
        origin = _make_term_origin({
            "population": {
                "include": {"adults": ["m1"]},
                "exclude": {"children": ["m1"]},
            }
        })
        merger = DedupMerger(dedup_quorum_fraction=0.5)
        result = merger.merge(criteria, evals, origin)

        pop = result.criteria.elements["population"]
        assert pop.model_votes == votes

    def test_retroactive_term_origin(self) -> None:
        """Canonical term inherits all contributors from merged terms."""
        criteria = _make_criteria(
            population={"include": ["adults", "adult patients"],
                        "exclude": []},
        )
        evals = _make_round2_evals(
            ("m1", [{"element": "population", "polarity": "include",
                      "term_a": "adults", "term_b": "adult patients",
                      "is_duplicate": True, "preferred": "adults"}]),
            ("m2", [{"element": "population", "polarity": "include",
                      "term_a": "adults", "term_b": "adult patients",
                      "is_duplicate": True, "preferred": "adults"}]),
        )
        origin = _make_term_origin({
            "population": {
                "include": {"adults": ["m1"], "adult patients": ["m2"]},
                "exclude": {},
            }
        })
        merger = DedupMerger(dedup_quorum_fraction=0.5)
        result = merger.merge(criteria, evals, origin)

        corrected = result.corrected_term_origin
        # Canonical "adults" should have both m1 and m2
        contributors = corrected["population"]["include"]["adults"]
        assert "m1" in contributors
        assert "m2" in contributors

    def test_edge_key_canonical_ordering(self) -> None:
        """Edge keys always use (min, max) for term ordering."""
        evals = _make_round2_evals(
            ("m1", [{"element": "intervention", "polarity": "include",
                      "term_a": "surgery", "term_b": "operation",
                      "is_duplicate": True, "preferred": "surgery"}]),
            ("m2", [{"element": "intervention", "polarity": "include",
                      "term_a": "operation", "term_b": "surgery",
                      "is_duplicate": True, "preferred": "surgery"}]),
        )
        edges = aggregate_dedup_edges(evals)
        # Both should map to the same canonical key
        key = ("intervention", "include", "operation", "surgery")
        assert key in edges
        assert edges[key]["votes"] == 2

    def test_zero_surviving_evals(self) -> None:
        """Empty round2_evals returns criteria unchanged (graceful degradation)."""
        criteria = _make_criteria(
            population={"include": ["adults"], "exclude": ["children"]},
        )
        origin = _make_term_origin({
            "population": {
                "include": {"adults": ["m1"]},
                "exclude": {"children": ["m1"]},
            }
        })
        merger = DedupMerger(dedup_quorum_fraction=0.5)
        result = merger.merge(criteria, {}, origin)

        assert result.criteria.elements["population"].include == ["adults"]
        assert result.criteria.elements["population"].exclude == ["children"]
        assert result.dedup_log == []
