"""Unit tests for framework auto-detection via LLM classification."""
from __future__ import annotations

import pytest

from metascreener.core.enums import CriteriaFramework
from metascreener.criteria.framework_detector import (
    FrameworkDetectionResult,
    FrameworkDetector,
)
from metascreener.llm.adapters.mock import MockLLMAdapter


def _mock_adapter(
    model_id: str,
    framework: str = "pico",
    confidence: float = 0.92,
) -> MockLLMAdapter:
    """Create a mock adapter that returns a specific framework."""
    return MockLLMAdapter(
        model_id=model_id,
        response_json={
            "recommended_framework": framework,
            "confidence": confidence,
            "reasoning": f"Mock reasoning for {framework}",
            "alternatives": [],
        },
    )


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


# =====================================================================
# Multi-model voting tests
# =====================================================================


@pytest.mark.asyncio
async def test_detect_with_voting_majority() -> None:
    """Majority framework wins in multi-model voting."""
    backends = [
        _mock_adapter("m1", "pico", 0.9),
        _mock_adapter("m2", "pico", 0.85),
        _mock_adapter("m3", "spider", 0.8),
        _mock_adapter("m4", "pico", 0.7),
    ]
    detector = FrameworkDetector(backend=backends)
    result = await detector.detect("Effect of drug X on mortality")

    assert result.framework == CriteriaFramework.PICO
    # 3 out of 4 agree → confidence = 0.75
    assert result.confidence == pytest.approx(0.75)
    assert "spider" in result.alternatives
    assert "Majority voting" in result.reasoning


@pytest.mark.asyncio
async def test_detect_with_voting_single_backend() -> None:
    """Single backend falls back to normal detection (no voting)."""
    adapter = _mock_adapter("solo", "spider", 0.88)
    detector = FrameworkDetector(backend=[adapter])
    result = await detector.detect("Qualitative experiences of patients")

    assert result.framework == CriteriaFramework.SPIDER
    assert result.confidence == pytest.approx(0.88)
    # Single model path: no "Majority voting" prefix
    assert "Majority voting" not in result.reasoning


@pytest.mark.asyncio
async def test_detect_with_voting_tie_breaks_by_confidence() -> None:
    """On a tie, the framework with higher average confidence wins."""
    backends = [
        _mock_adapter("m1", "pico", 0.6),
        _mock_adapter("m2", "peo", 0.95),
    ]
    detector = FrameworkDetector(backend=backends)
    result = await detector.detect("Exposure to pollution")

    # Tie 1-1, peo has higher confidence → peo wins
    assert result.framework == CriteriaFramework.PEO
    assert result.confidence == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_detect_with_voting_backward_compat_single() -> None:
    """Passing a single backend (not a list) still works."""
    adapter = _mock_adapter("compat", "pico", 0.9)
    detector = FrameworkDetector(backend=adapter)
    result = await detector.detect("Drug trial")

    assert result.framework == CriteriaFramework.PICO


@pytest.mark.asyncio
async def test_detect_with_voting_override_skips_voting() -> None:
    """Override framework still bypasses voting entirely."""
    backends = [
        _mock_adapter("m1", "pico", 0.9),
        _mock_adapter("m2", "spider", 0.9),
    ]
    detector = FrameworkDetector(backend=backends)
    result = await detector.detect(
        "some text",
        override_framework=CriteriaFramework.PEO,
    )
    assert result.framework == CriteriaFramework.PEO
    assert result.confidence == 1.0
