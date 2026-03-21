"""Tests for multi-model consensus merger."""
from __future__ import annotations

from metascreener.core.enums import CriteriaFramework
from metascreener.criteria.consensus import ConsensusMerger


def test_identical_items_merge() -> None:
    """Two models returning identical items should merge with agreement 1.0."""
    outputs = [
        {
            "research_question": "Effect of X on Y",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adults"],
                    "exclude": ["children"],
                },
            },
            "study_design_include": ["RCT"],
            "study_design_exclude": [],
            "ambiguities": [],
        },
        {
            "research_question": "Effect of X on Y",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adults"],
                    "exclude": ["children"],
                },
            },
            "study_design_include": ["RCT"],
            "study_design_exclude": [],
            "ambiguities": [],
        },
    ]
    result = ConsensusMerger.merge(outputs, framework=CriteriaFramework.PICO)
    assert "adults" in result.elements["population"].include
    pop_votes = result.elements["population"].model_votes
    assert pop_votes is not None
    assert pop_votes.get("adults", 0.0) == 1.0


def test_union_of_different_items() -> None:
    """Different items from different models should appear as union."""
    outputs = [
        {
            "research_question": "Effect of X on Y",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adults"],
                    "exclude": [],
                },
            },
            "study_design_include": ["RCT"],
            "study_design_exclude": [],
            "ambiguities": [],
        },
        {
            "research_question": "Effect of X on Y",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["elderly"],
                    "exclude": [],
                },
            },
            "study_design_include": ["cohort"],
            "study_design_exclude": [],
            "ambiguities": [],
        },
    ]
    result = ConsensusMerger.merge(outputs, framework=CriteriaFramework.PICO)
    pop = result.elements["population"]
    assert "adults" in pop.include
    assert "elderly" in pop.include
    assert "RCT" in result.study_design_include
    assert "cohort" in result.study_design_include


def test_agreement_scoring() -> None:
    """Items in all models -> 1.0, items in 1 of 2 -> 0.5."""
    outputs = [
        {
            "research_question": "Q",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adults", "ICU patients"],
                    "exclude": [],
                },
            },
            "study_design_include": [],
            "study_design_exclude": [],
            "ambiguities": [],
        },
        {
            "research_question": "Q",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adults"],
                    "exclude": [],
                },
            },
            "study_design_include": [],
            "study_design_exclude": [],
            "ambiguities": [],
        },
    ]
    result = ConsensusMerger.merge(outputs, framework=CriteriaFramework.PICO)
    votes = result.elements["population"].model_votes
    assert votes is not None
    assert votes["adults"] == 1.0  # in both
    assert votes["ICU patients"] == 0.5  # in 1 of 2


def test_single_model_output() -> None:
    """Single model output should produce valid ReviewCriteria."""
    outputs = [
        {
            "research_question": "Effect of A on B",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adults"],
                    "exclude": ["children"],
                },
            },
            "study_design_include": ["RCT"],
            "study_design_exclude": ["case reports"],
            "ambiguities": [],
        },
    ]
    result = ConsensusMerger.merge(outputs, framework=CriteriaFramework.PICO)
    assert result.research_question == "Effect of A on B"
    assert "adults" in result.elements["population"].include
    assert "children" in result.elements["population"].exclude
    assert "RCT" in result.study_design_include


def test_empty_outputs() -> None:
    """Empty model outputs list should return empty ReviewCriteria."""
    result = ConsensusMerger.merge([], framework=CriteriaFramework.PICO)
    assert result.framework == CriteriaFramework.PICO
    assert result.elements == {}


def test_different_element_keys_merged() -> None:
    """Models with different element keys should produce union of keys."""
    outputs = [
        {
            "research_question": "Q",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adults"],
                    "exclude": [],
                },
            },
            "study_design_include": [],
            "study_design_exclude": [],
            "ambiguities": [],
        },
        {
            "research_question": "Q",
            "elements": {
                "intervention": {
                    "name": "Intervention",
                    "include": ["drug X"],
                    "exclude": [],
                },
            },
            "study_design_include": [],
            "study_design_exclude": [],
            "ambiguities": [],
        },
    ]
    result = ConsensusMerger.merge(outputs, framework=CriteriaFramework.PICO)
    assert "population" in result.elements
    assert "intervention" in result.elements
    assert "adults" in result.elements["population"].include
    assert "drug X" in result.elements["intervention"].include


def test_exclude_terms_agreement() -> None:
    """Exclude terms should also track agreement scores."""
    outputs = [
        {
            "research_question": "Q",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": [],
                    "exclude": ["children", "neonates"],
                },
            },
            "study_design_include": [],
            "study_design_exclude": [],
            "ambiguities": [],
        },
        {
            "research_question": "Q",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": [],
                    "exclude": ["children"],
                },
            },
            "study_design_include": [],
            "study_design_exclude": [],
            "ambiguities": [],
        },
    ]
    result = ConsensusMerger.merge(outputs, framework=CriteriaFramework.PICO)
    votes = result.elements["population"].model_votes
    assert votes is not None
    assert votes["exclude:children"] == 1.0  # in both
    assert votes["exclude:neonates"] == 0.5  # in 1 of 2


def test_required_elements_populated_from_framework() -> None:
    """Merged result should have required_elements from framework definition."""
    outputs = [
        {
            "research_question": "Q",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adults"],
                    "exclude": [],
                },
                "intervention": {
                    "name": "Intervention",
                    "include": ["drug X"],
                    "exclude": [],
                },
            },
            "study_design_include": [],
            "study_design_exclude": [],
        },
    ]
    result = ConsensusMerger.merge(outputs, framework=CriteriaFramework.PICO)
    # PICO framework requires "population" and "intervention"
    assert "population" in result.required_elements
    assert "intervention" in result.required_elements


def test_required_elements_only_present_keys() -> None:
    """required_elements should only include keys actually present in elements."""
    outputs = [
        {
            "research_question": "Q",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adults"],
                    "exclude": [],
                },
            },
            "study_design_include": [],
            "study_design_exclude": [],
        },
    ]
    result = ConsensusMerger.merge(outputs, framework=CriteriaFramework.PICO)
    # "intervention" is required by PICO but not present in elements
    assert "population" in result.required_elements
    assert "intervention" not in result.required_elements


def test_required_elements_multi_model() -> None:
    """Multi-model merge should also populate required_elements."""
    outputs = [
        {
            "research_question": "Q",
            "elements": {
                "population": {"name": "Pop", "include": ["a"], "exclude": []},
                "intervention": {"name": "Int", "include": ["b"], "exclude": []},
            },
            "study_design_include": [],
            "study_design_exclude": [],
        },
        {
            "research_question": "Q",
            "elements": {
                "population": {"name": "Pop", "include": ["c"], "exclude": []},
            },
            "study_design_include": [],
            "study_design_exclude": [],
        },
    ]
    result = ConsensusMerger.merge(outputs, framework=CriteriaFramework.PICO)
    assert "population" in result.required_elements
    assert "intervention" in result.required_elements


# --- Fix #1: Term normalization ---


def test_merge_normalizes_term_casing() -> None:
    """Terms differing only in case should be merged, preserving first-seen casing."""
    outputs = [
        {
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["heart attack", "T2DM"],
                    "exclude": ["children"],
                },
            },
        },
        {
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["Heart Attack", "t2dm"],
                    "exclude": ["Children"],
                },
            },
        },
    ]
    result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
    pop = result.elements["population"]
    # Should have 2 unique terms, not 4
    assert len(pop.include) == 2
    assert "heart attack" in pop.include  # first-seen casing preserved
    assert len(pop.exclude) == 1
    # model_votes should show 1.0 (both models agreed)
    assert pop.model_votes is not None
    assert pop.model_votes["heart attack"] == 1.0


def test_merge_normalizes_whitespace() -> None:
    """Extra whitespace in terms should be normalized."""
    outputs = [
        {
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["  type 2 diabetes  "],
                    "exclude": [],
                },
            },
        },
        {
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["type 2 diabetes"],
                    "exclude": [],
                },
            },
        },
    ]
    result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
    pop = result.elements["population"]
    assert len(pop.include) == 1
    assert pop.include[0] == "type 2 diabetes"


# --- Fix #2: Research question selection ---


def test_select_research_question_prefers_majority() -> None:
    """When multiple models produce the same RQ, prefer it."""
    outputs = [
        {
            "research_question": "What is the effect of X on Y?",
            "elements": {
                "population": {"name": "P", "include": ["a"], "exclude": []},
            },
        },
        {
            "research_question": "What is the effect of X on Y?",
            "elements": {
                "population": {"name": "P", "include": ["a"], "exclude": []},
            },
        },
        {
            "research_question": "How does X influence Y in adults?",
            "elements": {
                "population": {"name": "P", "include": ["a"], "exclude": []},
            },
        },
    ]
    result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
    assert result.research_question == "What is the effect of X on Y?"


def test_select_research_question_prefers_longest_on_tie() -> None:
    """When all RQs are unique, prefer the longest."""
    outputs = [
        {
            "research_question": "Short?",
            "elements": {
                "population": {"name": "P", "include": ["a"], "exclude": []},
            },
        },
        {
            "research_question": "A much longer and more detailed research question about the topic?",
            "elements": {
                "population": {"name": "P", "include": ["a"], "exclude": []},
            },
        },
    ]
    result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
    assert "longer and more detailed" in result.research_question


# --- Fix #3: Low-agreement flagging ---


def test_merge_flags_low_agreement_terms() -> None:
    """Terms from only 1 of 3 models should get ambiguity flags."""
    outputs = [
        {
            "elements": {
                "population": {
                    "name": "P",
                    "include": ["diabetes", "obesity"],
                    "exclude": [],
                },
            },
        },
        {
            "elements": {
                "population": {
                    "name": "P",
                    "include": ["diabetes"],
                    "exclude": [],
                },
            },
        },
        {
            "elements": {
                "population": {
                    "name": "P",
                    "include": ["diabetes"],
                    "exclude": [],
                },
            },
        },
    ]
    result = ConsensusMerger.merge(outputs, CriteriaFramework.PICO)
    pop = result.elements["population"]
    # "obesity" only from 1/3 models -> should have ambiguity flag
    assert any("obesity" in f and "1/3" in f for f in pop.ambiguity_flags)
    # "diabetes" from 3/3 models -> no flag
    assert not any("diabetes" in f for f in pop.ambiguity_flags)
