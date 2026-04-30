"""Phase 2.5 integration safety: post-route override never bypasses HR.

Codex audit (2026-04-27) flagged that the legacy post-route logic in
``HCNScreener.screen_single`` could promote a router-issued HUMAN_REVIEW
back to auto-EXCLUDE when ``exclude_certainty_passes`` was True.  That
defeats the new Phase 2 directional gates: when the router returns HR
because of low EAS / 2-model SPRT under the stricter EAS threshold /
ECS-direction conflict, the system must respect that decision end to
end.

This module tests the contract directly by mocking the router to emit
HUMAN_REVIEW and confirming the integrated screener does not flip it.
"""
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
    population_match: bool | None = False,
    intervention_match: bool | None = False,
) -> ModelOutput:
    ea: dict[str, PICOAssessment] = {}
    if population_match is not None:
        ea["population"] = PICOAssessment(match=population_match, evidence="test")
    if intervention_match is not None:
        ea["intervention"] = PICOAssessment(
            match=intervention_match, evidence="test",
        )
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=0.1 if decision == Decision.EXCLUDE else 0.9,
        confidence=0.9,
        rationale="mock",
        element_assessment=ea,
        parse_quality=1.0,
    )


def _make_backend(
    model_id: str,
    decision: Decision = Decision.EXCLUDE,
    *,
    population_match: bool | None = False,
    intervention_match: bool | None = False,
) -> MagicMock:
    backend = MagicMock()
    backend.model_id = model_id
    backend.model_version = "mock-1.0"

    async def mock_call(prompt: str, seed: int = 42) -> ModelOutput:
        return _make_output(
            model_id, decision,
            population_match=population_match,
            intervention_match=intervention_match,
        )

    backend.call_with_prompt = AsyncMock(side_effect=mock_call)
    return backend


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


def _make_config(
    *, floor_enabled: bool = True, ec_loss_override: bool = True,
) -> MetaScreenerConfig:
    return MetaScreenerConfig(
        criteria=CriteriaConfig(),
        aggregation=AggregationConfig(method="dawid_skene"),
        ecs=ECSConfig(method="geometric"),
        sprt=SPRTConfig(enabled=True, waves=2),
        router=RouterConfig(
            method="bayesian",
            exclude_certainty_enabled=True,
            exclude_certainty_mode="coverage",
            exclude_certainty_difficulty_floor_enabled=floor_enabled,
            exclude_certainty_difficulty_floor=1.0,
            exclude_certainty_loss_override=ec_loss_override,
        ),
    )


@pytest.mark.asyncio
async def test_router_hr_is_not_promoted_to_exclude_by_loss_path() -> None:
    """Router emits HR; loss_prefers_exclude=True path must not flip it."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=False, ec_loss_override=False)
    backends = [
        _make_backend("m1", Decision.EXCLUDE),
        _make_backend("m2", Decision.EXCLUDE),
        _make_backend("m3", Decision.EXCLUDE),
        _make_backend("m4", Decision.EXCLUDE),
    ]
    screener = HCNScreener(backends=backends, config=config)

    # Replace the router so route() always returns HR (Tier 3) regardless
    # of inputs. Mirrors a Phase 2 router that vetoed the auto-decision
    # because of low EAS or 2-model SPRT under the stricter EAS gate.
    def _hr_route(*args: object, **kwargs: object) -> ScreeningDecision:
        return ScreeningDecision(
            record_id="",
            decision=Decision.HUMAN_REVIEW,
            tier=Tier.THREE,
            final_score=0.001,
            ensemble_confidence=1.0,
            expected_loss={"include": 0.999, "exclude": 0.05, "human_review": 0.5},
        )

    screener.bayesian_router.route = _hr_route  # type: ignore[method-assign]

    result = await screener.screen_single(
        Record(title="mock", abstract="mock"), _make_criteria(),
    )

    assert result.decision == Decision.HUMAN_REVIEW, (
        "Router said HR; loss_prefers_exclude must not promote to EXCLUDE."
    )
    assert result.tier == Tier.THREE


@pytest.mark.asyncio
async def test_router_hr_is_not_promoted_to_exclude_by_ec_override_flag() -> None:
    """Router emits HR; even with exclude_certainty_loss_override=True
    enabled, the override must not bypass HR."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=False, ec_loss_override=True)
    backends = [
        _make_backend("m1", Decision.EXCLUDE),
        _make_backend("m2", Decision.EXCLUDE),
        _make_backend("m3", Decision.EXCLUDE),
        _make_backend("m4", Decision.EXCLUDE),
    ]
    screener = HCNScreener(backends=backends, config=config)

    def _hr_route(*args: object, **kwargs: object) -> ScreeningDecision:
        return ScreeningDecision(
            record_id="",
            decision=Decision.HUMAN_REVIEW,
            tier=Tier.THREE,
            final_score=0.001,
            ensemble_confidence=1.0,
            expected_loss={"include": 0.999, "exclude": 0.05, "human_review": 0.5},
        )

    screener.bayesian_router.route = _hr_route  # type: ignore[method-assign]

    result = await screener.screen_single(
        Record(title="mock", abstract="mock"), _make_criteria(),
    )

    assert result.decision == Decision.HUMAN_REVIEW
    assert result.tier == Tier.THREE


@pytest.mark.asyncio
async def test_router_hr_is_not_promoted_to_exclude_by_difficulty_floor() -> None:
    """Router emits HR; difficulty_floor + passes=True must not bypass HR."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=True, ec_loss_override=False)
    backends = [
        _make_backend("m1", Decision.EXCLUDE),
        _make_backend("m2", Decision.EXCLUDE),
        _make_backend("m3", Decision.EXCLUDE),
        _make_backend("m4", Decision.EXCLUDE),
    ]
    screener = HCNScreener(backends=backends, config=config)

    def _hr_route(*args: object, **kwargs: object) -> ScreeningDecision:
        return ScreeningDecision(
            record_id="",
            decision=Decision.HUMAN_REVIEW,
            tier=Tier.THREE,
            final_score=0.001,
            ensemble_confidence=1.0,
            expected_loss={"include": 0.999, "exclude": 0.05, "human_review": 0.5},
        )

    screener.bayesian_router.route = _hr_route  # type: ignore[method-assign]

    result = await screener.screen_single(
        Record(title="mock", abstract="mock"), _make_criteria(),
    )

    assert result.decision == Decision.HUMAN_REVIEW, (
        "Phase 2 contract: router-issued HR cannot be promoted to EXCLUDE "
        "by the difficulty-floor / loss-override / exclude-certainty path."
    )


@pytest.mark.asyncio
async def test_router_committed_exclude_still_allowed_through() -> None:
    """Sanity check: when router returns auto-EXCLUDE the override is allowed
    to refine tier (the legacy promote-to-Tier-2 behaviour)."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = _make_config(floor_enabled=False, ec_loss_override=False)
    backends = [
        _make_backend("m1", Decision.EXCLUDE),
        _make_backend("m2", Decision.EXCLUDE),
        _make_backend("m3", Decision.EXCLUDE),
        _make_backend("m4", Decision.EXCLUDE),
    ]
    screener = HCNScreener(backends=backends, config=config)

    def _exclude_route(*args: object, **kwargs: object) -> ScreeningDecision:
        return ScreeningDecision(
            record_id="",
            decision=Decision.EXCLUDE,
            tier=Tier.TWO,
            final_score=0.001,
            ensemble_confidence=1.0,
            expected_loss={"include": 0.999, "exclude": 0.05, "human_review": 0.5},
        )

    screener.bayesian_router.route = _exclude_route  # type: ignore[method-assign]

    result = await screener.screen_single(
        Record(title="mock", abstract="mock"), _make_criteria(),
    )

    # Router said EXCLUDE → integrated screener still EXCLUDE
    assert result.decision == Decision.EXCLUDE
