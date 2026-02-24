"""Multi-LLM parallel data extraction engine.

Implements the chunk-then-merge strategy with majority-vote consensus
across multiple LLM backends. Designed for reproducible, auditable
data extraction in systematic reviews.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog

from metascreener.core.exceptions import LLMError
from metascreener.core.models import ExtractionResult
from metascreener.llm.base import LLMBackend, hash_prompt, parse_llm_response
from metascreener.module2_extraction.form_schema import ExtractionForm
from metascreener.module2_extraction.pdf_chunker import chunk_text
from metascreener.module2_extraction.prompts.extraction_v1 import build_extraction_prompt

logger = structlog.get_logger(__name__)


class ExtractionEngine:
    """Orchestrator for multi-LLM parallel data extraction.

    Implements the chunk-then-merge strategy:
    1. Split text into chunks
    2. For each chunk x each model: extract fields
    3. Merge chunks per model (take non-null values)
    4. Majority vote across models per field
    5. Flag discrepancies for human review

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

    async def extract(
        self,
        text: str,
        form: ExtractionForm,
        seed: int = 42,
    ) -> ExtractionResult:
        """Extract structured data from text using all backends.

        Args:
            text: Full text of the paper (from PDF).
            form: Extraction form defining fields to extract.
            seed: Reproducibility seed.

        Returns:
            ExtractionResult with consensus values and discrepancies.
        """
        logger.info(
            "extraction_start",
            n_backends=len(self._backends),
            n_fields=len(form.fields),
            text_len=len(text),
        )

        # Step 1: Chunk the text
        chunks = chunk_text(
            text,
            max_chunk_tokens=self._max_chunk_tokens,
            overlap_tokens=self._overlap_tokens,
        )
        logger.info("text_chunked", n_chunks=len(chunks))

        # Step 2: Extract from all chunks x all models in parallel
        per_model_per_chunk = await self._extract_all_chunks(chunks, form, seed)

        # Step 3: Merge chunks per model
        per_model_merged = self._merge_chunks(per_model_per_chunk)

        # Step 4: Majority vote across models
        consensus, discrepant, all_extracted = self._compute_consensus(
            per_model_merged, form
        )

        # Step 5: Identify required missing fields
        requires_review = bool(discrepant)
        for field_name, field_def in form.fields.items():
            if field_def.required and all_extracted.get(field_name) is None:
                if field_name not in discrepant:
                    discrepant.append(field_name)
                requires_review = True

        logger.info(
            "extraction_complete",
            n_consensus=len(consensus),
            n_discrepant=len(discrepant),
            requires_review=requires_review,
        )

        return ExtractionResult(
            record_id="",  # Caller sets this
            form_version=form.form_version,
            extracted_fields=all_extracted,
            model_outputs=per_model_merged,
            consensus_fields=consensus,
            discrepant_fields=discrepant,
            requires_human_review=requires_review,
            extracted_at=datetime.now(UTC),
        )

    async def _extract_all_chunks(
        self,
        chunks: list[str],
        form: ExtractionForm,
        seed: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """Extract from all chunks x all models in parallel.

        Args:
            chunks: Text chunks.
            form: Extraction form.
            seed: Reproducibility seed.

        Returns:
            Mapping of model_id -> list of per-chunk extraction dicts.
        """
        tasks: list[asyncio.Task[dict[str, Any]]] = []
        task_keys: list[tuple[str, int]] = []  # (model_id, chunk_index)

        for chunk_idx, chunk in enumerate(chunks):
            prompt = build_extraction_prompt(form, chunk)
            for backend in self._backends:
                tasks.append(
                    asyncio.ensure_future(
                        self._extract_single(backend, prompt, seed)
                    )
                )
                task_keys.append((backend.model_id, chunk_idx))

        results = await asyncio.gather(*tasks)

        # Group by model_id
        per_model: dict[str, list[dict[str, Any]]] = {
            b.model_id: [] for b in self._backends
        }
        for (model_id, _chunk_idx), result in zip(task_keys, results, strict=True):
            per_model[model_id].append(result)

        return per_model

    async def _extract_single(
        self,
        backend: LLMBackend,
        prompt: str,
        seed: int,
    ) -> dict[str, Any]:
        """Run a single extraction call with error handling.

        Args:
            backend: LLM backend to call.
            prompt: Complete extraction prompt.
            seed: Reproducibility seed.

        Returns:
            Parsed extraction dict, or empty dict on failure.
        """
        prompt_hash = hash_prompt(prompt)
        try:
            raw = await asyncio.wait_for(
                backend.complete(prompt, seed=seed),
                timeout=self._timeout_s,
            )
            parsed = parse_llm_response(raw, backend.model_id)
            logger.debug(
                "extraction_call_ok",
                model_id=backend.model_id,
                prompt_hash=prompt_hash[:12],
            )
            return parsed
        except TimeoutError:
            logger.warning(
                "extraction_timeout",
                model_id=backend.model_id,
                timeout_s=self._timeout_s,
            )
            return {}
        except LLMError as exc:
            logger.error(
                "extraction_llm_error",
                model_id=backend.model_id,
                error=str(exc),
            )
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "extraction_unexpected_error",
                model_id=backend.model_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return {}

    def _merge_chunks(
        self,
        per_model_per_chunk: dict[str, list[dict[str, Any]]],
    ) -> dict[str, dict[str, Any]]:
        """Merge per-chunk extractions into one dict per model.

        For each field, takes the first non-null value found across chunks.
        If multiple chunks have different non-null values, prefers the one
        with longer evidence text.

        Args:
            per_model_per_chunk: model_id -> list of per-chunk parsed dicts.

        Returns:
            model_id -> merged extraction dict with ``extracted_fields``
            and ``evidence`` sub-dicts.
        """
        merged: dict[str, dict[str, Any]] = {}

        for model_id, chunk_results in per_model_per_chunk.items():
            fields: dict[str, Any] = {}
            evidence: dict[str, str] = {}

            for chunk_result in chunk_results:
                chunk_fields = chunk_result.get("extracted_fields", {})
                chunk_evidence = chunk_result.get("evidence", {})

                for field_name, value in chunk_fields.items():
                    if value is None:
                        continue
                    existing = fields.get(field_name)
                    if existing is None:
                        fields[field_name] = value
                        if field_name in chunk_evidence:
                            evidence[field_name] = chunk_evidence[field_name]
                    elif existing != value:
                        # Prefer the value with longer evidence
                        new_ev = chunk_evidence.get(field_name, "")
                        old_ev = evidence.get(field_name, "")
                        if len(str(new_ev)) > len(str(old_ev)):
                            fields[field_name] = value
                            evidence[field_name] = new_ev

            merged[model_id] = {"extracted_fields": fields, "evidence": evidence}

        return merged

    def _compute_consensus(
        self,
        per_model_merged: dict[str, dict[str, Any]],
        form: ExtractionForm,
    ) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
        """Compute majority-vote consensus across models.

        Args:
            per_model_merged: model_id -> merged extraction dict.
            form: Extraction form (for field names).

        Returns:
            Tuple of (consensus_fields, discrepant_field_names,
            all_extracted_fields).
        """
        n_models = len(per_model_merged)
        consensus: dict[str, Any] = {}
        discrepant: list[str] = []
        all_extracted: dict[str, Any] = {}

        for field_name in form.fields:
            values: list[Any] = []
            for model_data in per_model_merged.values():
                fields = model_data.get("extracted_fields", {})
                val = fields.get(field_name)
                if val is not None:
                    values.append(val)

            if not values:
                all_extracted[field_name] = None
                continue

            if n_models == 1:
                # Single model: auto-accept
                all_extracted[field_name] = values[0]
                consensus[field_name] = values[0]
                continue

            # Majority vote
            majority_value = self._find_majority(values, n_models)
            if majority_value is not None:
                all_extracted[field_name] = majority_value
                consensus[field_name] = majority_value
            else:
                # No majority -- take first value but flag as discrepant
                all_extracted[field_name] = values[0]
                discrepant.append(field_name)

        return consensus, discrepant, all_extracted

    @staticmethod
    def _find_majority(values: list[Any], n_models: int) -> Any | None:  # noqa: ANN401
        """Find the majority value (> n/2 models agree).

        Args:
            values: Non-null values from models.
            n_models: Total number of models (including those returning null).

        Returns:
            The majority value, or None if no majority.
        """
        threshold = n_models / 2

        # Normalize values for comparison
        normalized: list[str] = []
        for v in values:
            if isinstance(v, bool):
                # Must check bool before int (bool is subclass of int)
                normalized.append(str(v))
            elif isinstance(v, str):
                normalized.append(v.strip().lower())
            elif isinstance(v, list):
                normalized.append(
                    str(tuple(sorted(str(x).strip().lower() for x in v)))
                )
            elif isinstance(v, (int, float)):
                # Normalize int/float to same representation (234 == 234.0)
                normalized.append(str(round(float(v), 6)))
            else:
                normalized.append(str(v))

        counts: Counter[str] = Counter(normalized)
        for norm_key, count in counts.most_common():
            if count > threshold:
                # Return original value (not normalized)
                for val, norm in zip(values, normalized, strict=True):
                    if norm == norm_key:
                        return val
        return None
