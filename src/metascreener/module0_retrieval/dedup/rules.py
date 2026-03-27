"""Rule-based deduplication matchers for Layers 1-5.

Each public function accepts a list of RawRecord objects and returns a list of
``(record_id_a, record_id_b)`` pairs that are considered duplicates.  Pairs are
emitted as (anchor, other) where anchor is the first record encountered in the
group; the engine uses union-find to merge transitively.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable

from metascreener.module0_retrieval.models import RawRecord

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_pairs_by_key(
    records: list[RawRecord],
    key_fn: Callable[[RawRecord], str | None],
) -> list[tuple[str, str]]:
    """Group records by the value returned by *key_fn* and emit duplicate pairs.

    Records for which *key_fn* returns ``None`` or an empty string are skipped.

    Args:
        records: All records to consider.
        key_fn: Function mapping a record to a normalised grouping key.

    Returns:
        List of ``(anchor_id, other_id)`` pairs — one pair per (anchor, duplicate).
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for rec in records:
        key = key_fn(rec)
        if key:
            groups[key].append(rec.record_id)

    pairs: list[tuple[str, str]] = []
    for ids in groups.values():
        if len(ids) < 2:
            continue
        anchor = ids[0]
        for other in ids[1:]:
            pairs.append((anchor, other))
    return pairs


# ---------------------------------------------------------------------------
# Layer 1 – DOI
# ---------------------------------------------------------------------------

_DOI_PREFIXES = re.compile(
    r"^(https?://doi\.org/|doi:)",
    re.IGNORECASE,
)


def _normalise_doi(doi: str) -> str:
    """Strip URL / ``doi:`` prefixes and lowercase.

    Args:
        doi: Raw DOI string, possibly with URL prefix.

    Returns:
        Normalised DOI string.
    """
    doi = doi.strip()
    doi = _DOI_PREFIXES.sub("", doi)
    return doi.lower()


def find_doi_duplicates(records: list[RawRecord]) -> list[tuple[str, str]]:
    """Layer 1: find duplicate pairs by normalised DOI.

    Args:
        records: Input bibliographic records.

    Returns:
        List of ``(anchor_id, duplicate_id)`` pairs.
    """
    return _find_pairs_by_key(
        records,
        lambda r: _normalise_doi(r.doi) if r.doi else None,
    )


# ---------------------------------------------------------------------------
# Layer 2 – PMID
# ---------------------------------------------------------------------------


def find_pmid_duplicates(records: list[RawRecord]) -> list[tuple[str, str]]:
    """Layer 2: find duplicate pairs by stripped PMID.

    Args:
        records: Input bibliographic records.

    Returns:
        List of ``(anchor_id, duplicate_id)`` pairs.
    """
    return _find_pairs_by_key(
        records,
        lambda r: r.pmid.strip() if r.pmid else None,
    )


# ---------------------------------------------------------------------------
# Layer 3 – PMCID
# ---------------------------------------------------------------------------


def _normalise_pmcid(pmcid: str) -> str:
    """Uppercase and ensure 'PMC' prefix.

    Args:
        pmcid: Raw PMCID, e.g. ``PMC1234567`` or ``1234567``.

    Returns:
        Normalised PMCID, e.g. ``PMC1234567``.
    """
    pmcid = pmcid.strip().upper()
    if not pmcid.startswith("PMC"):
        pmcid = "PMC" + pmcid
    return pmcid


def find_pmcid_duplicates(records: list[RawRecord]) -> list[tuple[str, str]]:
    """Layer 3: find duplicate pairs by case-insensitive PMCID.

    Args:
        records: Input bibliographic records.

    Returns:
        List of ``(anchor_id, duplicate_id)`` pairs.
    """
    return _find_pairs_by_key(
        records,
        lambda r: _normalise_pmcid(r.pmcid) if r.pmcid else None,
    )


# ---------------------------------------------------------------------------
# Layer 4 – External IDs
# ---------------------------------------------------------------------------


def find_external_id_duplicates(records: list[RawRecord]) -> list[tuple[str, str]]:
    """Layer 4: find duplicate pairs by OpenAlex, Scopus, or S2 ID.

    Each identifier type is matched independently; a single record may appear
    in multiple groups which the engine will unify via union-find.

    Args:
        records: Input bibliographic records.

    Returns:
        List of ``(anchor_id, duplicate_id)`` pairs (may contain duplicates
        across sub-lists — the engine deduplicates via union-find).
    """
    pairs: list[tuple[str, str]] = []
    pairs.extend(_find_pairs_by_key(records, lambda r: r.openalex_id or None))
    pairs.extend(_find_pairs_by_key(records, lambda r: r.scopus_id or None))
    pairs.extend(_find_pairs_by_key(records, lambda r: r.s2_id or None))
    return pairs


# ---------------------------------------------------------------------------
# Layer 5 – Title-Year
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_WHITESPACE = re.compile(r"\s+")


def _normalise_title(title: str) -> str:
    """Lowercase, strip accents, remove non-alphanumeric, collapse whitespace.

    Args:
        title: Raw title string.

    Returns:
        Normalised, whitespace-collapsed ASCII title.
    """
    # NFKD decomposition strips combining characters (accents)
    nfkd = unicodedata.normalize("NFKD", title)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    lower = ascii_str.lower()
    stripped = _NON_ALNUM.sub(" ", lower)
    return _WHITESPACE.sub(" ", stripped).strip()


def find_title_year_duplicates(records: list[RawRecord]) -> list[tuple[str, str]]:
    """Layer 5: find duplicates by normalised title with year ±1 tolerance.

    Two records match if their normalised titles are identical AND their years
    are both ``None`` or differ by at most 1.

    Args:
        records: Input bibliographic records.

    Returns:
        List of ``(anchor_id, duplicate_id)`` pairs.
    """
    pairs: list[tuple[str, str]] = []
    normalised = [(rec, _normalise_title(rec.title)) for rec in records]

    for i, (rec_a, norm_a) in enumerate(normalised):
        for rec_b, norm_b in normalised[i + 1 :]:
            if norm_a != norm_b:
                continue
            ya, yb = rec_a.year, rec_b.year
            if ya is None and yb is None:
                pairs.append((rec_a.record_id, rec_b.record_id))
            elif ya is not None and yb is not None and abs(ya - yb) <= 1:
                pairs.append((rec_a.record_id, rec_b.record_id))
            # Mixed None/int → no match
    return pairs
