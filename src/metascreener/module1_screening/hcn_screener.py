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

from collections.abc import Sequence

import structlog

from metascreener.core.enums import ScreeningStage
from metascreener.core.models import (
    AuditEntry,
    ModelOutput,
    PICOCriteria,
    Record,
    ReviewCriteria,
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
    ) -> None:
        self._backends = list(backends)
        self._inference = InferenceEngine(backends, timeout_s=timeout_s)
        self._rules = rule_engine or RuleEngine()
        self._aggregator = aggregator or CCAggregator(weights=prior_weights)
        self._router = router or DecisionRouter()
        self._fitted_calibrators = fitted_calibrators
        self._heuristic_alpha = heuristic_alpha
        self._prior_weights = prior_weights

    async def screen_single(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
        stage: str | None = None,
    ) -> ScreeningDecision:
        """Screen a single record through the full HCN pipeline.

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

        # Layer 1: Parallel LLM inference
        model_outputs = await self._inference.infer(
            record, criteria, seed=seed, stage=stage
        )

        # Layer 2: Semantic rule engine
        rule_result = self._rules.check(
            record, criteria, model_outputs, stage=stage
        )

        # Element-level consensus for structured adjudication
        element_consensus = build_element_consensus(criteria, model_outputs)

        # Layer 3a: Element Consensus Score (ECS)
        ecs_result = compute_ecs(element_consensus)

        # Layer 3b: Disagreement classification (informational)
        disagreement_result = classify_disagreement(
            model_outputs, ecs_result=ecs_result
        )

        # Layer 3c: Calibration (fitted if available, else CAMD heuristic)
        calibration_factors = get_calibration_factors(
            model_outputs,
            fitted_calibrators=self._fitted_calibrators,
            alpha=self._heuristic_alpha,
            prior_weights=self._prior_weights,
        )

        # Layer 3d: Calibrated confidence aggregation
        s_final, c_ensemble = self._aggregator.aggregate(
            model_outputs,
            rule_penalty=rule_result.total_penalty,
            calibration_overrides=calibration_factors or None,
        )

        # Layer 4: Hierarchical decision routing with ECS gating
        decision, tier = self._router.route(
            model_outputs,
            rule_result,
            s_final,
            c_ensemble,
            element_consensus=element_consensus,
            ecs_result=ecs_result,
            disagreement_result=disagreement_result,
        )

        logger.info(
            "screening_complete",
            record_id=record.record_id,
            stage=stage,
            decision=decision.value,
            tier=tier.value,
            score=round(s_final, 4),
            confidence=round(c_ensemble, 4),
            ecs_score=round(ecs_result.score, 4),
            disagreement=disagreement_result.disagreement_type.value,
        )

        return ScreeningDecision(
            record_id=record.record_id,
            stage=ScreeningStage(stage),
            decision=decision,
            tier=tier,
            final_score=s_final,
            ensemble_confidence=c_ensemble,
            model_outputs=model_outputs,
            rule_result=rule_result,
            element_consensus=element_consensus,
            ecs_result=ecs_result,
            disagreement_result=disagreement_result,
        )

    async def screen_batch(
        self,
        records: Sequence[Record],
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
        stage: str | None = None,
    ) -> list[ScreeningDecision]:
        """Screen a batch of records sequentially.

        Args:
            records: Records to screen.
            criteria: Review criteria (shared across all records).
            seed: Random seed for reproducibility.
            stage: Screening stage. If None, uses ``default_stage``.

        Returns:
            List of ScreeningDecision, one per record.
        """
        if stage is None:
            stage = self.default_stage

        results: list[ScreeningDecision] = []
        for i, record in enumerate(records):
            logger.info(
                "screening_progress",
                current=i + 1,
                total=len(records),
                record_id=record.record_id,
            )
            result = await self.screen_single(
                record, criteria, seed=seed, stage=stage
            )
            results.append(result)
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
