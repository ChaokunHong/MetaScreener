"""Unit tests for framework auto-detection via LLM classification."""
from __future__ import annotations

import pytest

from metascreener.core.enums import CriteriaFramework
from metascreener.criteria.framework_detector import (
    FrameworkDetectionResult,
    FrameworkDetector,
)
from metascreener.llm.adapters.mock import MockLLMAdapter


@pytest.fixture
def detector_with_mock() -> FrameworkDetector:
    """Detector backed by a mock that returns a valid PICO detection."""
    adapter = MockLLMAdapter(
        model_id="mock-detector",
        response_json={
            "recommended_framework": "pico",
            "confidence": 0.92,
            "reasoning": "Intervention study with drug treatment",
            "alternatives": ["peo"],
        },
    )
    return FrameworkDetector(backend=adapter)


@pytest.mark.asyncio
async def test_detect_returns_framework(detector_with_mock: FrameworkDetector) -> None:
    """Successful detection returns the correct framework and metadata."""
    result = await detector_with_mock.detect("Effect of drug X on mortality")
    assert isinstance(result, FrameworkDetectionResult)
    assert result.framework == CriteriaFramework.PICO
    assert result.confidence >= 0.0
    assert result.reasoning


@pytest.mark.asyncio
async def test_detect_with_override() -> None:
    """When user specifies framework, detection is skipped."""
    adapter = MockLLMAdapter(model_id="mock")
    detector = FrameworkDetector(backend=adapter)
    result = await detector.detect(
        "some text",
        override_framework=CriteriaFramework.SPIDER,
    )
    assert result.framework == CriteriaFramework.SPIDER
    assert result.confidence == 1.0
    assert result.prompt_hash is None


@pytest.mark.asyncio
async def test_detect_fallback_on_parse_error() -> None:
    """On LLM parse failure, fallback to PICO with low confidence."""
    adapter = MockLLMAdapter(
        model_id="mock-broken",
        response_json={"broken": True},  # Missing required fields
    )
    detector = FrameworkDetector(backend=adapter)
    result = await detector.detect("some text")
    assert result.framework == CriteriaFramework.PICO
    assert result.confidence < 0.5


@pytest.mark.asyncio
async def test_detect_unknown_framework_falls_back_to_pico() -> None:
    """When the LLM returns an unknown framework string, default to PICO."""
    adapter = MockLLMAdapter(
        model_id="mock-unknown",
        response_json={
            "recommended_framework": "nonexistent_framework",
            "confidence": 0.8,
            "reasoning": "Made up framework",
            "alternatives": [],
        },
    )
    detector = FrameworkDetector(backend=adapter)
    result = await detector.detect("some text")
    assert result.framework == CriteriaFramework.PICO


@pytest.mark.asyncio
async def test_detect_stores_prompt_hash(detector_with_mock: FrameworkDetector) -> None:
    """Detection result includes the SHA256 prompt hash."""
    result = await detector_with_mock.detect("Effect of drug X on mortality")
    assert result.prompt_hash is not None
    assert len(result.prompt_hash) == 64  # SHA256 hex length


@pytest.mark.asyncio
async def test_detect_alternatives_preserved(
    detector_with_mock: FrameworkDetector,
) -> None:
    """Alternative frameworks from the LLM response are preserved."""
    result = await detector_with_mock.detect("Effect of drug X on mortality")
    assert result.alternatives == ["peo"]
