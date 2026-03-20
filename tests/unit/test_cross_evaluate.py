"""Tests for cross_evaluate_v1 prompt and response validation."""
from __future__ import annotations

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, ReviewCriteria
from metascreener.criteria.prompts.cross_evaluate_v1 import (
    build_cross_evaluate_prompt,
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
