"""Tests for degenerate input handling in HCN screener.

When all LLM backends error out (e.g. the 2026-04-08 OpenRouter 402 outage),
the screener must NOT silently fall back to the prevalence prior. It must
return a HUMAN_REVIEW / Tier 3 decision so downstream metrics correctly
reflect the absence of LLM signal.

These tests pin the contract that protects against the 'A3 Bayesian router
collapse' incident documented in BENCHMARK_DIAGNOSIS.md and the
project_a3_diagnosis memory.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from metascreener.config import (
    AggregationConfig,
    MetaScreenerConfig,
    RouterConfig,
)
from metascreener.core.enums import CriteriaFramework, Decision, Tier
from metascreener.core.models import ModelOutput, Record, ReviewCriteria


def _make_error_backend(model_id: str, error_msg: str) -> MagicMock:
    """Create a mock backend that always returns an error ModelOutput.

    This mirrors what `ParallelRunner._run_one_with_prompt` does on
    HTTP 402 / timeouts / parse failures: returns a ModelOutput with
    `decision=HUMAN_REVIEW`, `score=0.5`, `confidence=0.0`, `error=<msg>`.
    """
    backend = MagicMock()
    backend.model_id = model_id
    backend.model_version = "mock-error-1.0"

    async def mock_call(prompt: str, seed: int = 42) -> ModelOutput:
        return ModelOutput(
            model_id=model_id,
            decision=Decision.HUMAN_REVIEW,
            score=0.5,
            confidence=0.0,
            rationale=f"Mock error: {error_msg}",
            error=error_msg,
        )

    backend.call_with_prompt = AsyncMock(side_effect=mock_call)
    return backend


def _make_criteria() -> ReviewCriteria:
    return ReviewCriteria(framework=CriteriaFramework.PICO)


def _make_record() -> Record:
    return Record(title="Effect of intervention on outcome in adults")


# ── Bug #2 reproducer ──


@pytest.mark.asyncio
async def test_all_backends_error_v20_path_returns_human_review() -> None:
    """v2.0 (CCA) path: all errors must produce HUMAN_REVIEW + Tier 3.

    Reproduces the degraded fallback observed in Moran_2021/a0.json
    where final_score=0.5 and ensemble_confidence=0.0 for every record.
    """
    from metascreener.module1_screening.hcn_screener import HCNScreener

    backends = [
        _make_error_backend(f"m-{i}", "402 Payment Required") for i in range(4)
    ]
    screener = HCNScreener(backends=backends)

    result = await screener.screen_single(_make_record(), _make_criteria())

    # Decision must be HUMAN_REVIEW with Tier 3 — never auto-decided
    assert result.decision == Decision.HUMAN_REVIEW, (
        f"Expected HUMAN_REVIEW when all backends error, got {result.decision}"
    )
    assert result.tier == Tier.THREE, f"Expected Tier.THREE, got {result.tier}"
    assert result.models_called == 4
    # All model_outputs should be marked as errored
    assert all(o.error is not None for o in (result.model_outputs or []))


@pytest.mark.asyncio
async def test_all_backends_error_ds_bayesian_path_returns_human_review() -> None:
    """DS + Bayesian path: must NOT fall back to prevalence prior + INCLUDE.

    This is the core Bug #2 reproducer. Before the fix, this scenario
    yielded p_include == 0.03 (prevalence prior leak) and decision=INCLUDE
    via the Bayesian router's loss minimization (because c_hr > c_fp*(1-p)
    for any p, and 0.03 > 1/51).
    """
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene"),
        router=RouterConfig(method="bayesian"),
    )
    backends = [
        _make_error_backend(f"m-{i}", "402 Payment Required") for i in range(4)
    ]
    screener = HCNScreener(backends=backends, config=config)

    result = await screener.screen_single(_make_record(), _make_criteria())

    # Must NOT silently auto-decide INCLUDE/EXCLUDE
    assert result.decision == Decision.HUMAN_REVIEW, (
        f"Expected HUMAN_REVIEW when all backends error, got {result.decision}. "
        f"p_include={result.p_include}. The router collapsed to the prior."
    )
    assert result.tier == Tier.THREE
    # p_include should be None or explicitly marked as missing — NOT the prior
    # The exact contract: either None, or a sentinel (NaN, -1) — but NEVER
    # exactly equal to the prevalence prior (0.03 for "low").
    if result.p_include is not None:
        assert result.p_include != 0.03, (
            "p_include must not equal the prevalence prior — that would mean "
            "the DS aggregator silently returned the prior unchanged"
        )


@pytest.mark.asyncio
async def test_all_backends_error_ds_threshold_router_returns_human_review() -> None:
    """DS + threshold router: same Bug #2 contract applies.

    A2 in the corrupted benchmark used this path and produced p_include=0.03
    + decision=HUMAN_REVIEW (the threshold router happened to escalate).
    The threshold router escalation was accidental — we should not rely on it.
    Make the contract explicit.
    """
    from metascreener.module1_screening.hcn_screener import HCNScreener

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene"),
        router=RouterConfig(method="threshold"),
    )
    backends = [
        _make_error_backend(f"m-{i}", "Timeout") for i in range(4)
    ]
    screener = HCNScreener(backends=backends, config=config)

    result = await screener.screen_single(_make_record(), _make_criteria())

    assert result.decision == Decision.HUMAN_REVIEW
    assert result.tier == Tier.THREE


@pytest.mark.asyncio
async def test_majority_backends_error_still_screens() -> None:
    """When fewer than all backends error, the screener should still proceed.

    The fail-safe must trigger ONLY at n_errors == n_total. With a
    surviving minority, we keep the existing behavior (the threshold
    router has its own >50% error escalation, which is separate).
    """
    from metascreener.core.models import PICOAssessment
    from metascreener.module1_screening.hcn_screener import HCNScreener

    # 3 errored backends + 1 working backend
    err_backends = [
        _make_error_backend(f"m-err-{i}", "402") for i in range(3)
    ]

    working = MagicMock()
    working.model_id = "m-ok"
    working.model_version = "mock-1.0"

    async def mock_ok(prompt: str, seed: int = 42) -> ModelOutput:
        return ModelOutput(
            model_id="m-ok",
            decision=Decision.EXCLUDE,
            score=0.1,
            confidence=0.95,
            rationale="ok",
            element_assessment={
                "population": PICOAssessment(match=False, evidence="ev"),
            },
        )

    working.call_with_prompt = AsyncMock(side_effect=mock_ok)

    config = MetaScreenerConfig(
        aggregation=AggregationConfig(method="dawid_skene"),
        router=RouterConfig(method="bayesian"),
    )
    screener = HCNScreener(backends=[*err_backends, working], config=config)
    result = await screener.screen_single(_make_record(), _make_criteria())

    # Should NOT trigger the all-errors fail-safe; the screener still
    # has the surviving annotation. Threshold router or Bayesian router
    # may still escalate to HR for other reasons, but that's a separate
    # path. The contract here is just: it must complete without crashing,
    # and if it auto-decides, that decision must be informed by the
    # surviving model.
    assert result.models_called == 4
    # Must not crash
    assert result.decision in (
        Decision.INCLUDE,
        Decision.EXCLUDE,
        Decision.HUMAN_REVIEW,
    )
