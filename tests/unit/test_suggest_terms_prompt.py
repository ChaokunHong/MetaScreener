"""Tests for the suggest_terms_v1 prompt builder."""
from __future__ import annotations

from metascreener.criteria.prompts.suggest_terms_v1 import build_suggest_terms_prompt


def test_build_suggest_terms_prompt_returns_string() -> None:
    """Call with full args; result must be a non-trivial string."""
    prompt = build_suggest_terms_prompt(
        element_key="population",
        element_name="Population",
        current_include=["adults", "patients aged 18 and over"],
        current_exclude=["children", "neonates"],
        topic="Effect of metformin on glycaemic control in type 2 diabetes",
        framework="pico",
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 100


def test_prompt_contains_no_repeat_instruction() -> None:
    """Prompt must instruct the LLM not to repeat existing terms."""
    prompt = build_suggest_terms_prompt(
        element_key="population",
        element_name="Population",
        current_include=["adults"],
        current_exclude=["children"],
        topic="Metformin in type 2 diabetes",
        framework="pico",
    )
    lower = prompt.lower()
    assert ("not" in lower or "NOT" in prompt) and (
        "repeat" in lower or "already" in lower
    )


def test_prompt_contains_current_terms() -> None:
    """Existing include/exclude terms must appear in the prompt string."""
    include_terms = ["randomised controlled trial", "adults aged 18-65"]
    exclude_terms = ["open-label studies", "paediatric patients"]
    prompt = build_suggest_terms_prompt(
        element_key="study_design",
        element_name="Study Design",
        current_include=include_terms,
        current_exclude=exclude_terms,
        topic="Antibiotic stewardship in ICU",
        framework="pico",
    )
    for term in include_terms + exclude_terms:
        assert term in prompt


def test_prompt_requests_json_output() -> None:
    """Prompt must ask for JSON-formatted output."""
    prompt = build_suggest_terms_prompt(
        element_key="intervention",
        element_name="Intervention",
        current_include=["metformin"],
        current_exclude=["insulin"],
        topic="Metformin in type 2 diabetes",
        framework="pico",
    )
    assert "json" in prompt.lower() or "JSON" in prompt


def test_prompt_handles_empty_lists() -> None:
    """Empty include/exclude lists must still return a valid string with element_name."""
    prompt = build_suggest_terms_prompt(
        element_key="outcome",
        element_name="Outcome",
        current_include=[],
        current_exclude=[],
        topic="Cardiovascular mortality in heart failure",
        framework="pico",
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "Outcome" in prompt
