"""Phase 2 router gating semantics: clean separation of signals.

After Codex's math audit, the router must treat each signal as having a
single, well-defined role:

    * p_include              -> direction probability
    * ECS (ecs_final)        -> inclusion support  (high = supports INCLUDE)
    * EAS (eas_score)        -> direction-agnostic agreement
    * exclude_certainty_passes -> exclusion support gate

Routing contract:

    INCLUDE auto requires:  p_include high  AND ECS high           AND EAS high
    EXCLUDE auto requires:  p_include low   AND ECS low            AND EAS high
                            AND exclude_certainty_passes
    HUMAN_REVIEW otherwise (low agreement, conflicting signals, or risk
    budget exceeded).

In the 2-model SPRT early-stop regime, the EAS threshold is stricter and
exclude_certainty_passes alone is insufficient without high agreement.
"""
from __future__ import annotations

from metascreener.core.enums import Decision
from metascreener.core.models_bayesian import LossMatrix
from metascreener.module1_screening.layer4.bayesian_router import BayesianRouter


def _balanced_router() -> BayesianRouter:
    return BayesianRouter(LossMatrix.from_preset("balanced"))


# ---------------------------------------------------------------------------
# INCLUDE direction gate
# ---------------------------------------------------------------------------


class TestIncludeGate:
    def test_high_p_high_ecs_high_eas_yields_include(self) -> None:
        router = _balanced_router()
        decision = router.route(
            p_include=0.95,
            ecs_final=0.9,
            rule_overrides=[],
            eas_score=0.9,
        )
        assert decision.decision == Decision.INCLUDE

    def test_high_p_low_ecs_yields_human_review(self) -> None:
        """ECS low but p_include high = signal conflict -> HR.

        ECS low means element-level consensus is mismatch; p_include high
        means the calibrated probability favours inclusion. Disagreement
        between the two should not auto-decide.
        """
        router = _balanced_router()
        decision = router.route(
            p_include=0.95,
            ecs_final=0.10,
            rule_overrides=[],
            eas_score=0.9,
        )
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_high_p_high_ecs_low_eas_yields_human_review(self) -> None:
        """Even with directional alignment, low EAS forces HR."""
        router = _balanced_router()
        decision = router.route(
            p_include=0.95,
            ecs_final=0.9,
            rule_overrides=[],
            eas_score=0.2,
        )
        assert decision.decision == Decision.HUMAN_REVIEW


# ---------------------------------------------------------------------------
# EXCLUDE direction gate
# ---------------------------------------------------------------------------


class TestExcludeGate:
    def test_low_p_low_ecs_high_eas_excert_pass_yields_exclude(self) -> None:
        router = _balanced_router()
        decision = router.route(
            p_include=0.001,
            ecs_final=0.05,
            rule_overrides=[],
            eas_score=0.9,
            exclude_certainty_passes=True,
        )
        assert decision.decision == Decision.EXCLUDE

    def test_low_p_low_ecs_high_eas_no_excert_yields_human_review(self) -> None:
        """Low p_include + low ECS + high EAS but exclude_certainty fails -> HR.

        This is the central Phase 2 promise: weak exclusion evidence
        cannot auto-EXCLUDE even when other signals look clean.
        """
        router = _balanced_router()
        decision = router.route(
            p_include=0.001,
            ecs_final=0.05,
            rule_overrides=[],
            eas_score=0.9,
            exclude_certainty_passes=False,
        )
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_low_p_low_ecs_low_eas_yields_human_review(self) -> None:
        """Low EAS alone is enough to force HR even with exclude_certainty."""
        router = _balanced_router()
        decision = router.route(
            p_include=0.001,
            ecs_final=0.05,
            rule_overrides=[],
            eas_score=0.2,
            exclude_certainty_passes=True,
        )
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_low_p_high_ecs_yields_human_review(self) -> None:
        """ECS high but p_include low = conflict -> HR.

        The legacy behaviour of "low p_include + high ECS -> EXCLUDE" was
        the asymmetric ECS safety valve. Phase 2 retires that path: high
        ECS supports INCLUDE, so it must not enable auto-EXCLUDE.
        """
        router = _balanced_router()
        decision = router.route(
            p_include=0.001,
            ecs_final=0.9,
            rule_overrides=[],
            eas_score=0.9,
            exclude_certainty_passes=True,
        )
        assert decision.decision == Decision.HUMAN_REVIEW


# ---------------------------------------------------------------------------
# 2-model SPRT early-stop safety
# ---------------------------------------------------------------------------


class TestSprtTwoModelSafety:
    def test_two_model_low_eas_blocks_exclude_even_with_excert(self) -> None:
        """SPRT early-stop with only 2 model votes needs stricter EAS."""
        router = _balanced_router()
        decision = router.route(
            p_include=0.001,
            ecs_final=0.05,
            rule_overrides=[],
            eas_score=0.55,           # would be ok in full regime, weak in 2-model
            exclude_certainty_passes=True,
            models_called=2,
            sprt_early_stop=True,
        )
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_two_model_high_eas_with_excert_can_exclude(self) -> None:
        """If 2-model SPRT but EAS very high and exclude_certainty passes,
        auto-EXCLUDE is allowed."""
        router = _balanced_router()
        decision = router.route(
            p_include=0.001,
            ecs_final=0.05,
            rule_overrides=[],
            eas_score=0.95,
            exclude_certainty_passes=True,
            models_called=2,
            sprt_early_stop=True,
        )
        assert decision.decision == Decision.EXCLUDE

    def test_full_wave_relaxes_eas_threshold(self) -> None:
        """4-model wave allows the looser EAS threshold."""
        router = _balanced_router()
        decision = router.route(
            p_include=0.001,
            ecs_final=0.05,
            rule_overrides=[],
            eas_score=0.55,
            exclude_certainty_passes=True,
            models_called=4,
            sprt_early_stop=False,
        )
        assert decision.decision == Decision.EXCLUDE


# ---------------------------------------------------------------------------
# EAS-modulated margin (replaces ECS-modulated margin)
# ---------------------------------------------------------------------------


class TestEasModulatedMargin:
    def test_low_eas_widens_margin_increases_hr(self) -> None:
        """At a borderline p_include, low EAS should push to HR while
        high EAS keeps the auto-decision."""
        router = _balanced_router()
        # Borderline include: r_inc/r_exc ratio = 0.45/0.55 = 0.82,
        # in the indifference zone if margin widens enough.
        borderline_p = 0.55
        low_eas_decision = router.route(
            p_include=borderline_p,
            ecs_final=0.85,
            rule_overrides=[],
            eas_score=0.20,
        )
        high_eas_decision = router.route(
            p_include=borderline_p,
            ecs_final=0.85,
            rule_overrides=[],
            eas_score=0.95,
        )
        assert low_eas_decision.decision == Decision.HUMAN_REVIEW
        assert high_eas_decision.decision == Decision.INCLUDE


# ---------------------------------------------------------------------------
# ESAS narrows margin only; it never bypasses Phase 2 gates
# ---------------------------------------------------------------------------


class TestEsasMarginNarrowing:
    def test_high_esas_can_narrow_margin_when_gates_pass(self) -> None:
        router = _balanced_router()

        without_esas = router.route(
            p_include=1.0 / 47.0,
            ecs_final=0.90,
            rule_overrides=[],
            eas_score=1.0,
            esas_score=0.0,
        )
        with_high_esas = router.route(
            p_include=1.0 / 47.0,
            ecs_final=0.90,
            rule_overrides=[],
            eas_score=1.0,
            esas_score=1.0,
            esas_margin_narrowing_factor=0.30,
        )

        assert without_esas.decision == Decision.HUMAN_REVIEW
        assert with_high_esas.decision == Decision.INCLUDE

    def test_low_esas_is_noop_for_margin(self) -> None:
        router = _balanced_router()

        decision = router.route(
            p_include=1.0 / 47.0,
            ecs_final=0.90,
            rule_overrides=[],
            eas_score=1.0,
            esas_score=0.50,
            esas_margin_narrowing_factor=0.30,
        )

        assert decision.decision == Decision.HUMAN_REVIEW

    def test_high_esas_cannot_bypass_eas_gate(self) -> None:
        router = _balanced_router()

        decision = router.route(
            p_include=1.0 / 47.0,
            ecs_final=0.90,
            rule_overrides=[],
            eas_score=0.20,
            esas_score=1.0,
            esas_margin_narrowing_factor=0.30,
        )

        assert decision.decision == Decision.HUMAN_REVIEW

    def test_high_esas_cannot_bypass_exclude_certainty_gate(self) -> None:
        router = _balanced_router()

        decision = router.route(
            p_include=0.001,
            ecs_final=0.05,
            rule_overrides=[],
            eas_score=1.0,
            esas_score=1.0,
            esas_margin_narrowing_factor=0.30,
            exclude_certainty_passes=False,
        )

        assert decision.decision == Decision.HUMAN_REVIEW

    def test_missing_exclude_certainty_defaults_to_hr_for_exclude(self) -> None:
        router = _balanced_router()

        decision = router.route(
            p_include=0.001,
            ecs_final=0.05,
            rule_overrides=[],
            eas_score=1.0,
        )

        assert decision.decision == Decision.HUMAN_REVIEW


# ---------------------------------------------------------------------------
# ecs_confidence routing mode also respects Phase 2 gates
# ---------------------------------------------------------------------------


class TestEcsConfidenceModeAlsoGated:
    """The alternate ``routing_mode='ecs_confidence'`` path must NOT bypass
    Phase 2 gates. The unified post-gate in ``route()`` enforces the
    contract for every routing mode."""

    def _ecs_router(self) -> BayesianRouter:
        return BayesianRouter(
            LossMatrix.from_preset("balanced"),
            routing_mode="ecs_confidence",
        )

    def test_ecs_confidence_low_eas_yields_hr(self) -> None:
        router = self._ecs_router()
        decision = router.route(
            p_include=0.95,
            ecs_final=0.9,
            rule_overrides=[],
            eas_score=0.2,                    # below full-regime gate
        )
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_ecs_confidence_exclude_without_excert_yields_hr(self) -> None:
        router = self._ecs_router()
        decision = router.route(
            p_include=0.001,
            ecs_final=0.05,
            rule_overrides=[],
            eas_score=0.9,
            exclude_certainty_passes=False,    # would be auto-EXCLUDE without Phase 2
        )
        assert decision.decision == Decision.HUMAN_REVIEW

    def test_ecs_confidence_include_low_ecs_yields_hr(self) -> None:
        router = self._ecs_router()
        decision = router.route(
            p_include=0.95,
            ecs_final=0.10,                    # ECS conflicts with INCLUDE direction
            rule_overrides=[],
            eas_score=0.9,
        )
        assert decision.decision == Decision.HUMAN_REVIEW


# ---------------------------------------------------------------------------
# Backward-compat: hard rule overrides still win
# ---------------------------------------------------------------------------


class TestHardRuleOverrideStillTier0:
    def test_hard_rule_overrides_phase2_gates(self) -> None:
        from metascreener.core.models_screening import RuleViolation

        router = _balanced_router()
        violation = RuleViolation(
            rule_name="retraction",
            rule_type="hard",
            description="Retracted paper",
            penalty=0.0,
        )
        decision = router.route(
            p_include=0.99,
            ecs_final=0.99,
            rule_overrides=[violation],
            eas_score=0.99,
            exclude_certainty_passes=True,
        )
        assert decision.decision == Decision.EXCLUDE
        # Tier 0 confirms hard-rule path still bypasses Phase 2 gates
        from metascreener.core.enums import Tier
        assert decision.tier == Tier.ZERO
