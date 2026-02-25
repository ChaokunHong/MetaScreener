"""Unified file writer -- write Record lists to various formats."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import structlog

from metascreener.core.exceptions import UnsupportedFormatError
from metascreener.core.models import Record

logger = structlog.get_logger(__name__)

SUPPORTED_WRITE_FORMATS = {".ris", ".csv", ".json", ".xlsx"}

_EXPORT_FIELDS = [
    "record_id",
    "title",
    "authors",
    "year",
    "abstract",
    "doi",
    "pmid",
    "journal",
    "keywords",
    "language",
]


def write_records(
    records: list[Record],
    path: Path,
    format_type: str | None = None,
) -> Path:
    """Write Record list to file. Auto-detect format from extension if not given.

    Args:
        records: List of Record objects to write.
        path: Output file path.
        format_type: Optional format override ("ris", "csv", "json", "excel").

    Returns:
        Path to the written file.

    Raises:
        UnsupportedFormatError: If format is not recognized.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fmt = format_type or _detect_format(path)

    if fmt == "ris":
        _write_ris(records, path)
    elif fmt == "csv":
        _write_csv(records, path)
    elif fmt == "json":
        _write_json(records, path)
    elif fmt == "excel":
        _write_excel(records, path)
    else:
        raise UnsupportedFormatError(fmt, ["ris", "csv", "json", "excel"])

    logger.info("write_records", path=str(path), format=fmt, n_records=len(records))
    return path


def _detect_format(path: Path) -> str:
    """Detect write format from file extension.

    Args:
        path: Output file path.

    Returns:
        Format string.

    Raises:
        UnsupportedFormatError: If extension not recognized.
    """
    ext = path.suffix.lower()
    fmt_map = {".ris": "ris", ".csv": "csv", ".json": "json", ".xlsx": "excel"}
    if ext not in fmt_map:
        raise UnsupportedFormatError(ext, sorted(SUPPORTED_WRITE_FORMATS))
    return fmt_map[ext]


def _record_to_flat_dict(record: Record) -> dict[str, str]:
    """Convert a Record to a flat dict suitable for CSV/Excel.

    Args:
        record: Record object.

    Returns:
        Flat dict with string values.
    """
    return {
        "record_id": record.record_id,
        "title": record.title,
        "authors": "; ".join(record.authors) if record.authors else "",
        "year": str(record.year) if record.year else "",
        "abstract": record.abstract or "",
        "doi": record.doi or "",
        "pmid": record.pmid or "",
        "journal": record.journal or "",
        "keywords": "; ".join(record.keywords) if record.keywords else "",
        "language": record.language or "",
    }


def _write_csv(records: list[Record], path: Path) -> None:
    """Write records as CSV with UTF-8 BOM for Excel compatibility.

    Args:
        records: List of Record objects.
        path: Output file path.
    """
    rows = [_record_to_flat_dict(r) for r in records]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_EXPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(records: list[Record], path: Path) -> None:
    """Write records as pretty-printed JSON.

    Args:
        records: List of Record objects.
        path: Output file path.
    """
    data = [r.model_dump(exclude={"raw_data"}) for r in records]
    path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def _write_excel(records: list[Record], path: Path) -> None:
    """Write records as Excel via pandas.

    Args:
        records: List of Record objects.
        path: Output file path.
    """
    import pandas as pd  # noqa: PLC0415

    rows = [_record_to_flat_dict(r) for r in records]
    df = pd.DataFrame(rows, columns=_EXPORT_FIELDS)
    df.to_excel(path, index=False, engine="openpyxl")


def _write_ris(records: list[Record], path: Path) -> None:
    """Write records as RIS format using rispy.

    Args:
        records: List of Record objects.
        path: Output file path.
    """
    import rispy  # type: ignore[import-untyped]  # noqa: PLC0415

    entries: list[dict[str, Any]] = []
    for record in records:
        entry: dict[str, Any] = {
            "type_of_reference": "JOUR",
            "title": record.title,
        }
        if record.authors:
            entry["authors"] = list(record.authors)
        if record.year:
            entry["year"] = str(record.year)
        if record.abstract:
            entry["abstract"] = record.abstract
        if record.doi:
            entry["doi"] = record.doi
        if record.journal:
            entry["journal_name"] = record.journal
        if record.keywords:
            entry["keywords"] = list(record.keywords)
        if record.language:
            entry["language"] = record.language
        entries.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        rispy.dump(entries, f)
