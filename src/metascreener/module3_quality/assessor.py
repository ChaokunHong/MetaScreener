"""RoBAssessor orchestrator: chunk -> parallel LLM -> merge -> consensus."""
from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog

from metascreener.core.enums import RoBJudgement, StudyType
from metascreener.core.exceptions import LLMError
from metascreener.core.models import RoBDomainResult, RoBResult
from metascreener.llm.base import LLMBackend, hash_prompt, parse_llm_response
from metascreener.module2_extraction.pdf_chunker import chunk_text
from metascreener.module3_quality.prompts.rob_v1 import build_rob_prompt
from metascreener.module3_quality.tools import get_tool_for_study_type, get_tool_schema
from metascreener.module3_quality.tools.base import RoBToolSchema

logger = structlog.get_logger(__name__)


class RoBAssessor:
    """Orchestrator for multi-LLM risk of bias assessment.

    Pipeline:
    1. Auto-select tool by StudyType (or manual override)
    2. Chunk text (reuse pdf_chunker)
    3. Per-chunk x all models: parallel LLM assessment
    4. Merge chunks per model: worst-case judgement per domain
    5. Majority vote per domain across models
    6. Compute overall judgement via tool schema
    7. Flag disagreements for human review

    Args:
        backends: LLM backend instances (1-4 models).
        timeout_s: Per-call timeout in seconds.
        max_chunk_tokens: Maximum tokens per text chunk.
        overlap_tokens: Overlap between consecutive chunks.
    """

    def __init__(
        self,
        backends: Sequence[LLMBackend],
        timeout_s: float = 120.0,
        max_chunk_tokens: int = 6000,
        overlap_tokens: int = 200,
    ) -> None:
        if not backends:
            raise ValueError("At least one LLM backend is required.")
        self._backends = list(backends)
        self._timeout_s = timeout_s
        self._max_chunk_tokens = max_chunk_tokens
        self._overlap_tokens = overlap_tokens

    async def assess(
        self,
        text: str,
        tool_name: str,
        seed: int = 42,
    ) -> RoBResult:
        """Assess risk of bias using a specified tool.

        Args:
            text: Full text of the paper.
            tool_name: Tool identifier ('rob2', 'robins_i', 'quadas2').
            seed: Reproducibility seed.

        Returns:
            RoBResult with per-domain judgements and overall assessment.
        """
        tool_schema = get_tool_schema(tool_name)
        return await self._run_pipeline(text, tool_schema, seed)

    async def assess_auto(
        self,
        text: str,
        study_type: StudyType,
        seed: int = 42,
    ) -> RoBResult:
        """Assess risk of bias with auto-selected tool based on study type.

        Args:
            text: Full text of the paper.
            study_type: Study design classification.
            seed: Reproducibility seed.

        Returns:
            RoBResult with per-domain judgements and overall assessment.
        """
        tool_schema = get_tool_for_study_type(study_type)
        return await self._run_pipeline(text, tool_schema, seed)

    async def _run_pipeline(
        self,
        text: str,
        tool_schema: RoBToolSchema,
        seed: int,
    ) -> RoBResult:
        """Execute the full assessment pipeline.

        Args:
            text: Full paper text.
            tool_schema: The RoB tool schema to use.
            seed: Reproducibility seed.

        Returns:
            Complete RoBResult.
        """
        logger.info(
            "rob_assessment_start",
            tool=tool_schema.tool_name,
            n_backends=len(self._backends),
            text_len=len(text),
        )

        # Step 1: Chunk the text
        chunks = chunk_text(
            text,
            max_chunk_tokens=self._max_chunk_tokens,
            overlap_tokens=self._overlap_tokens,
        )
        logger.info("text_chunked", n_chunks=len(chunks))

        # Step 2: Assess all chunks x all models in parallel
        per_model_per_chunk = await self._assess_all_chunks(
            chunks, tool_schema, seed
        )

        # Step 3: Merge chunks per model (worst-case)
        per_model_merged = self._merge_chunks_worst_case(
            per_model_per_chunk, tool_schema
        )

        # Step 4: Majority vote across models per domain
        domain_results = self._compute_consensus(per_model_merged, tool_schema)

        # Step 5: Overall judgement
        domain_judgements = [d.judgement for d in domain_results]
        overall = tool_schema.get_overall_judgement(domain_judgements)

        # Step 6: Flag disagreements
        requires_review = any(not d.consensus_reached for d in domain_results)

        logger.info(
            "rob_assessment_complete",
            tool=tool_schema.tool_name,
            overall=overall.value,
            requires_review=requires_review,
        )

        return RoBResult(
            record_id="",  # Caller sets this
            tool=tool_schema.tool_name,
            domains=domain_results,
            overall_judgement=overall,
            requires_human_review=requires_review,
            assessed_at=datetime.now(UTC),
        )

    # --- Private helpers ---

    async def _assess_all_chunks(
        self,
        chunks: list[str],
        tool_schema: RoBToolSchema,
        seed: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """Assess all chunks x all models in parallel.

        Returns:
            model_id -> list of per-chunk parsed dicts.
        """
        tasks: list[asyncio.Task[dict[str, Any]]] = []
        task_keys: list[tuple[str, int]] = []

        for chunk_idx, chunk in enumerate(chunks):
            prompt = build_rob_prompt(tool_schema, chunk)
            for backend in self._backends:
                tasks.append(
                    asyncio.ensure_future(
                        self._assess_single(backend, prompt, seed)
                    )
                )
                task_keys.append((backend.model_id, chunk_idx))

        results = await asyncio.gather(*tasks)

        per_model: dict[str, list[dict[str, Any]]] = {
            b.model_id: [] for b in self._backends
        }
        for (model_id, _), result in zip(task_keys, results, strict=True):
            per_model[model_id].append(result)

        return per_model

    async def _assess_single(
        self,
        backend: LLMBackend,
        prompt: str,
        seed: int,
    ) -> dict[str, Any]:
        """Run a single assessment call with error handling.

        Returns:
            Parsed assessment dict, or empty dict on failure.
        """
        prompt_hash = hash_prompt(prompt)
        try:
            raw = await asyncio.wait_for(
                backend.complete(prompt, seed=seed),
                timeout=self._timeout_s,
            )
            parsed = parse_llm_response(raw, backend.model_id)
            logger.debug(
                "rob_call_ok",
                model_id=backend.model_id,
                prompt_hash=prompt_hash[:12],
            )
            return parsed
        except TimeoutError:
            logger.warning(
                "rob_timeout",
                model_id=backend.model_id,
                timeout_s=self._timeout_s,
            )
            return {}
        except LLMError as exc:
            logger.error(
                "rob_llm_error",
                model_id=backend.model_id,
                error=str(exc),
            )
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "rob_unexpected_error",
                model_id=backend.model_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return {}

    def _merge_chunks_worst_case(
        self,
        per_model_per_chunk: dict[str, list[dict[str, Any]]],
        tool_schema: RoBToolSchema,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Merge per-chunk assessments per model using worst-case strategy.

        For each domain per model, takes the most pessimistic judgement
        across chunks. This is methodologically correct: if any part of
        the paper suggests high risk, the domain should reflect that.

        Handles the ``domains`` wrapper key in LLM responses. The mock
        responses (and real LLM responses) may nest domain data under
        a ``domains`` key.

        Returns:
            model_id -> {domain_enum_value -> {judgement, rationale, quotes}}.
        """
        merged: dict[str, dict[str, dict[str, Any]]] = {}

        for model_id, chunk_results in per_model_per_chunk.items():
            domain_data: dict[str, dict[str, Any]] = {}

            for domain in tool_schema.domains:
                key = domain.domain.value
                worst_judgement: RoBJudgement | None = None
                worst_rank = -1
                best_rationale = ""
                all_quotes: list[str] = []

                for chunk_result in chunk_results:
                    # Handle "domains" wrapper key from LLM response
                    domain_dict = chunk_result.get("domains", chunk_result)
                    if key not in domain_dict:
                        continue
                    domain_result = domain_dict[key]
                    j_str = domain_result.get("judgement", "unclear")
                    try:
                        j = RoBJudgement(j_str)
                    except ValueError:
                        j = RoBJudgement.UNCLEAR

                    rank = tool_schema.get_severity_rank(j)
                    if rank > worst_rank:
                        worst_rank = rank
                        worst_judgement = j
                        best_rationale = domain_result.get("rationale", "")

                    quotes = domain_result.get("supporting_quotes", [])
                    if isinstance(quotes, list):
                        all_quotes.extend(quotes)

                domain_data[key] = {
                    "judgement": worst_judgement or RoBJudgement.UNCLEAR,
                    "rationale": best_rationale,
                    "supporting_quotes": all_quotes,
                }

            merged[model_id] = domain_data

        return merged

    def _compute_consensus(
        self,
        per_model_merged: dict[str, dict[str, dict[str, Any]]],
        tool_schema: RoBToolSchema,
    ) -> list[RoBDomainResult]:
        """Compute majority-vote consensus per domain across models.

        Returns:
            List of RoBDomainResult with consensus judgements.
        """
        n_models = len(per_model_merged)
        domain_results: list[RoBDomainResult] = []

        for domain in tool_schema.domains:
            key = domain.domain.value
            model_judgements: dict[str, RoBJudgement] = {}
            all_rationales: list[str] = []
            all_quotes: list[str] = []

            for model_id, domain_data in per_model_merged.items():
                data = domain_data.get(key, {})
                j = data.get("judgement", RoBJudgement.UNCLEAR)
                if isinstance(j, str):
                    try:
                        j = RoBJudgement(j)
                    except ValueError:
                        j = RoBJudgement.UNCLEAR
                model_judgements[model_id] = j

                rationale = data.get("rationale", "")
                if rationale:
                    all_rationales.append(rationale)
                quotes = data.get("supporting_quotes", [])
                if isinstance(quotes, list):
                    all_quotes.extend(quotes)

            # Majority vote
            judgement_values = list(model_judgements.values())
            counts: Counter[RoBJudgement] = Counter(judgement_values)
            consensus_j, consensus_count = counts.most_common(1)[0]
            consensus_reached = consensus_count > n_models / 2

            # Deduplicate quotes
            unique_quotes = list(dict.fromkeys(all_quotes))

            domain_results.append(
                RoBDomainResult(
                    domain=domain.domain,
                    judgement=consensus_j,
                    rationale=all_rationales[0] if all_rationales else "",
                    supporting_quotes=unique_quotes[:5],  # Limit to 5
                    model_judgements=model_judgements,
                    consensus_reached=consensus_reached,
                )
            )

        return domain_results
