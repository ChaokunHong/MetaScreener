"""DedupEngine: orchestrates all 6 deduplication layers using union-find.

Pipeline:
    1. Run each layer function (Layers 1-5 always; Layer 6 optional).
    2. Union-find merges duplicate pairs; each new merge emits a MergeEvent.
    3. Records are grouped by union-find root and merged into canonical records.
    4. Returns a DedupResult with merged records, audit log, and layer counts.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog

from metascreener.module0_retrieval.models import DedupResult, MergeEvent, RawRecord
from metascreener.module0_retrieval.dedup.rules import (
    find_doi_duplicates,
    find_external_id_duplicates,
    find_pmcid_duplicates,
    find_pmid_duplicates,
    find_title_year_duplicates,
)
from metascreener.module0_retrieval.dedup.semantic import find_semantic_duplicates

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------


class _UnionFind:
    """Path-compressed, union-by-rank disjoint-set structure over string keys.

    The ``union`` method returns ``True`` when the two elements were in
    different components and have been merged, ``False`` otherwise (including
    when both ids are identical).
    """

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def _ensure(self, x: str) -> None:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0

    def find(self, x: str) -> str:
        """Return the root of *x*'s component with path compression."""
        self._ensure(x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path halving
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> bool:
        """Merge the components containing *a* and *b*.

        Args:
            a: First element id.
            b: Second element id.

        Returns:
            ``True`` if a merge actually occurred (different components),
            ``False`` if they were already in the same component.
        """
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1
        return True

    def groups(self, ids: list[str]) -> dict[str, list[str]]:
        """Return a mapping from root → list of members for the given ids.

        Args:
            ids: All element ids to group.

        Returns:
            Dict mapping each root id to the list of member ids.
        """
        result: dict[str, list[str]] = defaultdict(list)
        for id_ in ids:
            result[self.find(id_)].append(id_)
        return dict(result)


# ---------------------------------------------------------------------------
# Record merging
# ---------------------------------------------------------------------------


def _merge_records(records: list[RawRecord]) -> RawRecord:
    """Merge a group of duplicate records into a single canonical record.

    Selection rules:
    - **title**: longest string
    - **abstract**: longest non-None string (or None if all absent)
    - **authors**: list with most entries
    - **scalar IDs** (doi, pmid, pmcid, openalex_id, scopus_id, s2_id,
      journal, language): first non-None value across the group
    - **pdf_urls**: deduplicated union preserving insertion order
    - **source_db**: all unique values joined with ``"+"``
    - **year**, **keywords**, **raw_data**: from the record with the longest title

    Args:
        records: Non-empty list of records forming one duplicate cluster.

    Returns:
        A single merged RawRecord.
    """
    if len(records) == 1:
        return records[0]

    # Canonical anchor = record with the longest title (stable sort)
    anchor = max(records, key=lambda r: len(r.title))

    def _first_non_none(attr: str) -> Any:
        for rec in records:
            val = getattr(rec, attr)
            if val is not None:
                return val
        return None

    def _longest_str(attr: str) -> str | None:
        candidates = [getattr(r, attr) for r in records if getattr(r, attr) is not None]
        if not candidates:
            return None
        return max(candidates, key=len)

    def _most_authors() -> list[str]:
        best: list[str] = []
        for rec in records:
            if len(rec.authors) > len(best):
                best = rec.authors
        return best

    # Build deduplicated pdf_urls preserving order
    seen_urls: set[str] = set()
    merged_urls: list[str] = []
    for rec in records:
        for url in rec.pdf_urls:
            if url not in seen_urls:
                seen_urls.add(url)
                merged_urls.append(url)

    # Unique source_db values joined with "+"
    seen_dbs: set[str] = set()
    ordered_dbs: list[str] = []
    for rec in records:
        for part in rec.source_db.split("+"):
            part = part.strip()
            if part and part not in seen_dbs:
                seen_dbs.add(part)
                ordered_dbs.append(part)
    merged_source = "+".join(ordered_dbs)

    return RawRecord(
        record_id=anchor.record_id,
        title=max(records, key=lambda r: len(r.title)).title,
        abstract=_longest_str("abstract"),
        authors=_most_authors(),
        source_db=merged_source,
        year=anchor.year,
        doi=_first_non_none("doi"),
        pmid=_first_non_none("pmid"),
        pmcid=_first_non_none("pmcid"),
        openalex_id=_first_non_none("openalex_id"),
        scopus_id=_first_non_none("scopus_id"),
        s2_id=_first_non_none("s2_id"),
        journal=_first_non_none("journal"),
        language=_first_non_none("language"),
        pdf_urls=merged_urls,
        keywords=anchor.keywords,
        raw_data=anchor.raw_data,
    )


# ---------------------------------------------------------------------------
# Layer descriptor
# ---------------------------------------------------------------------------

_LAYER_DESCRIPTORS: dict[int, tuple[str, str]] = {
    1: ("doi", "doi"),
    2: ("pmid", "pmid"),
    3: ("pmcid", "pmcid"),
    4: ("external_id", "openalex/scopus/s2"),
    5: ("title_year", "title+year"),
    6: ("semantic", "title embedding"),
}


# ---------------------------------------------------------------------------
# DedupEngine
# ---------------------------------------------------------------------------


class DedupEngine:
    """Orchestrates all 6 deduplication layers using union-find.

    Args:
        enable_semantic: Whether to run Layer 6 (sentence-embedding cosine
            similarity).  Disable in tests / resource-constrained environments.
        semantic_threshold: Cosine similarity threshold for Layer 6.
        semantic_model: Pre-loaded sentence-transformer model (optional).  If
            ``None`` and *enable_semantic* is ``True``, the engine will attempt
            to load ``all-MiniLM-L6-v2`` at runtime.
    """

    def __init__(
        self,
        enable_semantic: bool = True,
        semantic_threshold: float = 0.95,
        semantic_model: Any | None = None,
    ) -> None:
        self.enable_semantic = enable_semantic
        self.semantic_threshold = semantic_threshold
        self.semantic_model = semantic_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deduplicate(self, records: list[RawRecord]) -> DedupResult:
        """Run the full 6-layer deduplication pipeline.

        Args:
            records: Raw bibliographic records, possibly containing duplicates.

        Returns:
            A :class:`~metascreener.module0_retrieval.models.DedupResult`
            containing the merged canonical records, a full audit log of every
            merge event, and per-layer merge counts.
        """
        original_count = len(records)

        if not records:
            return DedupResult(
                records=[],
                merge_log=[],
                original_count=0,
                deduped_count=0,
                per_layer_counts={},
            )

        uf = _UnionFind()
        merge_log: list[MergeEvent] = []
        per_layer_counts: dict[int, int] = {}

        # Initialise every record_id in the union-find
        for rec in records:
            uf.find(rec.record_id)

        # Layer function registry (layer_number → (finder_fn, match_key_label))
        layer_fns: list[tuple[int, Any]] = [
            (1, find_doi_duplicates),
            (2, find_pmid_duplicates),
            (3, find_pmcid_duplicates),
            (4, find_external_id_duplicates),
            (5, find_title_year_duplicates),
        ]

        if self.enable_semantic:
            layer_fns.append((6, None))  # handled separately below

        # Run Layers 1-5
        for layer_num, fn in layer_fns:
            if fn is None:
                continue
            pairs = fn(records)
            match_key, match_value_label = _LAYER_DESCRIPTORS[layer_num]
            count = 0
            for id_a, id_b in pairs:
                merged = uf.union(id_a, id_b)
                if merged:
                    count += 1
                    merge_log.append(
                        MergeEvent(
                            kept_id=uf.find(id_a),
                            merged_id=id_b if uf.find(id_b) != id_b else id_a,
                            layer=layer_num,
                            match_key=match_key,
                            match_value=match_value_label,
                        )
                    )
            if count:
                per_layer_counts[layer_num] = count

        # Layer 6 – semantic (optional)
        if self.enable_semantic:
            semantic_pairs = find_semantic_duplicates(
                records,
                model=self.semantic_model,
                threshold=self.semantic_threshold,
            )
            count = 0
            for id_a, id_b in semantic_pairs:
                merged = uf.union(id_a, id_b)
                if merged:
                    count += 1
                    merge_log.append(
                        MergeEvent(
                            kept_id=uf.find(id_a),
                            merged_id=id_b if uf.find(id_b) != id_b else id_a,
                            layer=6,
                            match_key="semantic",
                            match_value="title embedding",
                        )
                    )
            if count:
                per_layer_counts[6] = count

        # Group records by their union-find root
        id_to_record = {rec.record_id: rec for rec in records}
        all_ids = [rec.record_id for rec in records]
        groups = uf.groups(all_ids)

        canonical_records: list[RawRecord] = []
        for _root, member_ids in groups.items():
            group_records = [id_to_record[mid] for mid in member_ids]
            canonical_records.append(_merge_records(group_records))

        log.info(
            "dedup complete",
            original=original_count,
            deduped=len(canonical_records),
            merges=len(merge_log),
            layer_counts=per_layer_counts,
        )

        return DedupResult(
            records=canonical_records,
            merge_log=merge_log,
            original_count=original_count,
            deduped_count=len(canonical_records),
            per_layer_counts=per_layer_counts,
        )
