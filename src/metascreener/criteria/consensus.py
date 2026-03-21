"""Multi-model consensus merger for criteria generation."""
from __future__ import annotations

from collections import Counter
from typing import Any

import structlog

from metascreener.core.enums import CriteriaFramework
from metascreener.core.models import CriteriaElement, ReviewCriteria
from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS

logger = structlog.get_logger(__name__)


class ConsensusMerger:
    """Merge criteria from multiple LLM outputs using exact-string consensus.

    Current implementation uses exact string matching for merging.
    Semantic deduplication via LLM is a future enhancement.
    """

    @staticmethod
    def _build_key_alias_map(
        framework: CriteriaFramework,
    ) -> dict[str, str]:
        """Build a mapping from common aliases to canonical element keys.

        Models may use single-letter keys (P, E, O), full names
        (population, exposure, outcome), or labels (Population, Exposure).
        This normalizes all to the canonical keys defined in FRAMEWORK_ELEMENTS.

        Args:
            framework: The criteria framework.

        Returns:
            Dict mapping alias (lowercased) -> canonical key.
        """
        defn = FRAMEWORK_ELEMENTS.get(framework)
        if defn is None:
            return {}

        alias_map: dict[str, str] = {}
        labels = defn.get("labels", {})
        for canonical_key, label in labels.items():
            # canonical key itself
            alias_map[canonical_key.lower()] = canonical_key
            # label (e.g., "Population" -> "population")
            alias_map[label.lower()] = canonical_key
            # first letter (e.g., "p" -> "population")
            first_letter = canonical_key[0].lower()
            # Only add single-letter alias if unambiguous
            if first_letter not in alias_map:
                alias_map[first_letter] = canonical_key

        return alias_map

    @staticmethod
    def _normalize_key(
        raw_key: str,
        alias_map: dict[str, str],
    ) -> str:
        """Normalize an element key using the alias map.

        Args:
            raw_key: Key from model output (e.g., "P", "population", "Population").
            alias_map: Alias -> canonical key mapping.

        Returns:
            Canonical key, or original key lowercased if no alias found.
        """
        return alias_map.get(raw_key.lower(), raw_key.lower())

    @staticmethod
    def merge(
        model_outputs: list[dict[str, Any]],
        framework: CriteriaFramework,
    ) -> ReviewCriteria:
        """Merge multiple model outputs into a single ReviewCriteria.

        Args:
            model_outputs: List of parsed JSON dicts from each model.
            framework: The detected or specified framework.

        Returns:
            Merged ReviewCriteria with model_votes populated.
        """
        n_models = len(model_outputs)
        if n_models == 0:
            return ReviewCriteria(framework=framework)

        if n_models == 1:
            return ConsensusMerger._single_model_result(model_outputs[0], framework)

        alias_map = ConsensusMerger._build_key_alias_map(framework)

        # Normalize element keys in all outputs before merging
        normalized_outputs: list[dict[str, Any]] = []
        for output in model_outputs:
            if not isinstance(output, dict):
                normalized_outputs.append(output)
                continue
            norm = dict(output)
            elements = output.get("elements", {})
            if isinstance(elements, dict):
                norm_elements: dict[str, Any] = {}
                for raw_key, value in elements.items():
                    canon_key = ConsensusMerger._normalize_key(raw_key, alias_map)
                    if canon_key in norm_elements:
                        # Merge into existing canonical element
                        existing = norm_elements[canon_key]
                        if isinstance(existing, dict) and isinstance(value, dict):
                            for t in value.get("include", []):
                                if t not in existing.get("include", []):
                                    existing.setdefault("include", []).append(t)
                            for t in value.get("exclude", []):
                                if t not in existing.get("exclude", []):
                                    existing.setdefault("exclude", []).append(t)
                    else:
                        norm_elements[canon_key] = value
                norm["elements"] = norm_elements
            normalized_outputs.append(norm)

        # Collect all element keys across normalized outputs
        all_element_keys: set[str] = set()
        for output in normalized_outputs:
            if not isinstance(output, dict):
                continue
            elements = output.get("elements", {})
            if isinstance(elements, dict):
                all_element_keys.update(elements.keys())

        # Merge each element
        merged_elements: dict[str, CriteriaElement] = {}
        for key in sorted(all_element_keys):
            merged_elements[key] = ConsensusMerger._merge_element(
                key, normalized_outputs, n_models
            )

        # Merge study designs
        merged_sd_include = ConsensusMerger._merge_list_field(
            model_outputs, "study_design_include"
        )
        merged_sd_exclude = ConsensusMerger._merge_list_field(
            model_outputs, "study_design_exclude"
        )

        # Take research question from first dict-type model output
        first_dict = next((o for o in model_outputs if isinstance(o, dict)), {})
        research_question = first_dict.get("research_question", "")

        required = ConsensusMerger._required_elements(framework, merged_elements)

        logger.info(
            "consensus_merged",
            n_models=n_models,
            n_elements=len(merged_elements),
        )

        return ReviewCriteria(
            framework=framework,
            research_question=research_question,
            elements=merged_elements,
            required_elements=required,
            study_design_include=merged_sd_include,
            study_design_exclude=merged_sd_exclude,
        )

    @staticmethod
    def _merge_element(
        key: str,
        model_outputs: list[dict[str, Any]],
        n_models: int,
    ) -> CriteriaElement:
        """Merge a single element across all models.

        Args:
            key: Element key (e.g., 'population').
            model_outputs: All model output dicts.
            n_models: Total number of models.

        Returns:
            Merged CriteriaElement with model_votes.
        """
        include_counter: Counter[str] = Counter()
        exclude_counter: Counter[str] = Counter()
        name = key.title()

        for output in model_outputs:
            element = output.get("elements", {}).get(key, {})
            if isinstance(element, dict):
                name = element.get("name", key.title())
                for term in element.get("include", []):
                    include_counter[term] += 1
                for term in element.get("exclude", []):
                    exclude_counter[term] += 1

        # Build model_votes: term -> agreement ratio
        model_votes: dict[str, float] = {}
        for term, count in include_counter.items():
            model_votes[term] = count / n_models
        for term, count in exclude_counter.items():
            model_votes[f"exclude:{term}"] = count / n_models

        return CriteriaElement(
            name=name,
            include=list(include_counter.keys()),
            exclude=list(exclude_counter.keys()),
            model_votes=model_votes,
        )

    @staticmethod
    def _merge_list_field(
        model_outputs: list[dict[str, Any]],
        field: str,
    ) -> list[str]:
        """Merge a list field (e.g., study_design_include) as union.

        Args:
            model_outputs: All model output dicts.
            field: Field name to merge.

        Returns:
            Deduplicated union of all values.
        """
        seen: set[str] = set()
        result: list[str] = []
        for output in model_outputs:
            if not isinstance(output, dict):
                continue
            for item in output.get(field, []):
                if item not in seen:
                    seen.add(item)
                    result.append(item)
        return result

    @staticmethod
    def _single_model_result(
        output: dict[str, Any],
        framework: CriteriaFramework,
    ) -> ReviewCriteria:
        """Convert a single model output to ReviewCriteria.

        Args:
            output: Parsed model output dict.
            framework: The framework to use.

        Returns:
            ReviewCriteria from a single model.
        """
        if not isinstance(output, dict):
            logger.warning("single_model_non_dict", type=type(output).__name__)
            return ReviewCriteria(framework=framework)

        alias_map = ConsensusMerger._build_key_alias_map(framework)
        elements: dict[str, CriteriaElement] = {}
        for raw_key, elem_data in output.get("elements", {}).items():
            if isinstance(elem_data, dict):
                key = ConsensusMerger._normalize_key(raw_key, alias_map)
                if key in elements:
                    # Merge into existing
                    for t in elem_data.get("include", []):
                        if t not in elements[key].include:
                            elements[key].include.append(t)
                    for t in elem_data.get("exclude", []):
                        if t not in elements[key].exclude:
                            elements[key].exclude.append(t)
                else:
                    defn = FRAMEWORK_ELEMENTS.get(framework)
                    label = defn["labels"].get(key, key.title()) if defn else key.title()
                    elements[key] = CriteriaElement(
                        name=elem_data.get("name", label),
                        include=elem_data.get("include", []),
                        exclude=elem_data.get("exclude", []),
                    )

        required = ConsensusMerger._required_elements(framework, elements)

        logger.info("single_model_result", n_elements=len(elements))
        return ReviewCriteria(
            framework=framework,
            research_question=output.get("research_question", ""),
            elements=elements,
            required_elements=required,
            study_design_include=output.get("study_design_include", []),
            study_design_exclude=output.get("study_design_exclude", []),
        )

    @staticmethod
    def _required_elements(
        framework: CriteriaFramework,
        elements: dict[str, CriteriaElement],
    ) -> list[str]:
        """Derive required_elements from the framework definition.

        Returns the intersection of framework-required keys and actually
        present element keys.

        Args:
            framework: The criteria framework.
            elements: The merged element dict.

        Returns:
            List of required element keys present in elements.
        """
        defn = FRAMEWORK_ELEMENTS.get(framework)
        if defn is None:
            return list(elements.keys())
        fw_required = defn.get("required", [])
        # Only include keys that are actually present
        return [k for k in fw_required if k in elements]
