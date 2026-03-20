"""DedupMerger: semantic deduplication via union-find and pairwise edge voting.

Implements a multi-model consensus approach to term deduplication:
1. Aggregate pairwise duplicate edges from all model evaluations.
2. Confirm edges that meet a voting quorum.
3. Merge confirmed duplicates via union-find into canonical terms.
4. Generate ambiguity flags for sub-quorum and low-agreement terms.
5. Compute per-element quality scores from model evaluations.
"""
from __future__ import annotations

import copy
from collections import Counter
from math import ceil
from statistics import median
from typing import Any

import structlog

from metascreener.core.models import ReviewCriteria
from metascreener.criteria.models import DedupResult

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Union-Find (Disjoint Set)
# ---------------------------------------------------------------------------


class UnionFind:
    """Disjoint set data structure with path compression and union by rank.

    Supports string keys. Elements are lazily initialised on first access.
    """

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def find(self, x: str) -> str:
        """Return the root representative of the set containing *x*.

        Uses path compression for amortised near-constant time.

        Args:
            x: Element to look up.

        Returns:
            Root representative of the component.
        """
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        """Merge the sets containing *x* and *y*.

        Uses union by rank to keep trees shallow.

        Args:
            x: First element.
            y: Second element.
        """
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def components(self) -> list[set[str]]:
        """Return all disjoint components as a list of sets.

        Returns:
            List of sets, each containing the elements of one component.
        """
        groups: dict[str, set[str]] = {}
        for item in self._parent:
            root = self.find(item)
            groups.setdefault(root, set()).add(item)
        return list(groups.values())


# ---------------------------------------------------------------------------
# Quorum
# ---------------------------------------------------------------------------


def compute_dedup_quorum(n_models: int, fraction: float) -> int:
    """Compute the minimum vote count to confirm a dedup edge.

    Args:
        n_models: Total number of models that participated.
        fraction: Required agreement fraction (e.g. 0.5 for majority).

    Returns:
        Quorum value: ``max(2, ceil(n_models * fraction))``.
    """
    return max(2, ceil(n_models * fraction))


# ---------------------------------------------------------------------------
# Edge aggregation
# ---------------------------------------------------------------------------


def aggregate_dedup_edges(
    round2_evals: dict[str, Any],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """Collect pairwise dedup edges from all model evaluations.

    Each edge key is canonically ordered as
    ``(element_key, polarity, min(term_a, term_b), max(term_a, term_b))``
    so that reversed term pairs map to the same key.

    Args:
        round2_evals: Mapping of ``model_id`` to evaluation dict.
            Each eval dict should contain ``"dedup_edges"``: a list of
            edge dicts with keys ``element``, ``polarity``, ``term_a``,
            ``term_b``, ``is_duplicate``, ``preferred``.

    Returns:
        Dict mapping canonical edge key to
        ``{"votes": int, "preferred": Counter}``.
    """
    edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for _model_id, eval_data in round2_evals.items():
        for edge in eval_data.get("dedup_edges", []):
            if not edge.get("is_duplicate", False):
                continue
            term_a = edge["term_a"]
            term_b = edge["term_b"]
            lo, hi = (min(term_a, term_b), max(term_a, term_b))
            key = (edge["element"], edge["polarity"], lo, hi)

            if key not in edges:
                edges[key] = {"votes": 0, "preferred": Counter()}
            edges[key]["votes"] += 1
            edges[key]["preferred"][edge["preferred"]] += 1

    return edges


# ---------------------------------------------------------------------------
# DedupMerger
# ---------------------------------------------------------------------------


class DedupMerger:
    """Semantic deduplication merger using union-find and edge voting.

    Args:
        dedup_quorum_fraction: Fraction of models required to confirm
            a duplicate pair. Default ``0.5``.
    """

    def __init__(self, dedup_quorum_fraction: float = 0.5) -> None:
        self._quorum_fraction = dedup_quorum_fraction

    def merge(
        self,
        criteria: ReviewCriteria,
        round2_evals: dict[str, Any],
        term_origin: dict[str, dict[str, dict[str, list[str]]]],
    ) -> DedupResult:
        """Apply deduplication to *criteria* based on model evaluations.

        Args:
            criteria: Input criteria (will be deep-copied before mutation).
            round2_evals: Per-model cross-evaluation results.
            term_origin: ``element -> polarity -> term -> [model_ids]``.

        Returns:
            A :class:`DedupResult` with deduplicated criteria, logs,
            quality scores, and corrected term_origin.
        """
        # Graceful degradation: empty evals → return unchanged copy
        if not round2_evals:
            return DedupResult(
                criteria=criteria.model_copy(deep=True),
                dedup_log=[],
                quality_scores={},
                corrected_term_origin=copy.deepcopy(term_origin),
            )

        n_models = len(round2_evals)
        quorum = compute_dedup_quorum(n_models, self._quorum_fraction)

        # Step 1: aggregate edges
        all_edges = aggregate_dedup_edges(round2_evals)

        # Partition into confirmed and sub-quorum
        confirmed: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        sub_quorum: list[tuple[str, str, str, str]] = []
        for key, data in all_edges.items():
            if data["votes"] >= quorum:
                confirmed[key] = data
            else:
                sub_quorum.append(key)

        # Step 2: build union-find per (element, polarity)
        canonical_map = self._build_canonical_map(confirmed)

        # Step 3: deep copy and apply dedup
        result_criteria = criteria.model_copy(deep=True)
        dedup_log: list[dict[str, Any]] = []
        self._apply_dedup(result_criteria, canonical_map, dedup_log)

        # Step 4: ambiguity flags
        self._add_ambiguity_flags(
            result_criteria, sub_quorum, term_origin, n_models,
        )

        # Step 5: quality scores
        quality_scores = self._compute_quality_scores(round2_evals)

        # Step 6: retroactive term_origin correction
        corrected_origin = self._correct_term_origin(
            term_origin, canonical_map,
        )

        # Step 7: set element_quality on elements
        for elem_key, score in quality_scores.items():
            if elem_key in result_criteria.elements:
                result_criteria.elements[elem_key].element_quality = score

        logger.info(
            "dedup_merger.complete",
            confirmed_edges=len(confirmed),
            sub_quorum_edges=len(sub_quorum),
            quality_scores=quality_scores,
        )

        return DedupResult(
            criteria=result_criteria,
            dedup_log=dedup_log,
            quality_scores=quality_scores,
            corrected_term_origin=corrected_origin,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_canonical_map(
        confirmed: dict[tuple[str, str, str, str], dict[str, Any]],
    ) -> dict[tuple[str, str], dict[str, str]]:
        """Build a mapping from old term to canonical term per (element, polarity).

        Returns:
            ``(element, polarity) -> {old_term: canonical_term}``
        """
        # Group edges by (element, polarity)
        groups: dict[tuple[str, str], list[tuple[str, str, dict[str, Any]]]] = {}
        for (elem, pol, lo, hi), data in confirmed.items():
            groups.setdefault((elem, pol), []).append((lo, hi, data))

        result: dict[tuple[str, str], dict[str, str]] = {}
        for (elem, pol), edge_list in groups.items():
            uf = UnionFind()
            preferred_counter: dict[str, Counter[str]] = {}

            for lo, hi, data in edge_list:
                uf.union(lo, hi)
                # Track preferred per component
                for term in (lo, hi):
                    root = uf.find(term)
                    if root not in preferred_counter:
                        preferred_counter[root] = Counter()
                    preferred_counter[root] += data["preferred"]

            # For each component, pick canonical = most-preferred, ties alphabetical
            mapping: dict[str, str] = {}
            for component in uf.components():
                root = uf.find(next(iter(component)))
                counter = preferred_counter.get(root, Counter())
                if counter:
                    max_count = max(counter.values())
                    candidates = sorted(
                        t for t, c in counter.items() if c == max_count
                    )
                    canonical = candidates[0]
                else:
                    canonical = sorted(component)[0]

                for term in component:
                    if term != canonical:
                        mapping[term] = canonical

            if mapping:
                result[(elem, pol)] = mapping

        return result

    @staticmethod
    def _apply_dedup(
        criteria: ReviewCriteria,
        canonical_map: dict[tuple[str, str], dict[str, str]],
        dedup_log: list[dict[str, Any]],
    ) -> None:
        """Replace duplicate terms with canonical and deduplicate lists in place."""
        for (elem_key, polarity), mapping in canonical_map.items():
            if elem_key not in criteria.elements:
                continue
            elem = criteria.elements[elem_key]
            term_list: list[str] = getattr(elem, polarity, [])

            new_terms: list[str] = []
            seen: set[str] = set()
            for term in term_list:
                canonical = mapping.get(term, term)
                if canonical not in seen:
                    new_terms.append(canonical)
                    seen.add(canonical)
                if term in mapping:
                    dedup_log.append({
                        "element": elem_key,
                        "polarity": polarity,
                        "original": term,
                        "canonical": canonical,
                        "action": "merged",
                    })

            setattr(elem, polarity, new_terms)

    @staticmethod
    def _add_ambiguity_flags(
        criteria: ReviewCriteria,
        sub_quorum: list[tuple[str, str, str, str]],
        term_origin: dict[str, dict[str, dict[str, list[str]]]],
        n_models: int,
    ) -> None:
        """Add ambiguity flags for sub-quorum pairs and low-agreement terms."""
        # Sub-quorum duplicate flags
        for elem_key, _polarity, lo, hi in sub_quorum:
            if elem_key in criteria.elements:
                flag = f"possible duplicate: {lo} ~ {hi}"
                elem = criteria.elements[elem_key]
                if flag not in elem.ambiguity_flags:
                    elem.ambiguity_flags.append(flag)

        # Low agreement flags: terms from only 1 of N models
        for elem_key, polarities in term_origin.items():
            if elem_key not in criteria.elements:
                continue
            elem = criteria.elements[elem_key]
            for polarity in ("include", "exclude"):
                terms = polarities.get(polarity, {})
                for term, model_ids in terms.items():
                    if len(model_ids) == 1 and n_models > 1:
                        flag = (
                            f"low agreement: {term} "
                            f"({len(model_ids)}/{n_models} models)"
                        )
                        if flag not in elem.ambiguity_flags:
                            elem.ambiguity_flags.append(flag)

    @staticmethod
    def _compute_quality_scores(
        round2_evals: dict[str, Any],
    ) -> dict[str, int]:
        """Compute per-element quality: ``int(median(per-model means) * 10)``.

        Each model may provide a ``"quality"`` dict mapping element keys
        to ``{"precision": float, "completeness": float, "actionability": float}``.
        """
        # Collect per-element per-model scores
        elem_scores: dict[str, list[float]] = {}

        for _model_id, eval_data in round2_evals.items():
            quality = eval_data.get("quality", {})
            for elem_key, scores in quality.items():
                if not isinstance(scores, dict):
                    continue
                values = [
                    scores.get("precision", 0.0),
                    scores.get("completeness", 0.0),
                    scores.get("actionability", 0.0),
                ]
                mean_score = sum(values) / len(values)
                elem_scores.setdefault(elem_key, []).append(mean_score)

        result: dict[str, int] = {}
        for elem_key, scores in elem_scores.items():
            # Convert to 0-100 scale: round(median(means) * 10)
            result[elem_key] = round(median(scores) * 10)

        return result

    @staticmethod
    def _correct_term_origin(
        term_origin: dict[str, dict[str, dict[str, list[str]]]],
        canonical_map: dict[tuple[str, str], dict[str, str]],
    ) -> dict[str, dict[str, dict[str, list[str]]]]:
        """Retroactively correct term_origin so canonical terms inherit contributors."""
        corrected = copy.deepcopy(term_origin)

        for (elem_key, polarity), mapping in canonical_map.items():
            if elem_key not in corrected:
                continue
            pol_dict = corrected[elem_key].get(polarity, {})

            for old_term, canonical in mapping.items():
                # Merge contributors from old_term into canonical
                old_contributors = pol_dict.pop(old_term, [])
                if canonical not in pol_dict:
                    pol_dict[canonical] = []
                for model_id in old_contributors:
                    if model_id not in pol_dict[canonical]:
                        pol_dict[canonical].append(model_id)

        return corrected
