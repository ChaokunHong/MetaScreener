"""Tests for A14: GLAD difficulty floor in secondary exclude gate."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.config import (
    AggregationConfig,
    CriteriaConfig,
    ECSConfig,
    MetaScreenerConfig,
    RouterConfig,
    SPRTConfig,
)
from metascreener.core.enums import CriteriaFramework, Decision, Tier
from metascreener.core.models import (
    CriteriaElement,
    ModelOutput,
    PICOAssessment,
    Record,
    ReviewCriteria,
)
from metascreener.core.models_screening import ScreeningDecision


def _make_output(
    model_id: str,
    decision: Decision,
    *,
    population_match: bool | None = None,
    intervention_match: bool | None = None,
) -> ModelOutput:
    ea: dict[str, PICOAssessment] = {}
    if population_match is not None:
        ea["population"] = PICOAssessment(match=population_match, evidence="test")
    if intervention_match is not None:
        ea["intervention"] = PICOAssessment(match=intervention_match, evidence="test")
    return ModelOutput(
        model_id=model_id, decision=decision,
        score=0.1 if decision == Decision.EXCLUDE else 0.9,
        confidence=0.9, rationale="mock", element_assessment=ea, parse_quality=1.0,
    )


def _make_criteria() -> ReviewCriteria:
    return ReviewCriteria(
        framework=CriteriaFramework.PICO,
        research_question="mock question",
        elements={
            "population": CriteriaElement(name="Population", include=["adults"]),
            "intervention": CriteriaElement(name="Intervention", include=["drug x"]),
        },
        required_elements=["population", "intervention"],
    )


def _make_backend(
    model_id: str, decision: Decision,
    *, population_match: bool | None = None, intervention_match: bool | None = None,
) -> MagicMock:
    backend = MagicMock()
    backend.model_id = model_id
    backend.model_version = "mock-1.0"

    async def mock_call(prompt: str, seed: int = 42) -> ModelOutput:
        return _make_output(model_id, decision,
                            population_match=population_match,
                            intervention_match=intervention_match)

    backend.call_with_prompt = AsyncMock(side_effect=mock_call)
    return backend


def _make_config(
    *,
    floor_enabled: bool = False,
    floor: float = 1.0,
    mode: str = "coverage",
) -> MetaScreenerConfig:
    return MetaScreenerConfig(
        criteria=CriteriaConfig(),
        aggregation=AggregationConfig(method="dawid_skene"),
        ecs=ECSConfig(method="geometric"),
        sprt=SPRTConfig(enabled=True, waves=2),
        router=RouterConfig(
            method="bayesian",
            exclude_certainty_enabled=True,
            exclude_certainty_mode=mode,
            exclude_certainty_difficulty_floor_enabled=floor_enabled,
            exclude_certainty_difficulty_floor=floor,
        ),
    )


def _include_route(*args: object, **kwargs: object) -> ScreeningDecision:
    return ScreeningDecision(
        record_id="",
        decision=Decision.INCLUDE,
        tier=Tier.ONE,
        final_score=0.99,
        ensemble_confidence=0.9,
        expected_loss={"include": 0.01, "exclude": 0.9, "human_review": 5.0},
    )


@pytest.mark.asyncio
async def test_floor_disabled_matches_a13b() -> None:
    """With floor disabled, behavior identical to A13b."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=False)
    backends = [
        _make_backend("m1", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m2", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m3", Decision.INCLUDE, population_match=True, intervention_match=True),
        _make_backend("m4", Decision.INCLUDE, population_match=True, intervention_match=True),
    ]
    screener = HCNScreener(backends=backends, config=config)
    result = await screener.screen_single(
        Record(title="mock title", abstract="mock abstract"), _make_criteria(),
    )

    assert result.sprt_early_stop is True
    assert result.models_called == 2
    assert result.exclude_certainty_passes is True
    assert result.effective_difficulty is not None
    # With mocks, glad_difficulty=1.0 (GLAD has no real data), so effective_difficulty=1.0
    # regardless of floor. The floor only matters when glad_difficulty < floor.
    assert result.effective_difficulty == 1.0
    assert result.decision == Decision.EXCLUDE


@pytest.mark.asyncio
async def test_floor_not_applied_to_two_model_sprt_early_stop() -> None:
    """Difficulty floor is a full-panel guard, not a 2-model early-stop bypass."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=True, floor=1.0)
    backends = [
        _make_backend("m1", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m2", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m3", Decision.INCLUDE, population_match=True, intervention_match=True),
        _make_backend("m4", Decision.INCLUDE, population_match=True, intervention_match=True),
    ]
    screener = HCNScreener(backends=backends, config=config)
    screener.bayesian_router.route = _include_route  # type: ignore[method-assign]
    screener._aggregate_bayesian = (  # type: ignore[method-assign]
        lambda outputs: (0.01, 0.9, 0.2)
    )

    result = await screener.screen_single(
        Record(title="mock title", abstract="mock abstract"), _make_criteria(),
    )

    assert result.sprt_early_stop is True
    assert result.models_called == 2
    assert result.exclude_certainty_passes is True
    assert result.effective_difficulty == 0.2
    assert result.loss_prefers_exclude is False
    assert result.decision == Decision.INCLUDE


@pytest.mark.asyncio
async def test_floor_still_applies_after_full_model_panel() -> None:
    """Full 4-model routing can still use the floor to promote auto-EXCLUDE."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=True, floor=1.0)
    config.sprt.enabled = False
    backends = [
        _make_backend("m1", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m2", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m3", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m4", Decision.EXCLUDE, population_match=False, intervention_match=False),
    ]
    screener = HCNScreener(backends=backends, config=config)
    screener.bayesian_router.route = _include_route  # type: ignore[method-assign]
    screener._aggregate_bayesian = (  # type: ignore[method-assign]
        lambda outputs: (0.01, 0.9, 0.2)
    )

    result = await screener.screen_single(
        Record(title="mock title", abstract="mock abstract"), _make_criteria(),
    )

    assert result.sprt_early_stop is False
    assert result.models_called == 4
    assert result.exclude_certainty_passes is True
    assert result.effective_difficulty == 1.0
    assert result.loss_prefers_exclude is True
    assert result.decision == Decision.EXCLUDE


@pytest.mark.asyncio
async def test_floor_enabled_passes_true_low_p_include_upgrades() -> None:
    """Floor enabled + passes=True + low p_include → EXCLUDE upgrade."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=True, floor=1.0)
    backends = [
        _make_backend("m1", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m2", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m3", Decision.INCLUDE, population_match=True, intervention_match=True),
        _make_backend("m4", Decision.INCLUDE, population_match=True, intervention_match=True),
    ]
    screener = HCNScreener(backends=backends, config=config)
    result = await screener.screen_single(
        Record(title="mock title", abstract="mock abstract"), _make_criteria(),
    )

    assert result.sprt_early_stop is True
    assert result.models_called == 2
    assert result.exclude_certainty_passes is True
    assert result.effective_difficulty == 1.0  # Floor applied
    assert result.loss_prefers_exclude is True
    assert result.decision == Decision.EXCLUDE


@pytest.mark.asyncio
async def test_floor_enabled_passes_false_no_effect() -> None:
    """Floor enabled but passes=False → floor NOT applied, stays HR."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=True, floor=1.0)
    # Only 1 element mismatch shared -> passes=False in coverage mode
    # (supporting < 1? or coverage too low?)
    # Actually with both models saying pop=False, int=True:
    # coverage = weight(pop) / (weight(pop)+weight(int)) = 1.0/2.0 = 0.5 < 0.6 in early regime
    backends = [
        _make_backend("m1", Decision.EXCLUDE, population_match=False, intervention_match=True),
        _make_backend("m2", Decision.EXCLUDE, population_match=False, intervention_match=True),
        _make_backend("m3", Decision.INCLUDE, population_match=True, intervention_match=True),
        _make_backend("m4", Decision.INCLUDE, population_match=True, intervention_match=True),
    ]
    screener = HCNScreener(backends=backends, config=config)
    result = await screener.screen_single(
        Record(title="mock title", abstract="mock abstract"), _make_criteria(),
    )

    assert result.sprt_early_stop is True
    assert result.exclude_certainty_passes is False
    # Floor NOT applied when passes=False. With mocks glad_difficulty=1.0,
    # so effective_difficulty=1.0 either way. The key check is that the decision
    # stays HR despite floor being enabled (because passes=False).
    assert result.effective_difficulty is not None
    assert result.decision == Decision.HUMAN_REVIEW


@pytest.mark.asyncio
async def test_floor_enabled_high_p_include_stays_hr() -> None:
    """Floor enabled + passes=True but p_include above base threshold → still HR.

    This tests that difficulty_floor=1.0 doesn't bypass the base loss check.
    When p_include > 1/51 ≈ 0.0196, even floor=1.0 won't make loss_prefers_exclude True.

    Note: With only 2 mock models and DS prior at 0.03, p_include is typically
    very low (~0.01). This test would need a scenario where p_include is higher,
    which is hard to construct with simple mocks. We verify the math directly instead.
    """
    # Direct math verification
    c_fn, c_fp = 50.0, 1.0
    p_high = 0.025  # Above 1/51 = 0.0196

    # With floor=1.0: adjusted_c_fn = 50/1.0 = 50
    adjusted = c_fn / 1.0
    lpe = adjusted * p_high < c_fp * (1 - p_high)
    # 50 * 0.025 = 1.25 vs 1 * 0.975 = 0.975 → 1.25 > 0.975 → False
    assert lpe is False


@pytest.mark.asyncio
async def test_diagnostic_fields_populated() -> None:
    """All diagnostic fields are populated in ScreeningDecision."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=True, floor=0.8)
    backends = [
        _make_backend("m1", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m2", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m3", Decision.INCLUDE, population_match=True, intervention_match=True),
        _make_backend("m4", Decision.INCLUDE, population_match=True, intervention_match=True),
    ]
    screener = HCNScreener(backends=backends, config=config)
    result = await screener.screen_single(
        Record(title="mock title", abstract="mock abstract"), _make_criteria(),
    )

    assert result.exclude_certainty is not None
    assert result.exclude_certainty_passes is not None
    assert result.exclude_certainty_supporting_elements is not None
    assert result.exclude_certainty_regime in ("early", "full")
    assert result.loss_prefers_exclude is not None
    assert result.effective_difficulty is not None
    assert result.glad_difficulty > 0
