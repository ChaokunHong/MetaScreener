"""Integration tests for criteria wizard workflows."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from metascreener.core.enums import CriteriaFramework, CriteriaInputMode, WizardMode
from metascreener.core.models import ReviewCriteria, WizardSession
from metascreener.criteria.schema import CriteriaSchema
from metascreener.criteria.session import SessionManager
from metascreener.criteria.wizard import CriteriaWizard
from metascreener.llm.adapters.mock import MockLLMAdapter


def _make_gen_adapter(response: dict[str, Any] | None = None) -> MockLLMAdapter:
    """Create a mock generation adapter."""
    default: dict[str, Any] = {
        "research_question": "Effect of antimicrobial stewardship on ICU outcomes",
        "elements": {
            "population": {
                "name": "Population",
                "include": ["adult ICU patients", ">=18 years"],
                "exclude": ["pediatric"],
            },
            "intervention": {
                "name": "Intervention",
                "include": ["antimicrobial stewardship programs"],
                "exclude": [],
            },
            "comparison": {
                "name": "Comparison",
                "include": ["standard care"],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": ["mortality", "length of stay"],
                "exclude": [],
            },
        },
        "study_design_include": ["RCT", "quasi-experimental"],
        "study_design_exclude": ["case reports"],
        "ambiguities": [],
    }
    return MockLLMAdapter(model_id="mock-gen", response_json=response or default)


def _make_alt_adapter() -> MockLLMAdapter:
    """Create an alternative generation adapter for consensus testing."""
    return MockLLMAdapter(
        model_id="mock-gen-alt",
        response_json={
            "research_question": "Effect of antimicrobial stewardship on ICU outcomes",
            "elements": {
                "population": {
                    "name": "Population",
                    "include": ["adult patients in intensive care"],
                    "exclude": ["children"],
                },
                "intervention": {
                    "name": "Intervention",
                    "include": ["antibiotic stewardship"],
                    "exclude": [],
                },
                "comparison": {
                    "name": "Comparison",
                    "include": ["usual care"],
                    "exclude": [],
                },
                "outcome": {
                    "name": "Outcome",
                    "include": ["all-cause mortality", "hospital stay"],
                    "exclude": [],
                },
            },
            "study_design_include": ["randomized controlled trial"],
            "study_design_exclude": ["editorials"],
            "ambiguities": ["age threshold"],
        },
    )


def _make_detector_adapter() -> MockLLMAdapter:
    """Create a mock framework detector adapter."""
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
    """Create a mock quality assessment adapter."""
    return MockLLMAdapter(
        model_id="mock-quality",
        response_json={
            "total": 82,
            "completeness": 90,
            "precision": 78,
            "consistency": 85,
            "actionability": 75,
            "suggestions": ["Consider specifying primary vs secondary outcomes"],
        },
    )


async def _noop_ask(question: str) -> str:
    """No-op ask callback that always answers 'yes'."""
    return "yes"


async def _noop_status(msg: str) -> None:
    """No-op status callback."""


async def _noop_confirm(msg: str) -> bool:
    """No-op confirm callback that always returns True."""
    return True


class TestFullSmartWorkflow:
    """Test the complete smart mode workflow end-to-end."""

    @pytest.mark.asyncio
    async def test_topic_to_yaml_roundtrip(self, tmp_path: Path) -> None:
        """Topic -> detect framework -> generate -> validate -> save YAML -> load back."""
        wizard = CriteriaWizard(
            generation_backends=[_make_gen_adapter()],
            detector_backend=_make_detector_adapter(),
            quality_backend=_make_quality_adapter(),
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="antimicrobial stewardship in ICU",
            ask_user=_noop_ask,
            show_status=_noop_status,
            confirm=_noop_confirm,
        )

        # Verify result type and framework
        assert isinstance(result, ReviewCriteria)
        assert result.framework == CriteriaFramework.PICO
        assert len(result.elements) >= 3

        # Verify quality assessment ran
        assert result.quality_score is not None
        assert result.quality_score.total == 82

        # Verify YAML was saved and can be loaded back
        yaml_path = tmp_path / "criteria.yaml"
        assert yaml_path.exists()
        loaded = CriteriaSchema.load(yaml_path)
        assert loaded.framework == CriteriaFramework.PICO
        assert loaded.research_question == result.research_question
        assert len(loaded.elements) == len(result.elements)

    @pytest.mark.asyncio
    async def test_text_input_mode(self, tmp_path: Path) -> None:
        """Text input mode parses user-provided criteria text."""
        wizard = CriteriaWizard(
            generation_backends=[_make_gen_adapter()],
            detector_backend=_make_detector_adapter(),
            quality_backend=_make_quality_adapter(),
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TEXT,
            wizard_mode=WizardMode.SMART,
            raw_input=(
                "Include: adult ICU patients with antimicrobial stewardship. "
                "Exclude: pediatric. Outcomes: mortality, LOS."
            ),
            ask_user=_noop_ask,
            show_status=_noop_status,
            confirm=_noop_confirm,
        )

        assert isinstance(result, ReviewCriteria)
        assert result.framework == CriteriaFramework.PICO
        assert len(result.elements) >= 3

    @pytest.mark.asyncio
    async def test_without_quality_backend(self, tmp_path: Path) -> None:
        """Wizard runs without quality backend (quality_score is None)."""
        wizard = CriteriaWizard(
            generation_backends=[_make_gen_adapter()],
            detector_backend=_make_detector_adapter(),
            quality_backend=None,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="antimicrobial stewardship in ICU",
            ask_user=_noop_ask,
            show_status=_noop_status,
            confirm=_noop_confirm,
        )

        assert isinstance(result, ReviewCriteria)
        assert result.quality_score is None

    @pytest.mark.asyncio
    async def test_framework_override(self, tmp_path: Path) -> None:
        """Override framework bypasses detector and uses specified framework."""
        wizard = CriteriaWizard(
            generation_backends=[_make_gen_adapter()],
            detector_backend=_make_detector_adapter(),
            quality_backend=None,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="antimicrobial stewardship in ICU",
            ask_user=_noop_ask,
            show_status=_noop_status,
            confirm=_noop_confirm,
            override_framework=CriteriaFramework.PICO,
        )

        assert result.framework == CriteriaFramework.PICO

    @pytest.mark.asyncio
    async def test_guided_mode_walks_through_elements(self, tmp_path: Path) -> None:
        """Guided mode calls ask_user for each element."""
        asked_questions: list[str] = []

        async def _tracking_ask(question: str) -> str:
            asked_questions.append(question)
            return "yes"

        wizard = CriteriaWizard(
            generation_backends=[_make_gen_adapter()],
            detector_backend=_make_detector_adapter(),
            quality_backend=None,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.GUIDED,
            raw_input="antimicrobial stewardship in ICU",
            ask_user=_tracking_ask,
            show_status=_noop_status,
            confirm=_noop_confirm,
        )

        assert isinstance(result, ReviewCriteria)
        # In guided mode, ask_user should be called for each element
        assert len(asked_questions) >= len(result.elements)


class TestMultiModelConsensus:
    """Test multi-model consensus integration."""

    @pytest.mark.asyncio
    async def test_two_models_merge_with_votes(self, tmp_path: Path) -> None:
        """Two mock adapters with different outputs produce merged criteria."""
        wizard = CriteriaWizard(
            generation_backends=[_make_gen_adapter(), _make_alt_adapter()],
            detector_backend=_make_detector_adapter(),
            quality_backend=_make_quality_adapter(),
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="antimicrobial stewardship in ICU",
            ask_user=_noop_ask,
            show_status=_noop_status,
            confirm=_noop_confirm,
        )

        assert isinstance(result, ReviewCriteria)

        # Population should have union of terms from both models
        pop = result.elements.get("population")
        assert pop is not None
        assert len(pop.include) >= 2  # at least terms from both

        # model_votes should be populated for multi-model consensus
        assert pop.model_votes is not None
        assert len(pop.model_votes) > 0

    @pytest.mark.asyncio
    async def test_consensus_merges_study_designs(self, tmp_path: Path) -> None:
        """Multi-model consensus produces union of study design lists."""
        wizard = CriteriaWizard(
            generation_backends=[_make_gen_adapter(), _make_alt_adapter()],
            detector_backend=_make_detector_adapter(),
            quality_backend=None,
            output_dir=tmp_path,
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="antimicrobial stewardship in ICU",
            ask_user=_noop_ask,
            show_status=_noop_status,
            confirm=_noop_confirm,
        )

        # Should include study designs from both adapters
        assert len(result.study_design_include) >= 2
        assert len(result.study_design_exclude) >= 1


class TestSessionRecovery:
    """Test session persistence and recovery."""

    @pytest.mark.asyncio
    async def test_session_save_and_load(self, tmp_path: Path) -> None:
        """Session can be saved and loaded back by ID."""
        sessions_dir = tmp_path / "sessions"
        mgr = SessionManager(sessions_dir=sessions_dir)

        # Create a session manually (simulating wizard mid-step)
        session = WizardSession(current_step=3)
        mgr.save(session)

        # Verify it can be loaded back
        loaded = mgr.load(session.session_id)
        assert loaded is not None
        assert loaded.current_step == 3
        assert loaded.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_load_latest_returns_most_recent(self, tmp_path: Path) -> None:
        """load_latest returns the most recently saved session."""
        sessions_dir = tmp_path / "sessions"
        mgr = SessionManager(sessions_dir=sessions_dir)

        # Save two sessions
        session1 = WizardSession(current_step=1)
        mgr.save(session1)

        session2 = WizardSession(current_step=5)
        mgr.save(session2)

        # load_latest should return the most recent
        latest = mgr.load_latest()
        assert latest is not None
        assert latest.session_id == session2.session_id
        assert latest.current_step == 5

    @pytest.mark.asyncio
    async def test_load_nonexistent_session_returns_none(
        self, tmp_path: Path
    ) -> None:
        """Loading a non-existent session returns None."""
        sessions_dir = tmp_path / "sessions"
        mgr = SessionManager(sessions_dir=sessions_dir)

        result = mgr.load("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_latest_empty_dir_returns_none(
        self, tmp_path: Path
    ) -> None:
        """load_latest with no sessions returns None."""
        sessions_dir = tmp_path / "sessions"
        mgr = SessionManager(sessions_dir=sessions_dir)

        result = mgr.load_latest()
        assert result is None
