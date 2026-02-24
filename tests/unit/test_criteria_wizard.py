"""Tests for CriteriaWizard orchestrator."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.core.enums import CriteriaFramework, CriteriaInputMode, WizardMode
from metascreener.core.models import CriteriaElement, ReviewCriteria
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
            sessions_dir=tmp_path / "sessions",
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
            sessions_dir=tmp_path / "sessions",
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
            sessions_dir=tmp_path / "sessions",
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
            sessions_dir=tmp_path / "sessions",
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
            sessions_dir=tmp_path / "sessions",
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
            sessions_dir=tmp_path / "sessions",
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
            sessions_dir=tmp_path / "sessions",
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
            sessions_dir=tmp_path / "sessions",
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
            sessions_dir=tmp_path / "sessions",
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

    @pytest.mark.asyncio
    async def test_session_persisted(self, tmp_path: Path) -> None:
        """Session files should be created during wizard run."""
        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()
        sessions_dir = tmp_path / "sessions"

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
            sessions_dir=sessions_dir,
        )

        await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="test topic",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        # Sessions directory should be created and have session files
        assert sessions_dir.exists()
        session_files = list(sessions_dir.glob("*.json"))
        assert len(session_files) > 0


class TestApplyUserFeedback:
    """Tests for _apply_user_feedback static method."""

    def test_add_with_plus(self) -> None:
        """'+term' should add to include list."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["adults"]
                ),
            },
        )
        CriteriaWizard._apply_user_feedback(criteria, "population", "+elderly")
        assert "elderly" in criteria.elements["population"].include

    def test_remove_with_minus(self) -> None:
        """'-term' should remove from include or exclude list."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population",
                    include=["adults", "elderly"],
                    exclude=["children"],
                ),
            },
        )
        CriteriaWizard._apply_user_feedback(criteria, "population", "-elderly")
        assert "elderly" not in criteria.elements["population"].include
        assert "adults" in criteria.elements["population"].include

    def test_add_colon_syntax(self) -> None:
        """'add: term' should add to include list."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "intervention": CriteriaElement(
                    name="Intervention", include=["drug A"]
                ),
            },
        )
        CriteriaWizard._apply_user_feedback(
            criteria, "intervention", "add: drug B"
        )
        assert "drug B" in criteria.elements["intervention"].include

    def test_remove_colon_syntax(self) -> None:
        """'remove: term' should remove from lists."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "intervention": CriteriaElement(
                    name="Intervention",
                    include=["drug A", "drug B"],
                ),
            },
        )
        CriteriaWizard._apply_user_feedback(
            criteria, "intervention", "remove: drug B"
        )
        assert "drug B" not in criteria.elements["intervention"].include

    def test_exclude_colon_syntax(self) -> None:
        """'exclude: term' should add to exclude list."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["adults"]
                ),
            },
        )
        CriteriaWizard._apply_user_feedback(
            criteria, "population", "exclude: neonates"
        )
        assert "neonates" in criteria.elements["population"].exclude

    def test_free_text_stored_as_notes(self) -> None:
        """Unstructured feedback should be stored as element notes."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["adults"]
                ),
            },
        )
        CriteriaWizard._apply_user_feedback(
            criteria, "population", "Consider adding age range 18-65"
        )
        assert criteria.elements["population"].notes is not None
        assert "age range" in criteria.elements["population"].notes

    def test_multiline_feedback(self) -> None:
        """Multiline feedback with mixed commands should all be applied."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["adults"]
                ),
            },
        )
        CriteriaWizard._apply_user_feedback(
            criteria,
            "population",
            "+elderly\n-adults\nexclude: neonates",
        )
        assert "elderly" in criteria.elements["population"].include
        assert "adults" not in criteria.elements["population"].include
        assert "neonates" in criteria.elements["population"].exclude

    def test_missing_element_no_crash(self) -> None:
        """Feedback for a nonexistent element should be a no-op."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={},
        )
        # Should not raise
        CriteriaWizard._apply_user_feedback(
            criteria, "nonexistent", "+some term"
        )

    def test_duplicate_add_ignored(self) -> None:
        """Adding a term that already exists should not duplicate it."""
        criteria = ReviewCriteria(
            framework=CriteriaFramework.PICO,
            elements={
                "population": CriteriaElement(
                    name="Population", include=["adults"]
                ),
            },
        )
        CriteriaWizard._apply_user_feedback(criteria, "population", "+adults")
        assert criteria.elements["population"].include.count("adults") == 1


class TestWizardGenerationAudit:
    """Tests for GenerationAudit population (TRIPOD-LLM compliance)."""

    @pytest.mark.asyncio
    async def test_generation_audit_populated_for_topic(
        self, tmp_path: Path
    ) -> None:
        """Topic mode should populate generation_audit with models used."""
        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()

        async def mock_ask(q: str) -> str:
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
            sessions_dir=tmp_path / "sessions",
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="AMR in ICU",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        assert result.generation_audit is not None
        assert result.generation_audit.input_mode == CriteriaInputMode.TOPIC
        assert "mock-wizard" in result.generation_audit.models_used
        assert result.generation_audit.consensus_method == "single_model"


class TestWizardSessionContinuity:
    """Tests for session ID reuse across saves."""

    @pytest.mark.asyncio
    async def test_single_session_file(self, tmp_path: Path) -> None:
        """Wizard should create only one session file (same ID for both saves)."""
        gen_adapter = _make_mock_adapter()
        detector_adapter = _make_detector_adapter()
        sessions_dir = tmp_path / "sessions"

        async def mock_ask(q: str) -> str:
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
            sessions_dir=sessions_dir,
        )

        await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="test topic",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        # Should have exactly 1 session file (same ID reused)
        session_files = list(sessions_dir.glob("*.json"))
        assert len(session_files) == 1


class TestSmartRefinementGlobalIssues:
    """Tests for smart refinement reporting global validation issues."""

    @pytest.mark.asyncio
    async def test_global_issues_shown_to_user(self, tmp_path: Path) -> None:
        """Global validation issues (element=None) should be shown via show_status."""
        # Create criteria that trigger "too broad" (global) and overlap (element)
        gen_adapter = MockLLMAdapter(
            model_id="mock-wizard",
            response_json={
                "research_question": "Q",
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adults"],
                        "exclude": ["adults"],
                    },
                },
                "study_design_include": [],
                "study_design_exclude": [],
            },
        )
        detector_adapter = _make_detector_adapter()
        status_messages: list[str] = []

        async def mock_ask(q: str) -> str:
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
            sessions_dir=tmp_path / "sessions",
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="test",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        assert isinstance(result, ReviewCriteria)
        # Overlap auto-fix should have been applied
        assert "adults" not in result.elements["population"].exclude


class TestSmartRefinementOverlapAutoFix:
    """Tests for smart refinement overlap auto-fix."""

    @pytest.mark.asyncio
    async def test_overlap_auto_fixed(self, tmp_path: Path) -> None:
        """Include/exclude overlap should be auto-fixed by removing from exclude."""
        gen_adapter = MockLLMAdapter(
            model_id="mock-wizard",
            response_json={
                "research_question": "Q",
                "elements": {
                    "population": {
                        "name": "Population",
                        "include": ["adults", "elderly"],
                        "exclude": ["adults"],
                    },
                },
                "study_design_include": [],
                "study_design_exclude": [],
            },
        )
        detector_adapter = _make_detector_adapter()

        async def mock_ask(q: str) -> str:
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
            sessions_dir=tmp_path / "sessions",
        )

        result = await wizard.run(
            input_mode=CriteriaInputMode.TOPIC,
            wizard_mode=WizardMode.SMART,
            raw_input="test",
            ask_user=mock_ask,
            show_status=mock_status,
            confirm=mock_confirm,
        )

        pop = result.elements["population"]
        # Overlap term should be removed from exclude
        assert "adults" not in pop.exclude
        # Include list should be unchanged
        assert "adults" in pop.include
        assert "elderly" in pop.include
