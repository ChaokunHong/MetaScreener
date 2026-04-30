"""Tests for BayesianRouter uncertainty handling under production presets.

Pin the contract that the router must NOT auto-INCLUDE every borderline
record under the named presets (`high_recall`, `balanced`,
`high_throughput`). Before the fix, all three presets had `c_fp=1` and
`c_hr ∈ {3,5,10}`, which made the tie-break `r_hr ≤ r_inc` mathematically
impossible (since r_inc ≤ c_fp ≤ 1 < c_hr). HUMAN_REVIEW could only be
reached via the ECS safety valve, which only fires for low-p EXCLUDE
candidates — leaving "uncertain INCLUDE" with no escape hatch.

The fix introduces an uncertainty band: when the expected losses for
INCLUDE and EXCLUDE are too close (within `uncertainty_margin`), the
router defers to HUMAN_REVIEW regardless of which is technically lower.
This is the standard Chow rejection-rule pattern from Bayesian decision
theory under abstention.
"""
from __future__ import annotations

import pytest

from metascreener.core.enums import Decision
from metascreener.core.models_bayesian import LossMatrix
from metascreener.module1_screening.layer4.bayesian_router import BayesianRouter

PRESETS = ["high_recall", "balanced", "high_throughput"]


class TestUncertaintyBand:
    """Each preset must have a non-empty p_include band where HR is chosen."""

    @pytest.mark.parametrize("preset", PRESETS)
    def test_some_p_yields_human_review(self, preset: str) -> None:
        """For every preset, at least one p_include in [0, 1] must route to HR.

        With ecs_final=0.5 (moderate consensus), the ECS-modulated margin
        is non-trivial and should produce an HR zone around the loss
        indifference point.
        """
        router = BayesianRouter(LossMatrix.from_preset(preset))
        hr_ps = []
        for i in range(101):
            p = i / 100.0
            d = router.route(p_include=p, ecs_final=0.5, rule_overrides=[])
            if d.decision == Decision.HUMAN_REVIEW:
                hr_ps.append(p)
        assert hr_ps, (
            f"Preset {preset!r} never routed to HUMAN_REVIEW for any "
            f"p_include in [0, 1] with ecs_final=0.5."
        )

    @pytest.mark.parametrize("preset", PRESETS)
    def test_indifference_point_yields_human_review(self, preset: str) -> None:
        """At p* where r_inc == r_exc, the router has zero confidence and
        MUST defer to HUMAN_REVIEW.

        p* = c_fp / (c_fn + c_fp) is the maximum-uncertainty point under
        the asymmetric loss matrix.
        """
        loss = LossMatrix.from_preset(preset)
        p_star = loss.c_fp / (loss.c_fn + loss.c_fp)
        router = BayesianRouter(loss)
        # At moderate ECS (0.5), margin is non-trivial, so indifference → HR
        d = router.route(p_include=p_star, ecs_final=0.5, rule_overrides=[])
        assert d.decision == Decision.HUMAN_REVIEW, (
            f"Preset {preset!r} at indifference p_include={p_star:.4f}: "
            f"r_inc=r_exc, but router chose {d.decision}. Should be HR."
        )

    @pytest.mark.parametrize("preset", PRESETS)
    def test_high_confidence_include_still_works(self, preset: str) -> None:
        """A confident positive (p=0.95) must still auto-INCLUDE under Phase 2.

        Requires direction-aligned ECS (high) and high EAS for the gate.
        """
        router = BayesianRouter(LossMatrix.from_preset(preset))
        d = router.route(
            p_include=0.95, ecs_final=0.9, rule_overrides=[], eas_score=0.9,
        )
        assert d.decision == Decision.INCLUDE

    @pytest.mark.parametrize("preset", PRESETS)
    def test_high_confidence_exclude_still_works(self, preset: str) -> None:
        """A confident negative (p=0.001) must still auto-EXCLUDE under Phase 2.

        Phase 2 requires low ECS (direction-aligned) plus exclude_certainty_passes
        and high EAS.
        """
        router = BayesianRouter(LossMatrix.from_preset(preset))
        d = router.route(
            p_include=0.001, ecs_final=0.05, rule_overrides=[],
            eas_score=0.9, exclude_certainty_passes=True,
        )
        assert d.decision == Decision.EXCLUDE

    @pytest.mark.parametrize("preset", PRESETS)
    def test_just_past_indifference_is_still_uncertain(self, preset: str) -> None:
        """A p_include just slightly past the indifference point still falls
        inside the uncertainty band.

        Specifically, at the boundary of the band (loss_ratio = 1 - margin)
        the router should produce HR; only beyond the band should it commit.
        This is what makes the band a graceful transition rather than a
        cliff at p*.
        """
        loss = LossMatrix.from_preset(preset)
        router = BayesianRouter(loss)
        # Indifference: p_star = c_fp / (c_fn + c_fp). Move 10% closer to
        # the EXCLUDE side and verify the router still defers.
        p_star = loss.c_fp / (loss.c_fn + loss.c_fp)
        p_test = p_star * 0.95  # 5% lower than indifference
        # Use low ECS (0.2) so effective_margin = 0.10 * 0.8 = 0.08,
        # wide enough that the near-indifference point falls in HR zone.
        d = router.route(p_include=p_test, ecs_final=0.2, rule_overrides=[])
        r_inc = loss.c_fp * (1.0 - p_test)
        r_exc = loss.c_fn * p_test
        ratio = min(r_inc, r_exc) / max(r_inc, r_exc)
        # Effective margin with ECS=0.2: base_margin * (1-0.2) = 0.08
        effective_margin = router.uncertainty_margin * (1.0 - 0.2)
        assert ratio >= (1.0 - effective_margin), (
            f"Sanity check: ratio={ratio:.4f} should be >= "
            f"{1.0 - effective_margin:.4f}"
        )
        assert d.decision == Decision.HUMAN_REVIEW, (
            f"Preset {preset!r} at p={p_test:.4f} (95% of indifference): "
            f"r_inc={r_inc:.4f}, r_exc={r_exc:.4f}, ratio={ratio:.4f}, "
            f"router chose {d.decision}. Should be HR (within uncertainty band)."
        )

    def test_real_p_include_low_still_yields_include_by_loss_matrix(self) -> None:
        """Document the contract boundary between Bug #2 and Bug #3.

        The 2026-04-08 failure mode (p_include == 0.03 because all LLMs
        errored) is NOT defended by the router — that protection lives
        in `HCNScreener.screen_single` Step 1b (the all-errors fail-safe,
        Bug #2). This router test only documents that, given a REAL
        p_include of 0.03 from valid LLM signal, the balanced preset's
        asymmetric loss DOES correctly pick INCLUDE (because c_fn=50× c_fp).

        At margin=0.30 (empirically best across 12 datasets, see the
        docstring on DEFAULT_UNCERTAINTY_MARGIN for why 0.40/0.50 were
        rejected), p=0.03 gives loss_ratio ≈ 0.647 which is below the
        threshold (1 - 0.30) = 0.70, so the router commits to INCLUDE.
        """
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        d = router.route(
            p_include=0.03, ecs_final=1.0, rule_overrides=[], eas_score=0.9,
        )
        assert d.decision == Decision.INCLUDE


class TestExistingContractsPreserved:
    """The new uncertainty band must NOT break the previously-passing tests."""

    def test_old_high_p_include_still_yields_include(self) -> None:
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        d = router.route(
            p_include=0.95, ecs_final=0.9, rule_overrides=[], eas_score=0.9,
        )
        assert d.decision == Decision.INCLUDE

    def test_old_low_p_include_still_yields_exclude(self) -> None:
        # Phase 2: need direction-aligned ECS (low) + excert + EAS.
        router = BayesianRouter(LossMatrix.from_preset("balanced"))
        d = router.route(
            p_include=0.001, ecs_final=0.05, rule_overrides=[],
            eas_score=0.9, exclude_certainty_passes=True,
        )
        assert d.decision == Decision.EXCLUDE

    def test_old_tie_break_still_favors_human_review(self) -> None:
        """When r_hr is the smallest of all three (custom symmetric matrix),
        the original tie-break path still produces HR."""
        router = BayesianRouter(LossMatrix(c_fn=2, c_fp=2, c_hr=1))
        d = router.route(p_include=0.5, ecs_final=0.9, rule_overrides=[])
        assert d.decision == Decision.HUMAN_REVIEW
