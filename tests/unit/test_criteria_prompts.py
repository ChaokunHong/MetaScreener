"""Tests for criteria wizard prompt templates."""
from __future__ import annotations

from metascreener.criteria.prompts.detect_framework_v1 import (
    build_detect_framework_prompt,
)
from metascreener.criteria.prompts.generate_from_topic_v1 import (
    build_generate_from_topic_prompt,
)
from metascreener.criteria.prompts.infer_from_examples_v1 import (
    build_infer_from_examples_prompt,
)
from metascreener.criteria.prompts.parse_text_v1 import build_parse_text_prompt
from metascreener.criteria.prompts.refine_element_v1 import build_refine_element_prompt
from metascreener.criteria.prompts.validate_quality_v1 import (
    build_validate_quality_prompt,
)
from metascreener.llm.base import hash_prompt


def test_detect_framework_prompt_contains_input() -> None:
    """Detect-framework prompt must include user input and require JSON."""
    prompt = build_detect_framework_prompt("Effect of drug X on mortality in adults")
    assert "drug X" in prompt
    assert "JSON" in prompt
    assert "framework" in prompt.lower()


def test_detect_framework_prompt_lists_frameworks() -> None:
    """Detect-framework prompt must list all supported frameworks."""
    prompt = build_detect_framework_prompt("some topic")
    for fw in ("PICO", "PEO", "SPIDER", "PCC", "PIRD", "PIF", "PECO"):
        assert fw in prompt


def test_parse_text_prompt_includes_framework() -> None:
    """Parse-text prompt must include framework name and criteria text."""
    prompt = build_parse_text_prompt(
        criteria_text="Include adults with diabetes, exclude children",
        framework="pico",
        language="en",
    )
    assert "pico" in prompt.lower() or "PICO" in prompt
    assert "diabetes" in prompt


def test_parse_text_prompt_includes_language() -> None:
    """Parse-text prompt must include language instruction."""
    prompt = build_parse_text_prompt(
        criteria_text="Some criteria",
        framework="pico",
        language="zh",
    )
    assert "zh" in prompt


def test_generate_from_topic_prompt() -> None:
    """Generate-from-topic prompt must include topic and require JSON."""
    prompt = build_generate_from_topic_prompt(
        topic="antimicrobial resistance in ICU",
        framework="pico",
        language="en",
    )
    assert "antimicrobial" in prompt
    assert "JSON" in prompt


def test_infer_from_examples_prompt() -> None:
    """Infer-from-examples prompt must include example papers."""
    examples = [
        {
            "title": "Drug X for sepsis",
            "abstract": "A randomized trial...",
            "label": "INCLUDE",
        },
        {
            "title": "Review of antibiotics",
            "abstract": "A systematic review...",
            "label": "EXCLUDE",
        },
    ]
    prompt = build_infer_from_examples_prompt(
        examples=examples,
        framework="pico",
        language="en",
    )
    assert "Drug X for sepsis" in prompt
    assert "INCLUDE" in prompt
    assert "EXCLUDE" in prompt
    assert "inferred_from" in prompt


def test_validate_quality_prompt() -> None:
    """Validate-quality prompt must include criteria and scoring dimensions."""
    criteria_json = '{"elements": {"population": {"include": ["adults"]}}}'
    prompt = build_validate_quality_prompt(criteria_json)
    assert "quality" in prompt.lower() or "score" in prompt.lower()
    assert "adults" in prompt
    assert "completeness" in prompt.lower()
    assert "precision" in prompt.lower()


def test_refine_element_prompt() -> None:
    """Refine-element prompt must include element name and user feedback."""
    prompt = build_refine_element_prompt(
        element_name="Population",
        current_state='{"include": ["adults"], "exclude": []}',
        user_answer="I want to focus on elderly patients over 65",
        language="en",
    )
    assert "elderly" in prompt or "65" in prompt
    assert "Population" in prompt


def test_all_prompts_are_hashable() -> None:
    """All prompt outputs must be strings that can be hashed."""
    prompts = [
        build_detect_framework_prompt("test topic"),
        build_parse_text_prompt("test text", "pico", "en"),
        build_generate_from_topic_prompt("test topic", "pico", "en"),
        build_infer_from_examples_prompt(
            [{"title": "T", "abstract": "A", "label": "INCLUDE"}], "pico", "en"
        ),
        build_validate_quality_prompt('{"test": true}'),
        build_refine_element_prompt("Pop", "{}", "answer", "en"),
    ]
    for p in prompts:
        assert isinstance(p, str)
        h = hash_prompt(p)
        assert len(h) == 64  # SHA256 hex


def test_all_prompts_include_system_role() -> None:
    """All prompts must include the systematic review methodologist role."""
    prompts = [
        build_detect_framework_prompt("test"),
        build_parse_text_prompt("text", "pico", "en"),
        build_generate_from_topic_prompt("topic", "pico", "en"),
        build_infer_from_examples_prompt(
            [{"title": "T", "abstract": "A", "label": "INCLUDE"}], "pico", "en"
        ),
        build_validate_quality_prompt("{}"),
        build_refine_element_prompt("Pop", "{}", "answer", "en"),
    ]
    for p in prompts:
        assert "systematic review methodologist" in p.lower()


def test_all_prompts_require_json_output() -> None:
    """All prompts must require JSON output format."""
    prompts = [
        build_detect_framework_prompt("test"),
        build_parse_text_prompt("text", "pico", "en"),
        build_generate_from_topic_prompt("topic", "pico", "en"),
        build_infer_from_examples_prompt(
            [{"title": "T", "abstract": "A", "label": "INCLUDE"}], "pico", "en"
        ),
        build_validate_quality_prompt("{}"),
        build_refine_element_prompt("Pop", "{}", "answer", "en"),
    ]
    for p in prompts:
        assert "JSON" in p
