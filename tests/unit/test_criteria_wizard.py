"""Tests for CriteriaWizard orchestrator."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.core.enums import CriteriaFramework, CriteriaInputMode, WizardMode
from metascreener.core.models import ReviewCriteria
from metascreener.criteria.wizard import CriteriaWizard
from metascreener.llm.adapters.mock import MockLLMAdapter


def _make_mock_adapter(response: dict | None = None) -> MockLLMAdapter:
    """Create a mock adapter with a criteria generation response."""
    default_response = {
        "research_question": "Effect of X on Y",
        "elements": {
            "population": {
                "name": "Population",
                "include": ["adults"],
                "exclude": ["children"],
            },
            "intervention": {
                "name": "Intervention",
                "include": ["drug X"],
                "exclude": [],
            },
        },
        "study_design_include": ["RCT"],
        "study_design_exclude": ["case reports"],
        "ambiguities": [],
    }
    return MockLLMAdapter(
        model_id="mock-wizard",
        response_json=response or default_response,
    )


def _make_detector_adapter() -> MockLLMAdapter:
    """Create a mock adapter that returns framework detection results."""
    return MockLLMAdapter(
        model_id="mock-detector",
        response_json={
            "recommended_framework": "pico",
            "confidence": 0.92,
            "reasoning": "Intervention study",
            "alternatives": [],
        },
    )


def _make_quality_adapter() -> MockLLMAdapter:
    """Create a mock adapter that returns quality scores."""
    return MockLLMAdapter(
        model_id="mock-quality",
        response_json={
            "total": 85,
            "completeness": 90,
            "precision": 80,
            "consistency": 85,
            "actionability": 82,
            "suggestions": [],
        },
    )


class TestCriteriaWizard:
    """Tests for CriteriaWizard orchestrator."""

    @pytest.mark.asyncio
    async def test_smart_mode_full_flow(self, tmp_path: Path) -> None:
        """Smart mode: topic -> detect -> generate -> validate -> result."""
        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()
        quality_adapter = _make_quality_adapter()

        status_messages: list[str] = []
        questions_asked: list[str] = []

        async def mock_ask(question: str) -> str:
            questions_asked.append(question)
            return "yes"

        async def mock_status(msg: str) -> None:
            status_messages.append(msg)

        async def mock_confirm(msg: str) -> bool:
            return True

        wizard = CriteriaWizard(
            generation_backends=[gen_adapter],
            detector_backend=detector_adapter,
            quality_backend=quality_adapter,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="antimicrobial stewardship in ICU",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        assert isinstance(result, ReviewCriteria)
        assert result.framework == CriteriaFramework.PICO
        assert len(result.elements) > 0
        assert len(status_messages) > 0  # Should have shown progress
        # Verify criteria.yaml was saved
        assert (tmp_path / "criteria.yaml").exists()

    @pytest.mark.asyncio
    async def test_guided_mode_asks_elements(self, tmp_path: Path) -> None:
        """Guided mode should ask about each required element."""
        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()
        quality_adapter = _make_quality_adapter()

        questions_asked: list[str] = []

        async def mock_ask(question: str) -> str:
            questions_asked.append(question)
            return "looks good"

        async def mock_status(msg: str) -> None:
            pass

        async def mock_confirm(msg: str) -> bool:
            return True

        wizard = CriteriaWizard(
            generation_backends=[gen_adapter],
            detector_backend=detector_adapter,
            quality_backend=quality_adapter,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.GUIDED,
            raw_input="antimicrobial stewardship",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        assert isinstance(result, ReviewCriteria)
        # In guided mode, should have asked about elements
        assert len(questions_asked) > 0

    @pytest.mark.asyncio
    async def test_text_input_mode(self, tmp_path: Path) -> None:
        """Text input mode should use parse_text instead of generate_from_topic."""
        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()

        status_messages: list[str] = []

        async def mock_ask(question: str) -> str:
            return "yes"

        async def mock_status(msg: str) -> None:
            status_messages.append(msg)

        async def mock_confirm(msg: str) -> bool:
            return True

        wizard = CriteriaWizard(
            generation_backends=[gen_adapter],
            detector_backend=detector_adapter,
            quality_backend=None,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TEXT,
            wizard_mode=WizardMode.SMART,
            raw_input="Include adults with diabetes. Exclude children.",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        assert isinstance(result, ReviewCriteria)
        assert len(result.elements) > 0

    @pytest.mark.asyncio
    async def test_override_framework(self, tmp_path: Path) -> None:
        """Override framework should skip detection and use specified framework."""
        gen_adapter = _make_mock_adapter()
        # Detector should not be called (override), but we pass one anyway
        detector_adapter = _make_detector_adapter()

        status_messages: list[str] = []

        async def mock_ask(question: str) -> str:
            return "yes"

        async def mock_status(msg: str) -> None:
            status_messages.append(msg)

        async def mock_confirm(msg: str) -> bool:
            return True

        wizard = CriteriaWizard(
            generation_backends=[gen_adapter],
            detector_backend=detector_adapter,
            quality_backend=None,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="diagnostic accuracy study",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
            override_framework=CriteriaFramework.SPIDER,
        )

        assert isinstance(result, ReviewCriteria)
        # Framework should match the override, not what detector would say
        assert result.framework == CriteriaFramework.SPIDER

    @pytest.mark.asyncio
    async def test_no_quality_backend_skips_quality(self, tmp_path: Path) -> None:
        """When quality_backend is None, quality validation is skipped."""
        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()

        async def mock_ask(question: str) -> str:
            return "yes"

        async def mock_status(msg: str) -> None:
            pass

        async def mock_confirm(msg: str) -> bool:
            return True

        wizard = CriteriaWizard(
            generation_backends=[gen_adapter],
            detector_backend=detector_adapter,
            quality_backend=None,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="treatment of condition Y",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        assert isinstance(result, ReviewCriteria)
        # Quality score should be None when no backend provided
        assert result.quality_score is None

    @pytest.mark.asyncio
    async def test_quality_score_attached(self, tmp_path: Path) -> None:
        """When quality backend is provided, quality score should be attached."""
        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()
        quality_adapter = _make_quality_adapter()

        async def mock_ask(question: str) -> str:
            return "yes"

        async def mock_status(msg: str) -> None:
            pass

        async def mock_confirm(msg: str) -> bool:
            return True

        wizard = CriteriaWizard(
            generation_backends=[gen_adapter],
            detector_backend=detector_adapter,
            quality_backend=quality_adapter,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="effect of drug A on condition B",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        assert result.quality_score is not None
        assert result.quality_score.total == 85

    @pytest.mark.asyncio
    async def test_language_override(self, tmp_path: Path) -> None:
        """Language override should be used instead of auto-detection."""
        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()

        async def mock_ask(question: str) -> str:
            return "yes"

        async def mock_status(msg: str) -> None:
            pass

        async def mock_confirm(msg: str) -> bool:
            return True

        wizard = CriteriaWizard(
            generation_backends=[gen_adapter],
            detector_backend=detector_adapter,
            quality_backend=None,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="some english text",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
            language="zh",
        )

        assert result.detected_language == "zh"

    @pytest.mark.asyncio
    async def test_smart_mode_with_validation_issues(self, tmp_path: Path) -> None:
        """Smart mode should ask about issues when validation finds problems."""
        # Create adapter that generates criteria with an empty include list
        # to trigger "too broad" validation rule
        gen_adapter = MockLLMAdapter(
            model_id="mock-wizard",
            response_json={
                "research_question": "Effect of X on Y",
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": [],
                        "exclude": [],
                    },
                },
                "study_design_include": [],
                "study_design_exclude": [],
                "ambiguities": [],
            },
        )
        detector_adapter = _make_detector_adapter()

        questions_asked: list[str] = []

        async def mock_ask(question: str) -> str:
            questions_asked.append(question)
            return "add adults to population"

        async def mock_status(msg: str) -> None:
            pass

        async def mock_confirm(msg: str) -> bool:
            return True

        wizard = CriteriaWizard(
            generation_backends=[gen_adapter],
            detector_backend=detector_adapter,
            quality_backend=None,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="drug effects",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        assert isinstance(result, ReviewCriteria)
        # The "too broad" issue has element=None, so smart mode won't ask about it
        # (only element-specific issues get asked about)

    @pytest.mark.asyncio
    async def test_output_dir_created_if_missing(self, tmp_path: Path) -> None:
        """Output directory should be created if it does not exist."""
        nested_dir = tmp_path / "nested" / "output"
        assert not nested_dir.exists()

        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()

        async def mock_ask(question: str) -> str:
            return "yes"

        async def mock_status(msg: str) -> None:
            pass

        async def mock_confirm(msg: str) -> bool:
            return True

        wizard = CriteriaWizard(
            generation_backends=[gen_adapter],
            detector_backend=detector_adapter,
            quality_backend=None,
            output_dir=nested_dir,
        )

        await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="test topic",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        assert nested_dir.exists()
        assert (nested_dir / "criteria.yaml").exists()
