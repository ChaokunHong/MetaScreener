"""Bayesian optimal decision router for HCN v2.1."""

from __future__ import annotations

import math

import structlog

from metascreener.core.enums import Decision, Tier
from metascreener.core.models_bayesian import LossMatrix
from metascreener.core.models_screening import RuleViolation, ScreeningDecision

logger = structlog.get_logger(__name__)


class BayesianRouter:
    """Bayesian optimal decision routing with directional ECS gates (Phase 2).

    Signal contract (after Codex math audit, 2026-04-27):
      * ``p_include``                  — direction probability
      * ``ecs_final``                  — inclusion support
                                          (high ⇒ supports INCLUDE,
                                           low ⇒ supports EXCLUDE)
      * ``eas_score``                  — direction-agnostic agreement
      * ``exclude_certainty_passes``   — exclusion-support gate

    Decision logic:
      1. Tier 0: hard rule violation → EXCLUDE.
      2. Compute expected losses r_inc, r_exc, r_hr.
      3. If r_hr ≤ both alternatives, return HR (classical loss-min path).
      4. **EAS-modulated uncertainty band:** the indifference margin grows
         linearly as EAS drops, then high ESAS may narrow it:
             effective_margin = (base + (1 - safe_eas) * widening_factor)
                                * rcps_margin_scale
             effective_margin *= 1 - normalized_esas * narrow_factor
         Low EAS therefore widens the HR zone; high EAS keeps it tight.
         ESAS only narrows the margin and never bypasses Phase 2 gates.
      5. Loss picks the proposed direction (INCLUDE or EXCLUDE).
      6. **Phase 2 gates:**
           - EAS gate (stricter under 2-model SPRT early-stop):
                 safe_eas < eas_threshold ⇒ HR
           - Direction-aligned ECS gate:
                 INCLUDE proposal: safe_ecs < ecs_include_gate    ⇒ HR
                 EXCLUDE proposal: safe_ecs > ecs_exclude_max     ⇒ HR
                                   AND not exclude_certainty_passes ⇒ HR
      7. Otherwise return the proposed direction.

    Phase 2 retired the legacy asymmetric ECS safety valve
    ("low ECS blocks EXCLUDE"): low ECS now correctly indicates
    EXCLUDE evidence and is permitted as long as
    ``exclude_certainty_passes`` and the EAS gate hold. Set
    ``phase2_gates_enabled=False`` to fall back to the legacy
    ECS-modulated margin + asymmetric safety valve for regression
    or ablation A0 reproduction.

    Why the uncertainty band exists:
      All three production presets have ``c_fp=1`` and ``c_hr ∈ {3,5,10}``,
      which makes the classical tie-break (step 3) mathematically
      impossible — ``r_inc ≤ c_fp = 1 < c_hr`` always holds. Without the
      EAS-modulated band, the router would silently auto-INCLUDE every
      borderline record (the 2026-04-08 Moran_2021/a3.json failure mode
      where p_include = 0.03 was treated as a confident INCLUDE).

    HCNScreener post-route safety:
      ``HCNScreener.screen_single`` may apply a difficulty-floor /
      loss-override path after the router runs, but that path must never
      promote a router-issued HUMAN_REVIEW back to auto-EXCLUDE. See
      ``tests/unit/test_phase2_post_route_safety.py`` for the regression
      contract.
    """

    #: Default abstention margin. Loss ratio min/max ≥ 0.70 → HR.
    #:
    #: We tried widening this to 0.40 and 0.50 to save true positives
    #: in low-prevalence datasets (Appenzeller, Jeyaraman, van_der_Waal)
    #: where LLMs underestimate p_include. That succeeded on those
    #: three datasets but **destroyed** Leenaars and Muthu by perturbing
    #: the IPW audit → DS feedback loop into a different fixed point
    #: (Leenaars 574→190 TPs, Muthu 321→141 TPs at margin=0.40).
    #:
    #: Total TPs found across 12 datasets:
    #:   margin=0.30 → 1347  (best)
    #:   margin=0.40 → 797   (worst — non-monotonic in margin!)
    #:   margin=0.50 → 1068
    #:
    #: The non-monotonicity reveals that IPW + DS form a dynamical
    #: system highly sensitive to router output. A principled fix must
    #: decouple IPW audit sampling from router margin — not tune this
    #: knob. See the IPW investigation for the real root cause.
    DEFAULT_UNCERTAINTY_MARGIN = 0.10

    def __init__(
        self,
        loss: LossMatrix,
        uncertainty_margin: float = DEFAULT_UNCERTAINTY_MARGIN,
        routing_mode: str = "margin",
        ecs_auto_threshold: float = 0.60,
        use_ecs_margin: bool = True,
        wave2_uncertainty_margin: float | None = None,
        # Phase 2 directional gates (defaults match the Codex math-audit spec).
        ecs_include_gate: float = 0.50,
        ecs_exclude_max: float = 0.50,
        eas_gate_full: float = 0.50,
        eas_gate_two_model_sprt: float = 0.70,
        eas_widening_factor: float = 0.30,
        phase2_gates_enabled: bool = True,
    ) -> None:
        if not 0.0 <= uncertainty_margin < 1.0:
            raise ValueError(
                f"uncertainty_margin must be in [0, 1), got {uncertainty_margin}"
            )
        if wave2_uncertainty_margin is not None and not 0.0 <= wave2_uncertainty_margin < 1.0:
            raise ValueError(
                f"wave2_uncertainty_margin must be in [0, 1), got {wave2_uncertainty_margin}"
            )
        self.loss = loss
        self.uncertainty_margin = uncertainty_margin
        self.routing_mode = routing_mode
        self.ecs_auto_threshold = ecs_auto_threshold
        self.use_ecs_margin = use_ecs_margin
        # A15c: wave2 (full-info) records use a narrower margin to stop
        # indifference-region HR when all 4 models have been consulted.
        # None = fall back to uncertainty_margin (no wave awareness).
        self.wave2_uncertainty_margin = wave2_uncertainty_margin
        # Phase 2: directional ECS gates + EAS modulation parameters.
        # ecs_include_gate: minimum ECS for auto-INCLUDE (ECS supports inclusion)
        # ecs_exclude_max: maximum ECS for auto-EXCLUDE (ECS does not support inclusion)
        # eas_gate_full / eas_gate_two_model_sprt: minimum EAS to permit auto
        # eas_widening_factor: additive margin growth as EAS drops (0->base, 1->base+factor)
        # phase2_gates_enabled=False reverts to legacy ECS-asymmetric behaviour for tests.
        self.ecs_include_gate = ecs_include_gate
        self.ecs_exclude_max = ecs_exclude_max
        self.eas_gate_full = eas_gate_full
        self.eas_gate_two_model_sprt = eas_gate_two_model_sprt
        self.eas_widening_factor = eas_widening_factor
        self.phase2_gates_enabled = phase2_gates_enabled

    def route(
        self,
        p_include: float,
        ecs_final: float,
        rule_overrides: list[RuleViolation],
        ecs_safety_threshold: float = 0.20,
        ensemble_confidence: float = 0.5,
        rcps_margin_scale: float = 1.0,
        glad_difficulty: float = 1.0,
        eas_score: float = 0.0,
        esas_score: float = 0.0,
        esas_margin_narrowing_factor: float = 0.30,
        esas_margin_narrowing_tau: float = 0.50,
        sprt_early_stop: bool = True,
        exclude_certainty_passes: bool | None = None,
        models_called: int = 4,
    ) -> ScreeningDecision:
        """Route a record to a screening decision using expected-loss minimization.

        Args:
            p_include: Calibrated posterior probability of inclusion in [0, 1].
            ecs_final: Element Consensus Score for the ECS safety valve.
            rule_overrides: Rule violations from Layer 2 semantic rule engine.
            ecs_safety_threshold: Minimum ECS required to allow auto-exclusion.
            ensemble_confidence: Ensemble confidence from DS/GLAD aggregation,
                optionally boosted by ESAS. Range [0, 1].
            glad_difficulty: GLAD item difficulty in (0, 1]. 1.0 when inactive.
            eas_score: Element Agreement Score in [0, 1]. Measures direction-
                agnostic model agreement. Used to modulate the uncertainty
                band: high EAS (strong agreement) → narrow band (decisive),
                low EAS (disagreement) → wide band (cautious).
            esas_score: Evidence sentence alignment in [0, 1]. High values
                can narrow the margin, but cannot bypass Phase 2 gates.

        Returns:
            ScreeningDecision with decision, tier, and expected-loss metadata.
        """
        # Tier 0: hard rule override
        hard_violations = [r for r in rule_overrides if r.rule_type == "hard"]
        if hard_violations:
            return ScreeningDecision(
                record_id="",
                decision=Decision.EXCLUDE,
                tier=Tier.ZERO,
                final_score=0.0,
                ensemble_confidence=1.0,
                expected_loss={"include": 0.0, "exclude": 0.0, "human_review": 0.0},
            )

        # Expected losses with difficulty-adjusted FN cost.
        # β_j < 1 (difficult) → c_fn / β_j increases → EXCLUDE is costlier
        # → borderline records route to HUMAN_REVIEW instead of EXCLUDE.
        # β_j = 1.0 → no adjustment (identical to standard Bayesian router).
        safe_beta = max(glad_difficulty, 0.01)
        adjusted_c_fn = self.loss.c_fn / safe_beta
        r_inc = self.loss.c_fp * (1.0 - p_include)
        r_exc = adjusted_c_fn * p_include
        r_hr = self.loss.c_hr

        expected = {
            "include": round(r_inc, 6),
            "exclude": round(r_exc, 6),
            "human_review": round(r_hr, 6),
        }

        conf = max(0.0, min(1.0, ensemble_confidence))
        safe_ecs = ecs_final if not math.isnan(ecs_final) else 0.0
        safe_eas = max(0.0, min(1.0, eas_score))

        # A15c: wave2 records (full-info, SPRT didn't early-stop) use a
        # narrower margin if configured, because all 4 models have already
        # been consulted and indifference-region HR buys no additional info.
        effective_uncertainty_margin = self.uncertainty_margin
        if (
            self.wave2_uncertainty_margin is not None
            and not sprt_early_stop
        ):
            effective_uncertainty_margin = self.wave2_uncertainty_margin

        if self.routing_mode == "ecs_confidence":
            chosen = self._route_ecs_confidence(
                r_inc, r_exc, r_hr, safe_ecs,
            )
        else:
            chosen = self._route_margin(
                r_inc, r_exc, r_hr, rcps_margin_scale,
                safe_ecs, ecs_safety_threshold, safe_eas,
                uncertainty_margin_override=effective_uncertainty_margin,
                esas_score=esas_score,
                esas_margin_narrowing_factor=esas_margin_narrowing_factor,
                esas_margin_narrowing_tau=esas_margin_narrowing_tau,
            )

        # Phase 2 unified post-gate: applied to ALL routing modes so the
        # ecs_confidence path cannot bypass the directional/EAS/exclude_
        # certainty gates. HUMAN_REVIEW is a no-op; proposed auto decisions
        # must pass the contract here.
        chosen = self._apply_phase2_gates(
            chosen,
            safe_ecs=safe_ecs,
            safe_eas=safe_eas,
            exclude_certainty_passes=exclude_certainty_passes,
            models_called=models_called,
            sprt_early_stop=sprt_early_stop,
        )

        tier = self._assign_tier(chosen, r_inc, r_exc, r_hr)

        return ScreeningDecision(
            record_id="",
            decision=chosen,
            tier=tier,
            final_score=p_include,
            ensemble_confidence=conf,
            expected_loss=expected,
        )

    def _route_margin(
        self,
        r_inc: float,
        r_exc: float,
        r_hr: float,
        rcps_margin_scale: float,
        safe_ecs: float,
        ecs_safety_threshold: float,
        safe_eas: float = 0.0,
        uncertainty_margin_override: float | None = None,
        esas_score: float = 0.0,
        esas_margin_narrowing_factor: float = 0.30,
        esas_margin_narrowing_tau: float = 0.50,
    ) -> Decision:
        """Phase 2 margin-based routing with directional ECS gates.

        Signal contract:
            * p_include       — direction probability (drives r_inc/r_exc)
            * ECS (safe_ecs)  — inclusion support; high ⇒ supports INCLUDE,
                                low ⇒ supports EXCLUDE
            * EAS (safe_eas)  — direction-agnostic agreement; modulates the
                                uncertainty margin and gates auto-decisions

        Routing:
            HR if r_hr is loss-optimal.
            HR if loss-ratio falls inside the EAS-widened indifference band.
            Loss picks proposed direction (INCLUDE / EXCLUDE).
            Phase 2 gates are applied by ``_apply_phase2_gates`` after all
            routing modes return their proposed decision.

        Legacy mode (phase2_gates_enabled=False) preserves the asymmetric
        ECS safety-valve behaviour for regression tests.
        """
        if r_hr <= r_inc and r_hr <= r_exc:
            return Decision.HUMAN_REVIEW

        base_margin = (
            uncertainty_margin_override
            if uncertainty_margin_override is not None
            else self.uncertainty_margin
        )

        if self.phase2_gates_enabled:
            # EAS-modulated margin: low EAS → wide margin → more HR.
            margin_widen = max(0.0, 1.0 - safe_eas) * self.eas_widening_factor
            effective_margin = (base_margin + margin_widen) * rcps_margin_scale
            effective_margin = self._apply_esas_margin_narrowing(
                effective_margin,
                esas_score=esas_score,
                narrowing_factor=esas_margin_narrowing_factor,
                tau=esas_margin_narrowing_tau,
            )
        elif self.use_ecs_margin:
            # Legacy ECS-modulated margin (Phase 1 behaviour).
            effective_margin = base_margin * (1.0 - safe_ecs) * rcps_margin_scale
        else:
            effective_margin = base_margin * rcps_margin_scale

        effective_margin = max(0.02, min(0.60, effective_margin))

        r_min = min(r_inc, r_exc)
        r_max = max(r_inc, r_exc)
        loss_ratio = r_min / r_max if r_max > 0 else 1.0

        if loss_ratio >= (1.0 - effective_margin):
            return Decision.HUMAN_REVIEW

        proposed = Decision.INCLUDE if r_inc <= r_exc else Decision.EXCLUDE

        if not self.phase2_gates_enabled:
            # Legacy: EXCLUDE blocked when ECS below safety threshold.
            if proposed == Decision.EXCLUDE and safe_ecs < ecs_safety_threshold:
                return Decision.HUMAN_REVIEW
            return proposed

        return proposed

    @staticmethod
    def _apply_esas_margin_narrowing(
        effective_margin: float,
        *,
        esas_score: float,
        narrowing_factor: float,
        tau: float,
    ) -> float:
        """Narrow the HR margin when evidence alignment is high.

        ESAS is intentionally one-way: values at/below tau are no-op, and
        values above tau can only shrink the margin. The narrowing factor is
        capped at 0.30, so callers passing larger values still get at most 30%
        narrowing. Tau is clamped below 1.0 for numerical stability; set
        narrowing_factor=0.0 to disable narrowing entirely. The implementation
        normalizes the interval above tau, so higher tau values make narrowing
        ramp up over a shorter ESAS range.
        """
        safe_esas = 0.0 if math.isnan(esas_score) else max(0.0, min(1.0, esas_score))
        safe_factor = max(0.0, min(0.30, narrowing_factor))
        safe_tau = max(0.0, min(0.999, tau))
        if safe_factor == 0.0 or safe_esas <= safe_tau:
            return effective_margin

        normalized_esas = (safe_esas - safe_tau) / (1.0 - safe_tau)
        narrowing = safe_factor * normalized_esas
        narrowed = effective_margin * (1.0 - narrowing)
        return max(0.02, min(0.60, narrowed))

    def _apply_phase2_gates(
        self,
        proposed: Decision,
        *,
        safe_ecs: float,
        safe_eas: float,
        exclude_certainty_passes: bool | None,
        models_called: int,
        sprt_early_stop: bool,
    ) -> Decision:
        """Apply Phase 2 directional gates to a proposed decision.

        This is the single source of truth for the Phase 2 contract:

            INCLUDE auto requires:  ecs ≥ ecs_include_gate AND eas ≥ gate
            EXCLUDE auto requires:  ecs ≤ ecs_exclude_max AND eas ≥ gate
                                    AND exclude_certainty_passes
            EAS gate is stricter under 2-model SPRT early-stop.

        Returns the proposed decision if all gates pass; HUMAN_REVIEW
        otherwise. Calling on HUMAN_REVIEW is a no-op.

        When ``phase2_gates_enabled`` is False the call is a no-op so the
        legacy regression path is preserved.
        """
        if not self.phase2_gates_enabled:
            return proposed
        if proposed == Decision.HUMAN_REVIEW:
            return proposed

        eas_threshold = (
            self.eas_gate_two_model_sprt
            if (sprt_early_stop and models_called <= 2)
            else self.eas_gate_full
        )
        if safe_eas < eas_threshold:
            return Decision.HUMAN_REVIEW

        if proposed == Decision.INCLUDE:
            if safe_ecs < self.ecs_include_gate:
                return Decision.HUMAN_REVIEW
            return Decision.INCLUDE

        # proposed == EXCLUDE
        if safe_ecs > self.ecs_exclude_max:
            return Decision.HUMAN_REVIEW
        if not exclude_certainty_passes:
            return Decision.HUMAN_REVIEW
        return Decision.EXCLUDE

    def _route_ecs_confidence(
        self,
        r_inc: float,
        r_exc: float,
        r_hr: float,
        safe_ecs: float,
    ) -> Decision:
        """Two-score routing: loss for direction, ECS for confidence.

        Step 1: Loss function determines the optimal direction
                (INCLUDE vs EXCLUDE). If HR is loss-optimal, return HR.
        Step 2: ECS determines whether we have enough element-level
                consensus to auto-execute the direction decision.
                ECS >= threshold → auto-execute.
                ECS < threshold → HUMAN_REVIEW.
        """
        # Step 1: loss-optimal direction
        if r_hr <= r_inc and r_hr <= r_exc:
            return Decision.HUMAN_REVIEW

        loss_direction = Decision.INCLUDE if r_inc <= r_exc else Decision.EXCLUDE

        # Step 2: ECS confidence gate
        if safe_ecs >= self.ecs_auto_threshold:
            return loss_direction
        return Decision.HUMAN_REVIEW

    @staticmethod
    def _assign_tier(decision: Decision, r_inc: float, r_exc: float, r_hr: float) -> Tier:
        """Assign a routing tier based on the relative gap between best and second-best loss.

        Args:
            decision: The chosen decision.
            r_inc: Expected loss for INCLUDE.
            r_exc: Expected loss for EXCLUDE.
            r_hr: Expected loss for HUMAN_REVIEW.

        Returns:
            Tier ONE, TWO, or THREE.
        """
        if decision == Decision.HUMAN_REVIEW:
            return Tier.THREE
        losses = sorted([r_inc, r_exc, r_hr])
        best = losses[0]
        second = losses[1]
        relative_gap = (second - best) / (second + 1e-10)
        if relative_gap > 0.5:
            return Tier.ONE
        elif relative_gap > 0.1:
            return Tier.TWO
        else:
            return Tier.THREE
