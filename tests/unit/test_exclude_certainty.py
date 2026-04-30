"""Tests for rule-based EXCLUDE certification."""

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
from metascreener.core.enums import CriteriaFramework, Decision
from metascreener.core.models import (
    CriteriaElement,
    ModelOutput,
    PICOAssessment,
    Record,
    ReviewCriteria,
)
from metascreener.module1_screening.layer4.exclude_certainty import (
    compute_exclude_certainty,
)


def _make_output(
    model_id: str,
    decision: Decision,
    *,
    population_match: bool | None = None,
    intervention_match: bool | None = None,
) -> ModelOutput:
    element_assessment: dict[str, PICOAssessment] = {}
    if population_match is not None:
        element_assessment["population"] = PICOAssessment(
            match=population_match,
            evidence="population evidence",
        )
    if intervention_match is not None:
        element_assessment["intervention"] = PICOAssessment(
            match=intervention_match,
            evidence="intervention evidence",
        )
    return ModelOutput(
        model_id=model_id,
        decision=decision,
        score=0.1 if decision == Decision.EXCLUDE else 0.9,
        confidence=0.9,
        rationale="mock",
        element_assessment=element_assessment,
        parse_quality=1.0,
    )


def _make_criteria() -> ReviewCriteria:
    return ReviewCriteria(
        framework=CriteriaFramework.PICO,
        research_question="mock question",
        elements={
            "population": CriteriaElement(name="Population", include=["adults"]),
            "intervention": CriteriaElement(
                name="Intervention", include=["drug x"]
            ),
        },
        required_elements=["population", "intervention"],
    )


def _make_backend(
    model_id: str,
    decision: Decision,
    *,
    population_match: bool | None = None,
    intervention_match: bool | None = None,
) -> MagicMock:
    backend = MagicMock()
    backend.model_id = model_id
    backend.model_version = "mock-1.0"

    async def mock_call(prompt: str, seed: int = 42) -> ModelOutput:
        return _make_output(
            model_id,
            decision,
            population_match=population_match,
            intervention_match=intervention_match,
        )

    backend.call_with_prompt = AsyncMock(side_effect=mock_call)
    return backend


def test_early_regime_requires_two_supporting_elements() -> None:
    from metascreener.module1_screening.layer3.element_consensus import (
        build_element_consensus,
    )

    outputs = [
        _make_output("m1", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_output("m2", Decision.EXCLUDE, population_match=False, intervention_match=True),
    ]
    consensus = build_element_consensus(_make_criteria(), outputs)

    result = compute_exclude_certainty(
        outputs,
        consensus,
        sprt_early_stop=True,
        models_called=2,
    )

    assert result.vote_unanimous_exclude is True
    assert result.supporting_elements == 1
    assert result.regime == "early"
    assert result.passes is False


def test_full_regime_passes_single_strong_exclusion_element() -> None:
    from metascreener.module1_screening.layer3.element_consensus import (
        build_element_consensus,
    )

    outputs = [
        _make_output("m1", Decision.EXCLUDE, population_match=False, intervention_match=True),
        _make_output("m2", Decision.EXCLUDE, population_match=False, intervention_match=True),
        _make_output("m3", Decision.EXCLUDE, population_match=False, intervention_match=True),
        _make_output("m4", Decision.EXCLUDE, population_match=False, intervention_match=True),
    ]
    consensus = build_element_consensus(_make_criteria(), outputs)

    result = compute_exclude_certainty(
        outputs,
        consensus,
        sprt_early_stop=False,
        models_called=4,
    )

    assert result.vote_unanimous_exclude is True
    assert result.supporting_elements == 1
    assert result.regime == "full"
    assert result.score == pytest.approx(1.0)
    assert result.passes is True


@pytest.mark.asyncio
async def test_hcn_upgrades_early_exclude_with_two_supporting_elements() -> None:
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        criteria=CriteriaConfig(),
        aggregation=AggregationConfig(method="dawid_skene"),
        ecs=ECSConfig(method="geometric"),
        sprt=SPRTConfig(enabled=True, waves=2),
        router=RouterConfig(
            method="bayesian",
            exclude_certainty_enabled=True,
        ),
    )
    backends = [
        _make_backend("m1", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m2", Decision.EXCLUDE, population_match=False, intervention_match=False),
        _make_backend("m3", Decision.INCLUDE, population_match=True, intervention_match=True),
        _make_backend("m4", Decision.INCLUDE, population_match=True, intervention_match=True),
    ]
    screener = HCNScreener(backends=backends, config=config)

    result = await screener.screen_single(
        Record(title="mock title", abstract="mock abstract"),
        _make_criteria(),
    )

    assert result.sprt_early_stop is True
    assert result.models_called == 2
    assert result.exclude_certainty == pytest.approx(1.0)
    assert result.decision == Decision.EXCLUDE


@pytest.mark.asyncio
async def test_hcn_keeps_hr_when_early_exclude_has_one_supporting_element() -> None:
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        criteria=CriteriaConfig(),
        aggregation=AggregationConfig(method="dawid_skene"),
        ecs=ECSConfig(method="geometric"),
        sprt=SPRTConfig(enabled=True, waves=2),
        router=RouterConfig(
            method="bayesian",
            exclude_certainty_enabled=True,
        ),
    )
    backends = [
        _make_backend("m1", Decision.EXCLUDE, population_match=False, intervention_match=True),
        _make_backend("m2", Decision.EXCLUDE, population_match=False, intervention_match=True),
        _make_backend("m3", Decision.INCLUDE, population_match=True, intervention_match=True),
        _make_backend("m4", Decision.INCLUDE, population_match=True, intervention_match=True),
    ]
    screener = HCNScreener(backends=backends, config=config)

    result = await screener.screen_single(
        Record(title="mock title", abstract="mock abstract"),
        _make_criteria(),
    )

    assert result.sprt_early_stop is True
    assert result.models_called == 2
    assert result.exclude_certainty == pytest.approx(1.0)
    assert result.decision == Decision.HUMAN_REVIEW
