"""Base HCN (Hierarchical Consensus Network) screening orchestrator.

Coordinates all four layers of the HCN pipeline:
  Layer 1: Parallel LLM inference with framework-specific prompts
  Layer 2: Semantic rule engine (hard + soft + info rules)
  Layer 3: Calibrated Confidence Aggregation (CCA)
           + Element Consensus Score (ECS)
           + Heuristic calibration (cross-model consistency)
           + Disagreement classification
  Layer 4: Hierarchical decision routing (Tier 0-3) with ECS gating

Subclasses:
  - ``TAScreener``: Title/Abstract screening (stage="ta")
  - ``FTScreener``: Full-text screening (stage="ft") with PDF chunking
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

import structlog

from metascreener.config import MetaScreenerConfig
from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import (
    AuditEntry,
    ModelOutput,
    PICOCriteria,
    Record,
    ReviewCriteria,
    RuleCheckResult,
    ScreeningDecision,
)
from metascreener.llm.base import LLMBackend
from metascreener.module1_screening.layer1.inference import InferenceEngine
from metascreener.module1_screening.layer2.rule_engine import RuleEngine
from metascreener.module1_screening.layer3.aggregator import CCAggregator
from metascreener.module1_screening.layer3.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
)
from metascreener.module1_screening.layer3.disagreement import (
    classify_disagreement,
)
from metascreener.module1_screening.layer3.element_consensus import (
    build_element_consensus,
    compute_ecs,
)
from metascreener.module1_screening.layer3.heuristic_calibrator import (
    get_calibration_factors,
)
from metascreener.module1_screening.layer4.router import DecisionRouter

logger = structlog.get_logger(__name__)


class HCNScreener:
    """Base HCN screening orchestrator — shared Layer 1-4 pipeline.

    This class contains the core screening logic used by both TA and FT
    screening. Subclasses customize the ``default_stage`` and may add
    stage-specific pre/post-processing (e.g., PDF chunking for FT).

    Args:
        backends: LLM backends for parallel inference.
        rule_engine: Layer 2 rule engine. If None, uses defaults.
        aggregator: Layer 3 CCA aggregator. If None, uses defaults.
        router: Layer 4 decision router. If None, uses defaults.
        timeout_s: Timeout per LLM call in seconds.
        prior_weights: Model-id to weight mapping for CCA.
        fitted_calibrators: Pre-fitted Platt/isotonic calibrators per model.
        heuristic_alpha: Sensitivity for heuristic calibration deviation.
        element_weights: Custom element weights for ECS (element_key → weight).
            If None, uses the defaults from element_consensus module.
        calibration_overrides: Fixed per-model calibration factors
            (model_id → φ_i) from active learning / pilot recalibration.
            When provided, these override CAMD heuristic factors for the
            specified models.  Models not in the dict still use CAMD.
    """

    default_stage: str = "ta"

    def __init__(
        self,
        backends: Sequence[LLMBackend],
        rule_engine: RuleEngine | None = None,
        aggregator: CCAggregator | None = None,
        router: DecisionRouter | None = None,
        timeout_s: float = 120.0,
        prior_weights: dict[str, float] | None = None,
        fitted_calibrators: (
            dict[str, PlattCalibrator | IsotonicCalibrator] | None
        ) = None,
        heuristic_alpha: float = 0.5,
        element_weights: dict[str, float] | None = None,
        calibration_overrides: dict[str, float] | None = None,
        config: MetaScreenerConfig | None = None,
    ) -> None:
        self._backends = list(backends)
        self._inference = InferenceEngine(backends, timeout_s=timeout_s)
        self._rules = rule_engine or RuleEngine()
        self._aggregator = aggregator or CCAggregator(weights=prior_weights)
        self._router = router or DecisionRouter()
        self._fitted_calibrators = fitted_calibrators
        self._heuristic_alpha = heuristic_alpha
        self._prior_weights = prior_weights
        self._element_weights = element_weights
        self._calibration_overrides = calibration_overrides

        # ── v2.1 Bayesian pipeline (component-level feature switches) ──
        self._config = config or MetaScreenerConfig()
        self._use_bayesian = self._config.aggregation.method in (
            "dawid_skene",
            "glad",
        )
        self._use_glad = False
        self._labelled_buffer: list[dict] = []

        if self._use_bayesian:
            prevalence_map = {"low": 0.03, "medium": 0.07, "high": 0.15}
            prevalence = prevalence_map[self._config.decision.prevalence_prior]
            n_models = len(self._backends)

            from metascreener.module1_screening.layer3.dawid_skene import (  # noqa: PLC0415
                BayesianDawidSkene,
            )

            self.ds = BayesianDawidSkene(
                n_models=n_models,
                alpha_0=self._config.aggregation.ds_prior_alpha,
                beta_0=self._config.aggregation.ds_prior_beta,
                prevalence=prevalence,
            )

            if self._config.aggregation.method == "glad":
                from metascreener.module1_screening.layer3.glad import GLAD  # noqa: PLC0415

                self.glad = GLAD(
                    n_models=n_models,
                    alpha_0=self._config.aggregation.ds_prior_alpha,
                    beta_0=self._config.aggregation.ds_prior_beta,
                    prevalence=prevalence,
                )

        if self._config.sprt.enabled and self._use_bayesian:
            from metascreener.core.models_bayesian import LossMatrix  # noqa: PLC0415
            from metascreener.module1_screening.layer1.sprt_inference import (  # noqa: PLC0415
                SPRTInference,
            )

            loss = LossMatrix.from_preset(self._config.decision.loss_preset)
            self.sprt = SPRTInference(
                loss, self.ds, wave1_size=self._config.sprt.waves
            )

        if self._config.router.method == "bayesian":
            from metascreener.core.models_bayesian import LossMatrix  # noqa: PLC0415
            from metascreener.module1_screening.layer4.bayesian_router import (  # noqa: PLC0415
                BayesianRouter,
            )

            loss = LossMatrix.from_preset(self._config.decision.loss_preset)
            self.bayesian_router = BayesianRouter(loss)

        if self._config.rcps.enabled:
            from metascreener.module1_screening.layer4.rcps import (  # noqa: PLC0415
                RCPSController,
            )

            self.rcps = RCPSController(
                alpha_fnr=self._config.rcps.alpha_fnr,
                alpha_automation=self._config.rcps.alpha_automation,
                delta=self._config.rcps.delta,
                min_calibration_size=self._config.rcps.min_calibration_size,
            )

        if self._config.ipw.audit_rate > 0:
            from metascreener.module1_screening.layer3.ipw import (  # noqa: PLC0415
                IPWController,
            )

            self.ipw = IPWController(
                audit_rate=self._config.ipw.audit_rate,
                seed=self._config.ipw.seed,
            )

    async def screen_single(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
        stage: str | None = None,
    ) -> ScreeningDecision:
        """Screen a single record through the full HCN pipeline.

        Supports component-level dispatch between v2.0 (CCA) and v2.1
        (Bayesian) paths based on ``self._config``.  Each step uses an
        if/else to select the appropriate component.

        Args:
            record: The literature record to screen.
            criteria: Review criteria (PICOCriteria auto-converted).
            seed: Random seed for reproducibility.
            stage: Screening stage. If None, uses ``default_stage``.

        Returns:
            ScreeningDecision with decision, tier, score, and outputs.
        """
        if stage is None:
            stage = self.default_stage

        # ── Step 0: Hard rule pre-check (v2.1 only) ──
        if self._use_bayesian:
            hard_result = self._rules.check_hard_rules(record, criteria)
            if hard_result.has_hard_violation:
                return ScreeningDecision(
                    record_id=record.record_id,
                    stage=ScreeningStage(stage),
                    decision=Decision.EXCLUDE,
                    tier=Tier.ZERO,
                    final_score=0.0,
                    ensemble_confidence=1.0,
                    rule_result=hard_result,
                )

        # ── Step 1: Inference ──
        early_stop = False
        if self._config.sprt.enabled and self._use_bayesian:
            model_outputs, early_stop = await self.sprt.run(
                record, criteria, self._backends, seed
            )
        else:
            model_outputs = await self._inference.infer(
                record, criteria, seed=seed, stage=stage
            )

        # ── Step 2: Rules ──
        if self._use_bayesian:
            model_outputs = self._rules.apply_soft_rules(
                model_outputs, criteria, record
            )
            rule_result = RuleCheckResult()
        else:
            rule_result = self._rules.check(
                record, criteria, model_outputs, stage=stage
            )

        # Sort by model_id for determinism
        model_outputs.sort(key=lambda o: o.model_id)

        # ── Step 3: Element Consensus ──
        element_consensus = build_element_consensus(criteria, model_outputs)

        # ── Step 4: ECS ──
        if self._config.ecs.method == "geometric":
            from metascreener.module1_screening.layer3.element_consensus import (  # noqa: PLC0415
                compute_ecs_geometric,
            )

            ecs_result = compute_ecs_geometric(
                element_consensus,
                self._element_weights or {},
                trim_percentile=self._config.ecs.trim_percentile,
                min_threshold=self._config.ecs.min_threshold,
                epsilon=self._config.ecs.epsilon,
            )
        else:
            ecs_result = compute_ecs(
                element_consensus, element_weights=self._element_weights
            )

        # ── Step 5: Aggregation ──
        p_include: float | None = None
        confidence: float | None = None
        s_final: float = 0.0
        c_ensemble: float = 0.0
        disagree_result = None

        if self._use_bayesian:
            p_include, confidence = self._aggregate_bayesian(model_outputs)
        else:
            # v2.0 path: CAMD + CCA
            disagree_result = classify_disagreement(
                model_outputs, ecs_result=ecs_result
            )
            calibration_factors = get_calibration_factors(
                model_outputs,
                fitted_calibrators=self._fitted_calibrators,
                alpha=self._heuristic_alpha,
                prior_weights=self._prior_weights,
            )
            if self._calibration_overrides:
                merged = (
                    dict(calibration_factors) if calibration_factors else {}
                )
                merged.update(self._calibration_overrides)
                calibration_factors = merged
            s_final, c_ensemble = self._aggregator.aggregate(
                model_outputs,
                rule_penalty=rule_result.total_penalty,
                calibration_overrides=calibration_factors or None,
            )

        # ── Step 5b: ESAS (optional, v2.1 only) ──
        if self._config.esas.enabled and p_include is not None:
            from metascreener.module1_screening.layer3.evidence_alignment import (  # noqa: PLC0415
                compute_esas,
                esas_modulation,
            )

            mean_esas, _ = compute_esas(
                model_outputs, list(element_consensus.keys())
            )
            confidence = esas_modulation(
                confidence,  # type: ignore[arg-type]
                mean_esas,
                gamma=self._config.esas.gamma,
                tau=self._config.esas.tau,
            )

        # ── Step 6: Routing ──
        expected_loss: dict[str, float] | None = None

        if self._config.router.method == "bayesian":
            # RCPS adjustment
            if self._config.rcps.enabled and hasattr(self, "rcps"):
                from metascreener.core.models_bayesian import LossMatrix  # noqa: PLC0415
                from metascreener.module1_screening.layer4.bayesian_router import (  # noqa: PLC0415
                    BayesianRouter,
                )

                adjusted_loss = self.rcps.adjust_loss(
                    LossMatrix.from_preset(self._config.decision.loss_preset)
                )
                adjusted_router = BayesianRouter(adjusted_loss)
            else:
                adjusted_router = self.bayesian_router

            bayes_decision = adjusted_router.route(
                p_include=p_include,  # type: ignore[arg-type]
                ecs_final=ecs_result.score,
                rule_overrides=[],
            )
            decision = bayes_decision.decision
            tier = bayes_decision.tier
            expected_loss = bayes_decision.expected_loss
            s_final_out = p_include  # type: ignore[assignment]
            c_ensemble_out = confidence  # type: ignore[assignment]
        elif p_include is not None:
            # DS aggregation + old threshold router
            decision, tier = self._router.route(
                model_outputs,
                rule_result,
                p_include,
                confidence,  # type: ignore[arg-type]
                element_consensus=element_consensus,
                ecs_result=ecs_result,
            )
            s_final_out = p_include
            c_ensemble_out = confidence  # type: ignore[assignment]
        else:
            # Full v2.0 path — disagreement already computed in step 5
            decision, tier = self._router.route(
                model_outputs,
                rule_result,
                s_final,
                c_ensemble,
                element_consensus=element_consensus,
                ecs_result=ecs_result,
                disagreement_result=disagree_result,
            )
            s_final_out = s_final
            c_ensemble_out = c_ensemble

        # ── Step 7: IPW audit sampling ──
        requires_labelling = False
        ipw_weight: float | None = None
        if self._config.ipw.audit_rate > 0 and hasattr(self, "ipw"):
            requires_labelling = self.ipw.should_audit(decision)
            if requires_labelling:
                ipw_weight = self.ipw.get_ipw_weight(decision)

        # ── Step 8: Build result ──
        logger.info(
            "screening_complete",
            record_id=record.record_id,
            stage=stage,
            decision=decision.value,
            tier=tier.value,
            score=round(s_final_out, 4),
            confidence=(
                round(c_ensemble_out, 4) if c_ensemble_out else 0.0
            ),
            ecs_score=round(ecs_result.score, 4),
        )

        return ScreeningDecision(
            record_id=record.record_id,
            stage=ScreeningStage(stage),
            decision=decision,
            tier=tier,
            final_score=s_final_out,
            ensemble_confidence=c_ensemble_out or 0.0,
            model_outputs=model_outputs,
            rule_result=rule_result,
            element_consensus=element_consensus,
            ecs_result=ecs_result,
            disagreement_result=disagree_result,
            p_include=p_include,
            expected_loss=expected_loss,
            requires_labelling=requires_labelling,
            ipw_weight=ipw_weight,
            sprt_early_stop=early_stop,
            models_called=len(model_outputs),
        )

    def _aggregate_bayesian(
        self,
        model_outputs: list[ModelOutput],
    ) -> tuple[float, float]:
        """Aggregate using Dawid-Skene or GLAD.

        Returns:
            Tuple of (p_include, confidence).
        """
        import math  # noqa: PLC0415

        import numpy as np  # noqa: PLC0415
        from scipy.stats import entropy as scipy_entropy  # noqa: PLC0415

        annotations: list[int | None] = []
        for o in model_outputs:
            if o.decision == Decision.INCLUDE:
                annotations.append(0)
            elif o.decision == Decision.EXCLUDE:
                annotations.append(1)
            else:
                annotations.append(None)

        if self._config.parse_quality.enabled:
            qualities = [o.parse_quality for o in model_outputs]
        else:
            qualities = [1.0] * len(model_outputs)

        if self._use_glad and hasattr(self, "glad") and self.glad.active:
            features = self.glad.compute_features(None, model_outputs, criteria=None)
            difficulty = self.glad.predict_difficulty(features)
            posterior = self.glad.e_step_glad(annotations, qualities, difficulty)
        else:
            posterior = self.ds.e_step(annotations, qualities)

        p_include = float(posterior[0])

        # Confidence = 1 - normalized entropy
        ent = scipy_entropy(posterior)
        max_ent = math.log(len(posterior))
        confidence = 1.0 - (ent / max_ent if max_ent > 0 else 0.0)

        return p_include, confidence

    def incorporate_feedback(
        self,
        record_id: str,
        true_label: int,
        decision: ScreeningDecision,
    ) -> None:
        """Process human feedback for online learning (v2.1 only).

        Accumulates labelled records and triggers batch updates to
        the Dawid-Skene confusion matrix (and optionally GLAD
        difficulty model) every ``batch_update_size`` records.

        Args:
            record_id: Identifier of the labelled record.
            true_label: Ground truth label (0=INCLUDE, 1=EXCLUDE).
            decision: The original ScreeningDecision for the record.
        """
        if not self._use_bayesian:
            return

        annotations: list[int | None] = []
        for o in decision.model_outputs:
            if o.decision == Decision.INCLUDE:
                annotations.append(0)
            elif o.decision == Decision.EXCLUDE:
                annotations.append(1)
            else:
                annotations.append(None)

        labelled = {
            "record_id": record_id,
            "annotations": annotations,
            "parse_qualities": [o.parse_quality for o in decision.model_outputs],
            "true_label": true_label,
            "ipw_weight": decision.ipw_weight or 1.0,
        }
        self._labelled_buffer.append(labelled)

        batch_size = self._config.aggregation.batch_update_size
        if len(self._labelled_buffer) % batch_size == 0:
            batch = sorted(
                self._labelled_buffer, key=lambda r: r["record_id"]
            )
            self.ds.m_step_update(batch)

            # GLAD switch check
            if (
                self._config.aggregation.method == "glad"
                and len(batch) >= self._config.aggregation.glad_switch_after_n
                and not self._use_glad
                and hasattr(self, "glad")
            ):
                import numpy as np  # noqa: PLC0415

                self.glad.posterior = self.ds.posterior.copy()
                pilot_data = []
                for r in batch:
                    features = self.glad.compute_features(None, [], criteria=None)
                    ds_pred = (
                        0
                        if self.ds.e_step(
                            r["annotations"], r["parse_qualities"]
                        )[0]
                        > 0.5
                        else 1
                    )
                    pilot_data.append(
                        {
                            "features": features,
                            "ds_correct": ds_pred == r["true_label"],
                        }
                    )
                self.glad.fit_difficulty_model(pilot_data)
                self._use_glad = self.glad.active

            # RCPS recalibration
            if self._config.rcps.enabled and hasattr(self, "rcps"):
                cal_records = [
                    {
                        "p_include": self.ds.e_step(
                            r["annotations"], r["parse_qualities"]
                        )[0],
                        "true_label": r["true_label"],
                        "ipw_weight": r["ipw_weight"],
                    }
                    for r in batch
                ]
                self.rcps.calibrate(cal_records)

    async def screen_batch(
        self,
        records: Sequence[Record],
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
        stage: str | None = None,
        completed_ids: set[str] | None = None,
        on_result: Callable[[ScreeningDecision, int, int], None] | None = None,
    ) -> list[ScreeningDecision]:
        """Screen a batch of records sequentially with checkpoint support.

        Args:
            records: Records to screen.
            criteria: Review criteria (shared across all records).
            seed: Random seed for reproducibility.
            stage: Screening stage. If None, uses ``default_stage``.
            completed_ids: Record IDs already screened (for resume).
                Records in this set are skipped.
            on_result: Optional callback invoked after each record is
                screened, receiving ``(decision, current_index, total)``.
                Use this for progress reporting or persisting intermediate
                results to disk.

        Returns:
            List of ScreeningDecision, one per record (excludes skipped).
        """
        if stage is None:
            stage = self.default_stage

        skip = completed_ids or set()
        results: list[ScreeningDecision] = []
        total = len(records)

        for i, record in enumerate(records):
            if str(record.record_id) in skip:
                logger.debug(
                    "screening_skipped_checkpoint",
                    record_id=record.record_id,
                )
                continue

            logger.info(
                "screening_progress",
                current=i + 1,
                total=total,
                record_id=record.record_id,
            )
            result = await self.screen_single(
                record, criteria, seed=seed, stage=stage
            )
            results.append(result)

            if on_result is not None:
                on_result(result, i + 1, total)

        return results

    def build_audit_entry(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        decision: ScreeningDecision,
        seed: int = 42,
        calibration_method: str = "none",
        calibration_factors: dict[str, float] | None = None,
    ) -> AuditEntry:
        """Build a TRIPOD-LLM compliant audit trail entry.

        For chunked decisions (``decision.chunking_applied == True``),
        model_outputs and prompt_hashes are collected from all
        ``chunk_details`` since the aggregate decision has empty
        model_outputs.

        Args:
            record: The screened record.
            criteria: Review criteria used.
            decision: The screening decision.
            seed: Random seed used.
            calibration_method: Calibration method applied.
            calibration_factors: Per-model calibration factors.

        Returns:
            AuditEntry with full reproducibility information.
        """
        criteria_obj = (
            ReviewCriteria.from_pico_criteria(criteria)
            if isinstance(criteria, PICOCriteria)
            else criteria
        )

        model_versions = {
            b.model_id: b.model_version for b in self._backends
        }

        # For chunked decisions, collect from chunk_details
        if decision.chunking_applied and decision.chunk_details:
            all_outputs: list[ModelOutput] = []
            prompt_hashes: dict[str, str] = {}
            for chunk_dec in decision.chunk_details:
                all_outputs.extend(chunk_dec.model_outputs)
                for o in chunk_dec.model_outputs:
                    if o.prompt_hash and o.model_id not in prompt_hashes:
                        prompt_hashes[o.model_id] = o.prompt_hash
        else:
            all_outputs = decision.model_outputs
            prompt_hashes = {
                o.model_id: o.prompt_hash
                for o in decision.model_outputs
                if o.prompt_hash
            }

        return AuditEntry(
            record_id=record.record_id,
            record_title=record.title,
            stage=decision.stage,
            criteria_id=criteria_obj.criteria_id,
            criteria_version=criteria_obj.criteria_version,
            model_versions=model_versions,
            prompt_hashes=prompt_hashes,
            model_outputs=all_outputs,
            rule_result=decision.rule_result,
            element_consensus=decision.element_consensus,
            ecs_result=decision.ecs_result,
            disagreement_result=decision.disagreement_result,
            final_decision=decision.decision,
            tier=decision.tier,
            final_score=decision.final_score,
            ensemble_confidence=decision.ensemble_confidence,
            seed=seed,
            calibration_method=calibration_method,
            calibration_factors=calibration_factors or {},
            chunking_applied=decision.chunking_applied,
            n_chunks=decision.n_chunks,
            text_quality=decision.text_quality,
            chunk_heterogeneity=decision.chunk_heterogeneity,
        )
