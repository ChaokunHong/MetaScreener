"""Title/Abstract screening orchestrator — full HCN pipeline.

Coordinates all four layers of the Hierarchical Consensus Network:
  Layer 1: Parallel LLM inference with framework-specific prompts
  Layer 2: Semantic rule engine (3 hard + 3 soft rules)
  Layer 3: Calibrated Confidence Aggregation (CCA)
  Layer 4: Hierarchical decision routing (Tier 0-3)
"""
from __future__ import annotations

from collections.abc import Sequence

import structlog

from metascreener.core.enums import ScreeningStage
from metascreener.core.models import (
    AuditEntry,
    PICOCriteria,
    Record,
    ReviewCriteria,
    ScreeningDecision,
)
from metascreener.llm.base import LLMBackend
from metascreener.module1_screening.layer1.inference import InferenceEngine
from metascreener.module1_screening.layer2.rule_engine import RuleEngine
from metascreener.module1_screening.layer3.aggregator import CCAggregator
from metascreener.module1_screening.layer4.router import DecisionRouter

logger = structlog.get_logger(__name__)


class TAScreener:
    """Title/Abstract screening orchestrator — full HCN pipeline.

    Runs the complete 4-layer HCN pipeline for each record and produces
    a ScreeningDecision with full audit trail.

    Args:
        backends: LLM backends for parallel inference.
        rule_engine: Layer 2 rule engine. If None, uses defaults.
        aggregator: Layer 3 CCA aggregator. If None, uses defaults.
        router: Layer 4 decision router. If None, uses defaults.
        timeout_s: Timeout per LLM call in seconds.
    """

    def __init__(
        self,
        backends: Sequence[LLMBackend],
        rule_engine: RuleEngine | None = None,
        aggregator: CCAggregator | None = None,
        router: DecisionRouter | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self._backends = list(backends)
        self._inference = InferenceEngine(backends, timeout_s=timeout_s)
        self._rules = rule_engine or RuleEngine()
        self._aggregator = aggregator or CCAggregator()
        self._router = router or DecisionRouter()

    async def screen_single(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
    ) -> ScreeningDecision:
        """Screen a single record through the full HCN pipeline.

        Args:
            record: The literature record to screen.
            criteria: Review criteria (PICOCriteria auto-converted).
            seed: Random seed for reproducibility.

        Returns:
            ScreeningDecision with decision, tier, score, and outputs.
        """
        # Layer 1: Parallel LLM inference
        model_outputs = await self._inference.infer(
            record, criteria, seed=seed
        )

        # Layer 2: Semantic rule engine
        rule_result = self._rules.check(
            record, criteria, model_outputs
        )

        # Layer 3: Calibrated confidence aggregation
        s_final, c_ensemble = self._aggregator.aggregate(
            model_outputs, rule_penalty=rule_result.total_penalty
        )

        # Layer 4: Hierarchical decision routing
        decision, tier = self._router.route(
            model_outputs, rule_result, s_final, c_ensemble
        )

        logger.info(
            "screening_complete",
            record_id=record.record_id,
            decision=decision.value,
            tier=tier.value,
            score=round(s_final, 4),
            confidence=round(c_ensemble, 4),
        )

        return ScreeningDecision(
            record_id=record.record_id,
            stage=ScreeningStage.TITLE_ABSTRACT,
            decision=decision,
            tier=tier,
            final_score=s_final,
            ensemble_confidence=c_ensemble,
            model_outputs=model_outputs,
            rule_result=rule_result,
        )

    async def screen_batch(
        self,
        records: Sequence[Record],
        criteria: ReviewCriteria | PICOCriteria,
        seed: int = 42,
    ) -> list[ScreeningDecision]:
        """Screen a batch of records sequentially.

        Args:
            records: Records to screen.
            criteria: Review criteria (shared across all records).
            seed: Random seed for reproducibility.

        Returns:
            List of ScreeningDecision, one per record.
        """
        results: list[ScreeningDecision] = []
        for i, record in enumerate(records):
            logger.info(
                "screening_progress",
                current=i + 1,
                total=len(records),
                record_id=record.record_id,
            )
            result = await self.screen_single(record, criteria, seed=seed)
            results.append(result)
        return results

    def build_audit_entry(
        self,
        record: Record,
        criteria: ReviewCriteria | PICOCriteria,
        decision: ScreeningDecision,
        seed: int = 42,
    ) -> AuditEntry:
        """Build a TRIPOD-LLM compliant audit trail entry.

        Args:
            record: The screened record.
            criteria: Review criteria used.
            decision: The screening decision.
            seed: Random seed used.

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
        prompt_hashes = {
            o.model_id: o.prompt_hash
            for o in decision.model_outputs
            if o.prompt_hash
        }

        return AuditEntry(
            record_id=record.record_id,
            record_title=record.title,
            stage=ScreeningStage.TITLE_ABSTRACT,
            criteria_id=criteria_obj.criteria_id,
            criteria_version=criteria_obj.criteria_version,
            model_versions=model_versions,
            prompt_hashes=prompt_hashes,
            model_outputs=decision.model_outputs,
            rule_result=decision.rule_result,
            final_decision=decision.decision,
            tier=decision.tier,
            final_score=decision.final_score,
            ensemble_confidence=decision.ensemble_confidence,
            seed=seed,
        )
