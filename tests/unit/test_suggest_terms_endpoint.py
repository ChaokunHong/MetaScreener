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


def test_missing_elements_detection() -> None:
    """Required elements with no include terms should be flagged."""
    from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS
    from metascreener.core.enums import CriteriaFramework

    fw_info = FRAMEWORK_ELEMENTS[CriteriaFramework.PICO]
    required = fw_info["required"]

    # Simulate criteria with only population
    elements = {"population": {"include": ["adults"], "exclude": []}}

    missing_req = [
        k for k in required
        if k not in elements or not elements[k].get("include")
    ]
    assert "intervention" in missing_req  # intervention is required for PICO
    assert "population" not in missing_req  # population has include terms


def test_missing_elements_all_present() -> None:
    """No missing elements when all required elements have include terms."""
    from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS
    from metascreener.core.enums import CriteriaFramework

    fw_info = FRAMEWORK_ELEMENTS[CriteriaFramework.PICO]
    required = fw_info["required"]

    elements = {
        "population": {"include": ["adults"], "exclude": []},
        "intervention": {"include": ["surgery"], "exclude": []},
    }

    missing_req = [
        k for k in required
        if k not in elements or not elements[k].get("include")
    ]
    assert missing_req == []


def test_missing_optional_elements_detection() -> None:
    """Optional elements with no include terms should be flagged as missing_optional."""
    from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS
    from metascreener.core.enums import CriteriaFramework

    fw_info = FRAMEWORK_ELEMENTS[CriteriaFramework.PICO]
    optional = fw_info["optional"]

    elements = {"population": {"include": ["adults"], "exclude": []}}

    missing_opt = [
        k for k in optional
        if k not in elements or not elements[k].get("include")
    ]
    assert "comparison" in missing_opt
    assert "outcome" in missing_opt


def test_n_models_clamping_logic():
    """Verify n_models clamping: [1, len(backends)]."""
    def clamp(n_models: int, n_backends: int) -> int:
        return max(1, min(int(n_models), n_backends))

    assert clamp(0, 4) == 1
    assert clamp(1, 4) == 1
    assert clamp(2, 4) == 2
    assert clamp(3, 4) == 3
    assert clamp(4, 4) == 4
    assert clamp(99, 4) == 4
    assert clamp(4, 2) == 2
    assert clamp(-1, 4) == 1
