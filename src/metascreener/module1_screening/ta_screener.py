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

from metascreener.core.enums import Decision, ScreeningStage
from metascreener.core.models import (
    AuditEntry,
    ModelOutput,
    PICOCriteria,
    Record,
    ReviewCriteria,
    ScreeningDecision,
)
from metascreener.llm.base import LLMBackend, hash_prompt
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
        batch_size: int = 5,
    ) -> list[ScreeningDecision]:
        """Screen records in batches for performance.

        Groups records into batches of ``batch_size``, sends each batch
        as a single prompt to all models in parallel, then processes
        results through Layers 2-4 individually.

        Args:
            records: Records to screen.
            criteria: Review criteria (shared across all records).
            seed: Random seed for reproducibility.
            batch_size: Number of papers per prompt (default 5).

        Returns:
            List of ScreeningDecision, one per record.
        """
        import asyncio  # noqa: PLC0415

        from metascreener.module1_screening.layer1.batch_prompt import (  # noqa: PLC0415
            build_batch_screening_prompt,
            parse_batch_response,
        )

        if batch_size <= 1:
            # Fall back to sequential screening
            results: list[ScreeningDecision] = []
            for i, record in enumerate(records):
                logger.info("screening_progress", current=i + 1, total=len(records))
                result = await self.screen_single(record, criteria, seed=seed)
                results.append(result)
            return results

        # Split into batches
        record_list = list(records)
        batches: list[list[Record]] = []
        for i in range(0, len(record_list), batch_size):
            batches.append(record_list[i : i + batch_size])

        logger.info(
            "batch_screening_start",
            n_records=len(records),
            n_batches=len(batches),
            batch_size=batch_size,
        )

        all_decisions: list[ScreeningDecision] = []

        for batch_idx, batch_records in enumerate(batches):
            logger.info(
                "batch_progress",
                batch=batch_idx + 1,
                total=len(batches),
                batch_size=len(batch_records),
            )

            # Build batch prompt
            prompt = build_batch_screening_prompt(batch_records, criteria)
            prompt_hash = hash_prompt(prompt)

            async def _call_model_batch(
                backend: LLMBackend,
                _prompt: str = prompt,
                _hash: str = prompt_hash,
                _records: list[Record] = batch_records,
                _criteria: ReviewCriteria | PICOCriteria = criteria,
            ) -> list[ModelOutput]:
                """Call one model with batch prompt; fall back to individual calls on failure."""
                try:
                    from metascreener.llm.response_cache import (  # noqa: PLC0415
                        get_cached,
                        put_cached,
                    )

                    cached = get_cached(backend.model_id, _hash)
                    if cached is not None:
                        raw = cached
                    else:
                        raw = await backend._call_api(_prompt, seed=seed)
                        put_cached(backend.model_id, _hash, raw)
                    results = parse_batch_response(raw, _records, backend.model_id)
                    # Check if batch parse actually failed (all have error)
                    all_failed = all(o.error for o in results)
                    if not all_failed:
                        return results
                    # Fall through to individual calls
                    logger.info("batch_fallback_to_individual", model_id=backend.model_id, n_records=len(_records))
                except Exception as e:  # noqa: BLE001
                    logger.warning("batch_model_error", model_id=backend.model_id, error=str(e))

                # Fallback: call individually for each record
                from metascreener.module1_screening.layer1.prompts import PromptRouter  # noqa: PLC0415
                individual_router = PromptRouter()
                individual_results: list[ModelOutput] = []
                for rec in _records:
                    try:
                        ind_prompt = individual_router.build_prompt(rec, _criteria)
                        output = await backend.call_with_prompt(ind_prompt, seed=seed)
                        individual_results.append(output)
                    except Exception as ind_e:  # noqa: BLE001
                        individual_results.append(ModelOutput(
                            model_id=backend.model_id,
                            decision=Decision.INCLUDE,
                            score=0.5, confidence=0.0,
                            rationale=f"Individual fallback error: {ind_e}",
                            error=str(ind_e),
                        ))
                return individual_results

            model_results = await asyncio.gather(
                *[_call_model_batch(b) for b in self._backends]
            )
            # model_results: list[list[ModelOutput]] - [n_models][n_records_in_batch]

            # Transpose: for each record, collect outputs from all models
            for rec_idx, record in enumerate(batch_records):
                model_outputs = [
                    model_results[m][rec_idx] for m in range(len(self._backends))
                ]

                # Layers 2-4 (same as screen_single)
                rule_result = self._rules.check(record, criteria, model_outputs)
                s_final, c_ensemble = self._aggregator.aggregate(
                    model_outputs, rule_penalty=rule_result.total_penalty
                )
                decision, tier = self._router.route(
                    model_outputs, rule_result, s_final, c_ensemble
                )

                all_decisions.append(
                    ScreeningDecision(
                        record_id=record.record_id,
                        stage=ScreeningStage.TITLE_ABSTRACT,
                        decision=decision,
                        tier=tier,
                        final_score=s_final,
                        ensemble_confidence=c_ensemble,
                        model_outputs=model_outputs,
                        rule_result=rule_result,
                    )
                )

        return all_decisions

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
