"""Integration tests for HCN v2.1 Bayesian pipeline feature switches."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.config import (
    AggregationConfig,
    ECSConfig,
    MetaCalibratorConfig,
    MetaScreenerConfig,
    RouterConfig,
)
from metascreener.core.enums import CriteriaFramework, Decision, ScreeningStage, Tier
from metascreener.core.models import (
    ECSResult,
    ElementConsensus,
    ModelOutput,
    PICOAssessment,
    Record,
    ReviewCriteria,
    RuleCheckResult,
    ScreeningDecision,
)


def _make_mock_backend(
    model_id: str, decision: str = "INCLUDE", score: float = 0.85
) -> MagicMock:
    """Create a mock LLM backend returning a fixed screening response."""
    backend = MagicMock()
    backend.model_id = model_id
    backend.model_version = "mock-1.0"

    async def mock_call(prompt: str, seed: int = 42) -> ModelOutput:
        return ModelOutput(
            model_id=model_id,
            decision=Decision(decision),
            score=score,
            confidence=0.9,
            rationale="Mock rationale",
            element_assessment={
                "population": PICOAssessment(match=True, evidence="ev"),
                "intervention": PICOAssessment(match=True, evidence="ev"),
            },
            prompt_hash="abc123",
        )

    backend.call_with_prompt = AsyncMock(side_effect=mock_call)
    return backend


def _make_criteria() -> ReviewCriteria:
    return ReviewCriteria(framework=CriteriaFramework.PICO)


def _make_record() -> Record:
    return Record(title="Effect of intervention on outcome in adults")


# ── Test 1: Default config → v2.0 path ──


@pytest.mark.asyncio
async def test_default_config_v20_path() -> None:
    """Default MetaScreenerConfig uses v2.0 CCA; p_include should be None."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends)

    result = await screener.screen_single(_make_record(), _make_criteria())

    assert result.p_include is None
    assert result.expected_loss is None
    assert result.sprt_early_stop is False
    assert result.requires_labelling is False
    assert result.decision in (
        Decision.INCLUDE,
        Decision.EXCLUDE,
        Decision.HUMAN_REVIEW,
    )
    assert 0.0 <= result.final_score <= 1.0
    assert len(result.model_outputs) == 4


@pytest.mark.asyncio
async def test_default_config_backward_compat() -> None:
    """Explicit config=None produces identical behavior to no config."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    backends_a = [_make_mock_backend(f"m-{i}") for i in range(4)]
    backends_b = [_make_mock_backend(f"m-{i}") for i in range(4)]

    screener_a = HCNScreener(backends=backends_a)
    screener_b = HCNScreener(backends=backends_b, config=None)

    record = _make_record()
    criteria = _make_criteria()

    result_a = await screener_a.screen_single(record, criteria, seed=42)
    result_b = await screener_b.screen_single(record, criteria, seed=42)

    assert result_a.decision == result_b.decision
    assert result_a.tier == result_b.tier
    assert result_a.final_score == pytest.approx(result_b.final_score, abs=1e-6)


# ── Test 2: DS + threshold router ──


@pytest.mark.asyncio
async def test_ds_with_threshold_router() -> None:
    """DS aggregation + threshold router: p_include set, expected_loss None."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene"),
        router=RouterConfig(method="threshold"),
    )
    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends, config=config)

    result = await screener.screen_single(_make_record(), _make_criteria())

    assert result.p_include is not None
    assert 0.0 <= result.p_include <= 1.0
    assert result.expected_loss is None
    assert result.models_called == 4


# ── Test 3: DS + bayesian router ──


@pytest.mark.asyncio
async def test_ds_with_bayesian_router() -> None:
    """DS aggregation + Bayesian router: both p_include and expected_loss set."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene"),
        router=RouterConfig(method="bayesian"),
    )
    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends, config=config)

    result = await screener.screen_single(_make_record(), _make_criteria())

    assert result.p_include is not None
    assert result.expected_loss is not None
    assert "include" in result.expected_loss
    assert "exclude" in result.expected_loss
    assert "human_review" in result.expected_loss


# ── Test 4: Geometric ECS dispatch ──


@pytest.mark.asyncio
async def test_geometric_ecs_dispatch() -> None:
    """Geometric ECS method should be selected when configured."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        ecs=ECSConfig(method="geometric"),
    )
    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends, config=config)

    result = await screener.screen_single(_make_record(), _make_criteria())

    # Should complete without error; ECS uses geometric path
    assert result.ecs_result is not None
    assert result.p_include is None  # still v2.0 aggregation


# ── Test 5: Bayesian screener attributes ──


def test_bayesian_screener_has_ds_attribute() -> None:
    """DS config should create self.ds on the screener."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene"),
    )
    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends, config=config)

    assert hasattr(screener, "ds")
    assert screener._use_bayesian is True
    assert screener._use_glad is False


def test_glad_config_creates_glad_attribute() -> None:
    """GLAD config should create both self.ds and self.glad."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="glad"),
    )
    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends, config=config)

    assert hasattr(screener, "ds")
    assert hasattr(screener, "glad")
    assert screener._use_bayesian is True


def test_bayesian_router_config() -> None:
    """Bayesian router config should create self.bayesian_router."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        router=RouterConfig(method="bayesian"),
    )
    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends, config=config)

    assert hasattr(screener, "bayesian_router")


def test_meta_calibrator_config_is_runtime_noop() -> None:
    """Meta-calibrator config is retained for experiments, not runtime wiring."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene"),
        meta_calibrator=MetaCalibratorConfig(enabled=True),
        router=RouterConfig(method="bayesian"),
    )
    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends, config=config)

    assert not hasattr(screener, "meta_calibrator")


def test_default_config_no_bayesian_attributes() -> None:
    """Default config should not create Bayesian attributes."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends)

    assert screener._use_bayesian is False
    assert not hasattr(screener, "ds")
    assert not hasattr(screener, "glad")
    assert not hasattr(screener, "bayesian_router")
    assert not hasattr(screener, "sprt")


# ── Test 6: incorporate_feedback no-op on v2.0 ──


def test_incorporate_feedback_noop_on_v20() -> None:
    """incorporate_feedback should be a no-op when not using Bayesian."""
    from metascreener.core.enums import Tier
    from metascreener.core.models import ScreeningDecision
    from metascreener.module1_screening.hcn_screener import HCNScreener

    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends)

    dummy_decision = ScreeningDecision(
        record_id="r1",
        decision=Decision.INCLUDE,
        tier=Tier.ONE,
        final_score=0.8,
        ensemble_confidence=0.9,
        model_outputs=[],
    )
    # Should not raise
    screener.incorporate_feedback("r1", 0, dummy_decision)
    assert screener._labelled_buffer == []


# ── Test 7: Mixed include/exclude with DS ──


@pytest.mark.asyncio
async def test_ds_mixed_decisions() -> None:
    """DS with mixed INCLUDE/EXCLUDE outputs should still produce valid results."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene"),
        router=RouterConfig(method="bayesian"),
    )
    backends = [
        _make_mock_backend("m-0", decision="INCLUDE"),
        _make_mock_backend("m-1", decision="INCLUDE"),
        _make_mock_backend("m-2", decision="EXCLUDE"),
        _make_mock_backend("m-3", decision="EXCLUDE"),
    ]
    screener = HCNScreener(backends=backends, config=config)

    result = await screener.screen_single(_make_record(), _make_criteria())

    assert result.p_include is not None
    assert 0.0 <= result.p_include <= 1.0
    assert result.expected_loss is not None


@pytest.mark.asyncio
async def test_meta_calibrator_falls_back_before_fit() -> None:
    """Runtime routing should stay on raw p_include even if config enables it."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene"),
        meta_calibrator=MetaCalibratorConfig(enabled=True, min_samples=5),
        router=RouterConfig(method="bayesian"),
    )
    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends, config=config)

    result = await screener.screen_single(_make_record(), _make_criteria())

    assert result.p_include is not None
    assert result.q_include is None
    assert result.final_score == pytest.approx(result.p_include)


def test_incorporate_feedback_ignores_meta_calibrator_config() -> None:
    """Batch feedback should not add meta-calibrator state to runtime."""
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene", batch_update_size=2),
        meta_calibrator=MetaCalibratorConfig(enabled=True, min_samples=2),
        router=RouterConfig(method="bayesian"),
    )
    backends = [_make_mock_backend(f"m-{i}") for i in range(4)]
    screener = HCNScreener(backends=backends, config=config)

    def make_decision(record_id: str, p_include: float, decision_votes: list[Decision]) -> ScreeningDecision:
        model_outputs = [
            ModelOutput(
                model_id=f"m-{idx}",
                decision=vote,
                score=0.9 if vote == Decision.INCLUDE else 0.1,
                confidence=0.9,
                rationale="mock",
                element_assessment={
                    "population": PICOAssessment(
                        match=vote == Decision.INCLUDE,
                        evidence="ev",
                    )
                },
                parse_quality=1.0,
            )
            for idx, vote in enumerate(decision_votes)
        ]
        n_include = sum(1 for vote in decision_votes if vote == Decision.INCLUDE)
        n_exclude = len(decision_votes) - n_include
        return ScreeningDecision(
            record_id=record_id,
            stage=ScreeningStage.TITLE_ABSTRACT,
            decision=Decision.INCLUDE,
            tier=Tier.ONE,
            final_score=p_include,
            ensemble_confidence=0.9,
            model_outputs=model_outputs,
            rule_result=RuleCheckResult(),
            element_consensus={
                "population": ElementConsensus(
                    name="Population",
                    required=True,
                    exclusion_relevant=True,
                    n_match=n_include,
                    n_mismatch=n_exclude,
                    n_unclear=0,
                    support_ratio=n_include / max(n_include + n_exclude, 1),
                )
            },
            ecs_result=ECSResult(
                score=0.9 if p_include > 0.5 else 0.1,
                eas_score=1.0,
            ),
            p_include=p_include,
            q_include=p_include,
            esas_score=0.4,
            glad_difficulty=1.0,
            sprt_early_stop=True,
            models_called=2,
            ipw_weight=1.0,
        )

    screener.incorporate_feedback(
        "r-pos",
        0,
        make_decision("r-pos", 0.9, [Decision.INCLUDE, Decision.INCLUDE]),
    )
    screener.incorporate_feedback(
        "r-neg",
        1,
        make_decision("r-neg", 0.05, [Decision.EXCLUDE, Decision.EXCLUDE]),
    )

    assert not hasattr(screener, "meta_calibrator")
    assert all("meta_features" not in row for row in screener._labelled_buffer)
