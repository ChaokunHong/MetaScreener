"""Record normalisation -- raw format-specific dicts to Record objects."""
from __future__ import annotations

import re
from typing import Any

import structlog

from metascreener.core.models import Record

logger = structlog.get_logger(__name__)

# ---------- RIS field mapping (rispy dict keys) ----------

RIS_FIELD_MAP: dict[str, str] = {
    "type_of_reference": "_study_type",
    "title": "title",
    "primary_title": "title",
    "abstract": "abstract",
    "notes_abstract": "abstract",
    "authors": "authors",
    "first_authors": "authors",
    "year": "year",
    "publication_year": "year",
    "doi": "doi",
    "accession_number": "pmid",
    "journal_name": "journal",
    "alternate_title3": "journal",
    "keywords": "keywords",
    "language": "language",
}

# ---------- BibTeX field mapping ----------

BIBTEX_FIELD_MAP: dict[str, str] = {
    "title": "title",
    "abstract": "abstract",
    "author": "authors",
    "year": "year",
    "doi": "doi",
    "journal": "journal",
    "keywords": "keywords",
    "language": "language",
    "pmid": "pmid",
}

# ---------- CSV fuzzy column matching ----------

CSV_COLUMN_ALIASES: dict[str, list[str]] = {
    "title": ["title", "ti", "article_title", "article title"],
    "abstract": ["abstract", "ab", "n2", "summary"],
    "authors": ["authors", "author", "au", "a1"],
    "year": ["year", "py", "publication_year", "pub_year", "date"],
    "doi": ["doi", "do", "digital_object_identifier"],
    "pmid": ["pmid", "an", "pubmed_id", "accession_number"],
    "journal": ["journal", "jo", "journal_name", "source"],
    "keywords": ["keywords", "kw", "mesh_terms"],
    "language": ["language", "la", "lang"],
    "record_id": ["record_id", "id", "accession", "uid"],
}

_YEAR_RE = re.compile(r"((?:19|20)\d{2})")


def normalize_record(
    raw: dict[str, Any],
    format_type: str,
    source_file: str | None = None,
) -> Record:
    """Normalise a raw record dict from any format into a Record.

    Args:
        raw: Raw key-value pairs from a format-specific parser.
        format_type: Source format identifier ("ris", "bibtex", "csv", "xml",
            "excel").
        source_file: Path to the original source file.

    Returns:
        Normalised Record instance.
    """
    if format_type == "ris":
        mapped = _map_fields(raw, RIS_FIELD_MAP)
    elif format_type == "bibtex":
        mapped = _map_fields(raw, BIBTEX_FIELD_MAP)
    elif format_type in ("csv", "excel"):
        mapped = _resolve_csv_columns(raw)
    elif format_type == "xml":
        mapped = dict(raw)
    else:
        mapped = dict(raw)

    title = str(mapped.get("title", "")).strip()
    if not title:
        title = "[Untitled]"

    # Build kwargs conditionally -- record_id uses default_factory so we
    # must NOT pass it when it's absent from the mapped data.
    kwargs: dict[str, Any] = {
        "title": title,
        "abstract": _str_or_none(mapped.get("abstract")),
        "authors": _split_authors(mapped.get("authors"), format_type),
        "year": _parse_year(mapped.get("year")),
        "doi": _str_or_none(mapped.get("doi")),
        "pmid": _str_or_none(mapped.get("pmid")),
        "journal": _str_or_none(mapped.get("journal")),
        "keywords": _split_keywords(mapped.get("keywords")),
        "language": _str_or_none(mapped.get("language")),
        "source_file": source_file,
        "raw_data": raw,
    }

    if "record_id" in mapped and mapped["record_id"]:
        kwargs["record_id"] = str(mapped["record_id"])

    return Record(**kwargs)


def _map_fields(raw: dict[str, Any], field_map: dict[str, str]) -> dict[str, Any]:
    """Map raw keys to canonical field names using a mapping table.

    First match wins -- earlier keys in field_map have priority.

    Args:
        raw: Raw key-value dict.
        field_map: Mapping from raw key to canonical field name.

    Returns:
        Dict with canonical field names.
    """
    mapped: dict[str, Any] = {}
    for raw_key, canonical in field_map.items():
        if canonical.startswith("_"):
            continue
        if raw_key in raw and raw[raw_key] and canonical not in mapped:
            mapped[canonical] = raw[raw_key]
    return mapped


def _resolve_csv_columns(raw: dict[str, Any]) -> dict[str, Any]:
    """Map CSV column names to canonical field names via fuzzy matching.

    Args:
        raw: Raw CSV row dict (keys are column headers).

    Returns:
        Dict with canonical field names.
    """
    resolved: dict[str, Any] = {}
    lower_map = {k.lower().strip(): v for k, v in raw.items()}

    for canonical, aliases in CSV_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_map and lower_map[alias]:
                resolved[canonical] = lower_map[alias]
                break

    return resolved


def _parse_year(value: Any) -> int | None:  # noqa: ANN401
    """Extract 4-digit year from various formats.

    Args:
        value: Raw year value (str, int, or None).

    Returns:
        Integer year or None if unparseable.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    m = _YEAR_RE.search(str(value))
    return int(m.group(1)) if m else None


def _split_authors(value: Any, format_type: str) -> list[str]:  # noqa: ANN401
    """Split author string into list based on format conventions.

    Args:
        value: Raw author value (str, list, or None).
        format_type: Source format ("ris", "bibtex", "csv", "xml", "excel").

    Returns:
        List of author name strings.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(a).strip() for a in value if str(a).strip()]
    text = str(value)
    if format_type == "bibtex":
        return [a.strip() for a in text.split(" and ") if a.strip()]
    return [a.strip() for a in text.split(";") if a.strip()]


def _split_keywords(value: Any) -> list[str]:  # noqa: ANN401
    """Split keywords string into list.

    Args:
        value: Raw keywords value (str, list, or None).

    Returns:
        List of keyword strings.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(k).strip() for k in value if str(k).strip()]
    text = str(value)
    sep = ";" if ";" in text else ","
    return [k.strip() for k in text.split(sep) if k.strip()]


def _str_or_none(value: Any) -> str | None:  # noqa: ANN401
    """Convert value to str or None.

    Args:
        value: Any value.

    Returns:
        String or None if empty.
    """
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
