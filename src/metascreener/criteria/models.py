"""Intermediate data models for the criteria generation pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import ReviewCriteria


@dataclass
class GenerationResult:
    """Intermediate result from criteria generation pipeline.

    Attributes:
        raw_merged: Merged criteria from ConsensusMerger.
        per_model_outputs: Raw parsed JSON from each backend.
        term_origin: Mapping of element -> polarity -> term -> [model_ids].
        round2_evaluations: Per-model cross-eval results (None if skipped/failed).
    """

    raw_merged: ReviewCriteria
    per_model_outputs: list[dict[str, Any]] = field(default_factory=list)
    term_origin: dict[str, dict[str, dict[str, list[str]]]] = field(
        default_factory=dict
    )
    round2_evaluations: dict[str, Any] | None = None


@dataclass
class DedupResult:
    """Result from DedupMerger.merge().

    Attributes:
        criteria: Final ReviewCriteria with dedup applied.
        dedup_log: List of merge decisions for audit trail.
        quality_scores: Per-element quality scores (element_key -> 0-100).
        corrected_term_origin: term_origin after retroactive dedup correction.
    """

    criteria: ReviewCriteria
    dedup_log: list[dict[str, Any]] = field(default_factory=list)
    quality_scores: dict[str, int] = field(default_factory=dict)
    corrected_term_origin: dict[str, dict[str, dict[str, list[str]]]] = field(
        default_factory=dict
    )


def build_term_origin(
    per_model_outputs: list[dict[str, Any]],
    model_ids: list[str],
    framework: CriteriaFramework | None = None,
) -> dict[str, dict[str, dict[str, list[str]]]]:
    """Build term_origin mapping from per-model parsed outputs.

    Args:
        per_model_outputs: Raw parsed JSON dicts from each model.
        model_ids: Corresponding model identifiers (same order).
        framework: Optional framework for normalizing raw element keys
            (e.g. "P" → "population", "I" → "intervention").

    Returns:
        Nested dict: element_key -> polarity -> term -> [model_ids].
        Polarity is "include" or "exclude".
    """
    from metascreener.criteria.consensus import ConsensusMerger  # noqa: PLC0415

    alias_map: dict[str, str] = {}
    if framework is not None:
        alias_map = ConsensusMerger._build_key_alias_map(framework)

    origin: dict[str, dict[str, dict[str, list[str]]]] = {}

    for output, model_id in zip(per_model_outputs, model_ids, strict=True):
        elements = output.get("elements", {})
        if not isinstance(elements, dict):
            continue
        for raw_key, elem_data in elements.items():
            if not isinstance(elem_data, dict):
                continue
            key = alias_map.get(raw_key.lower(), raw_key.lower()) if alias_map else raw_key
            if key not in origin:
                origin[key] = {"include": {}, "exclude": {}}
            for polarity in ("include", "exclude"):
                for term in elem_data.get(polarity, []):
                    if term not in origin[key][polarity]:
                        origin[key][polarity][term] = []
                    if model_id not in origin[key][polarity][term]:
                        origin[key][polarity][term].append(model_id)

    return origin
