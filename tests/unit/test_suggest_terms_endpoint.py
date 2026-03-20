"""Unit tests for SuggestTermsRequest/Response Pydantic models."""
import pytest
from pydantic import ValidationError

from metascreener.api.schemas import (
    SuggestTermsRequest,
    SuggestTermsResponse,
    TermSuggestion,
)


def test_suggest_terms_request_valid() -> None:
    """SuggestTermsRequest accepts all fields and stores them correctly."""
    req = SuggestTermsRequest(
        element_key="population",
        element_name="Population",
        current_include=["adults", "elderly"],
        current_exclude=["children"],
        topic="cardiovascular disease prevention",
        framework="pico",
    )
    assert req.element_key == "population"
    assert len(req.current_include) == 2


def test_suggest_terms_request_defaults() -> None:
    """current_include and current_exclude default to empty lists."""
    req = SuggestTermsRequest(
        element_key="intervention",
        element_name="Intervention",
        topic="diabetes management",
        framework="pico",
    )
    assert req.current_include == []
    assert req.current_exclude == []


def test_suggest_terms_request_missing_required() -> None:
    """ValidationError raised when topic, framework, or element_name is missing."""
    with pytest.raises(ValidationError):
        SuggestTermsRequest(element_key="outcome")  # type: ignore[call-arg]


def test_term_suggestion_model() -> None:
    """TermSuggestion stores term and rationale correctly."""
    suggestion = TermSuggestion(
        term="hypertension",
        rationale="Commonly used synonym for high blood pressure in clinical literature.",
    )
    assert suggestion.term == "hypertension"
    assert "blood pressure" in suggestion.rationale


def test_suggest_terms_response_empty() -> None:
    """SuggestTermsResponse defaults to an empty suggestions list."""
    response = SuggestTermsResponse()
    assert response.suggestions == []


def test_suggest_terms_response_with_data() -> None:
    """SuggestTermsResponse stores provided TermSuggestion items."""
    suggestion = TermSuggestion(
        term="metformin",
        rationale="First-line pharmacological treatment for type 2 diabetes.",
    )
    response = SuggestTermsResponse(suggestions=[suggestion])
    assert len(response.suggestions) == 1
    assert response.suggestions[0].term == "metformin"
