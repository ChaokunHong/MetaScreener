"""Tests for the pilot relevance assessment prompt builder."""
from __future__ import annotations

from metascreener.criteria.prompts.pilot_relevance_v1 import build_pilot_relevance_prompt


SAMPLE_CRITERIA = {
    "population": {
        "include": ["elderly patients aged 65 and over"],
        "exclude": ["paediatric patients"],
    },
    "intervention": {
        "include": ["metformin"],
        "exclude": [],
    },
    "outcome": {
        "include": ["HbA1c reduction"],
        "exclude": [],
    },
}


def test_prompt_returns_string() -> None:
    """build_pilot_relevance_prompt returns a non-trivial string."""
    articles = [
        {
            "pmid": "12345678",
            "title": "Effect of metformin on HbA1c in elderly diabetic patients",
            "abstract": "This study investigates the effect of metformin on glycaemic control.",
        }
    ]
    result = build_pilot_relevance_prompt(articles, SAMPLE_CRITERIA)

    assert isinstance(result, str)
    assert len(result) > 100


def test_prompt_contains_articles() -> None:
    """All article titles and PMIDs appear in the prompt."""
    articles = [
        {
            "pmid": "11111111",
            "title": "First Study Title",
            "abstract": "Abstract one.",
        },
        {
            "pmid": "22222222",
            "title": "Second Study Title",
            "abstract": "Abstract two.",
        },
    ]
    result = build_pilot_relevance_prompt(articles, SAMPLE_CRITERIA)

    assert "11111111" in result
    assert "First Study Title" in result
    assert "22222222" in result
    assert "Second Study Title" in result


def test_prompt_contains_criteria() -> None:
    """Criteria content (e.g. 'elderly') appears in the prompt."""
    articles = [
        {
            "pmid": "99999999",
            "title": "A relevant study",
            "abstract": "Some abstract text.",
        }
    ]
    result = build_pilot_relevance_prompt(articles, SAMPLE_CRITERIA)

    assert "elderly" in result


def test_prompt_requests_json() -> None:
    """The prompt instructs the model to return JSON output."""
    articles = [
        {
            "pmid": "55555555",
            "title": "Any Study",
            "abstract": "Any abstract.",
        }
    ]
    result = build_pilot_relevance_prompt(articles, SAMPLE_CRITERIA)

    assert "json" in result or "JSON" in result
