"""Tests for cross_evaluate_v1 prompt and response validation."""
from __future__ import annotations

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, ReviewCriteria
from metascreener.criteria.prompts.cross_evaluate_v1 import (
    build_cross_evaluate_prompt,
    transform_cross_evaluate_response,
    validate_cross_evaluate_response,
)


class TestBuildPrompt:
    def test_contains_polarity_instruction(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={"population": CriteriaElement(name="Population", include=["adults"])},
        )
        prompt = build_cross_evaluate_prompt(criteria)
        assert "include list OR within the exclude list" in prompt
        assert "Never merge a term from include with a term from exclude" in prompt

    def test_terms_sorted_alphabetically(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={"population": CriteriaElement(
                name="Population", include=["zebra", "apple", "mango"],
            )},
        )
        prompt = build_cross_evaluate_prompt(criteria)
        apple_pos = prompt.index("apple")
        mango_pos = prompt.index("mango")
        zebra_pos = prompt.index("zebra")
        assert apple_pos < mango_pos < zebra_pos

    def test_includes_json_output_spec(self) -> None:
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={"population": CriteriaElement(name="Population", include=["adults"])},
        )
        prompt = build_cross_evaluate_prompt(criteria)
        assert "element_evaluations" in prompt
        assert "duplicate_pairs" in prompt
        assert "quality" in prompt


class TestValidateResponse:
    def test_valid_response(self) -> None:
        resp = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [
                        {"term_a": "a", "term_b": "b", "preferred": "a", "polarity": "include"}
                    ],
                    "quality": {"precision": 8, "completeness": 7, "actionability": 9},
                }
            }
        }
        assert validate_cross_evaluate_response(resp) is True

    def test_valid_empty_pairs(self) -> None:
        resp = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [],
                    "quality": {"precision": 5, "completeness": 5, "actionability": 5},
                }
            }
        }
        assert validate_cross_evaluate_response(resp) is True

    def test_missing_key(self) -> None:
        assert validate_cross_evaluate_response({"bad": "data"}) is False

    def test_invalid_score_range(self) -> None:
        resp = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [],
                    "quality": {"precision": 15, "completeness": 7, "actionability": 9},
                }
            }
        }
        assert validate_cross_evaluate_response(resp) is False

    def test_preferred_not_in_pair(self) -> None:
        resp = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [
                        {"term_a": "a", "term_b": "b", "preferred": "c", "polarity": "include"}
                    ],
                    "quality": {"precision": 5, "completeness": 5, "actionability": 5},
                }
            }
        }
        assert validate_cross_evaluate_response(resp) is False

    def test_invalid_polarity(self) -> None:
        resp = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [
                        {"term_a": "a", "term_b": "b", "preferred": "a", "polarity": "both"}
                    ],
                    "quality": {"precision": 5, "completeness": 5, "actionability": 5},
                }
            }
        }
        assert validate_cross_evaluate_response(resp) is False

    def test_float_scores_accepted(self) -> None:
        """LLMs sometimes return float scores; validator should accept them."""
        resp = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [],
                    "quality": {"precision": 7.0, "completeness": 8.5, "actionability": 6.0},
                }
            }
        }
        assert validate_cross_evaluate_response(resp) is True

    def test_validate_accepts_extra_quality_keys(self) -> None:
        """Response with extra quality keys should still be valid."""
        response = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [],
                    "quality": {
                        "precision": 8,
                        "completeness": 7,
                        "actionability": 9,
                        "relevance": 8,  # extra key
                    },
                }
            }
        }
        assert validate_cross_evaluate_response(response) is True


class TestTransformResponse:
    """Tests for transform_cross_evaluate_response: LLM format → DedupMerger format."""

    def test_duplicate_pairs_become_dedup_edges(self) -> None:
        llm_response = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [
                        {"term_a": "adults", "term_b": "adult patients",
                         "preferred": "adults", "polarity": "include"}
                    ],
                    "quality": {"precision": 8, "completeness": 7, "actionability": 9},
                }
            }
        }
        result = transform_cross_evaluate_response(llm_response)

        assert "dedup_edges" in result
        assert len(result["dedup_edges"]) == 1
        edge = result["dedup_edges"][0]
        assert edge["element"] == "population"
        assert edge["polarity"] == "include"
        assert edge["term_a"] == "adults"
        assert edge["term_b"] == "adult patients"
        assert edge["is_duplicate"] is True
        assert edge["preferred"] == "adults"

    def test_quality_scores_normalised_to_0_1(self) -> None:
        llm_response = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [],
                    "quality": {"precision": 8, "completeness": 6, "actionability": 7},
                }
            }
        }
        result = transform_cross_evaluate_response(llm_response)

        q = result["quality"]["population"]
        assert q["precision"] == 0.8
        assert q["completeness"] == 0.6
        assert q["actionability"] == 0.7

    def test_empty_evaluations(self) -> None:
        result = transform_cross_evaluate_response({"element_evaluations": {}})
        assert result["dedup_edges"] == []
        assert result["quality"] == {}

    def test_multiple_elements(self) -> None:
        llm_response = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [
                        {"term_a": "a", "term_b": "b", "preferred": "a", "polarity": "include"}
                    ],
                    "quality": {"precision": 10, "completeness": 10, "actionability": 10},
                },
                "intervention": {
                    "duplicate_pairs": [],
                    "quality": {"precision": 5, "completeness": 5, "actionability": 5},
                },
            }
        }
        result = transform_cross_evaluate_response(llm_response)

        assert len(result["dedup_edges"]) == 1
        assert result["dedup_edges"][0]["element"] == "population"
        assert result["quality"]["population"]["precision"] == 1.0
        assert result["quality"]["intervention"]["precision"] == 0.5


class TestFullDataPath:
    """Integration test: LLM response → transform → DedupMerger."""

    def test_llm_response_through_dedup_merger(self) -> None:
        """Simulate the full Round 2 data path end-to-end."""
        from metascreener.criteria.dedup_merger import DedupMerger

        # 1. Build criteria (as Round 1 would produce)
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population",
                    include=["adults", "adult patients", "elderly"],
                    exclude=["children"],
                ),
            },
        )
        term_origin = {
            "population": {
                "include": {
                    "adults": ["model_a", "model_b"],
                    "adult patients": ["model_a"],
                    "elderly": ["model_b"],
                },
                "exclude": {"children": ["model_a", "model_b"]},
            }
        }

        # 2. Simulate LLM responses (raw format from cross-eval prompt)
        llm_response_a = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [
                        {"term_a": "adults", "term_b": "adult patients",
                         "preferred": "adults", "polarity": "include"},
                    ],
                    "quality": {"precision": 8, "completeness": 7, "actionability": 9},
                }
            }
        }
        llm_response_b = {
            "element_evaluations": {
                "population": {
                    "duplicate_pairs": [
                        {"term_a": "adults", "term_b": "adult patients",
                         "preferred": "adults", "polarity": "include"},
                    ],
                    "quality": {"precision": 9, "completeness": 8, "actionability": 8},
                }
            }
        }

        # 3. Transform (as generator._run_round2 now does)
        round2_evals = {
            "model_a": transform_cross_evaluate_response(llm_response_a),
            "model_b": transform_cross_evaluate_response(llm_response_b),
        }

        # 4. Verify transformed format matches DedupMerger expectations
        for model_data in round2_evals.values():
            assert "dedup_edges" in model_data
            assert "quality" in model_data
            assert isinstance(model_data["dedup_edges"], list)
            assert isinstance(model_data["quality"], dict)

        # 5. Run DedupMerger
        result = DedupMerger(dedup_quorum_fraction=0.5).merge(
            criteria, round2_evals, term_origin,
        )

        # 6. Verify dedup worked: "adult patients" merged into "adults"
        pop = result.criteria.elements["population"]
        assert "adults" in pop.include
        assert "adult patients" not in pop.include
        assert "elderly" in pop.include  # untouched
        assert "children" in pop.exclude  # untouched

        # 7. Verify quality scores computed correctly
        # model_a: mean(0.8, 0.7, 0.9) = 0.8
        # model_b: mean(0.9, 0.8, 0.8) = 0.833...
        # median([0.8, 0.833]) = 0.8166... → round(0.8166 * 10) = 8
        assert result.quality_scores["population"] == 8

        # 8. Verify term_origin corrected
        adults_contributors = result.corrected_term_origin["population"]["include"]["adults"]
        assert "model_a" in adults_contributors
