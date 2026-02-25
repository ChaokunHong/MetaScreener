"""Unified file reader -- auto-detects format by extension."""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from typing import Any

import structlog

from metascreener.core.exceptions import UnsupportedFormatError
from metascreener.core.models import Record
from metascreener.io.parsers import normalize_record

logger = structlog.get_logger(__name__)

SUPPORTED_EXTENSIONS = {".ris", ".bib", ".csv", ".xml", ".xlsx"}


def read_records(path: Path) -> list[Record]:
    """Read literature records from a file, auto-detecting format by extension.

    Args:
        path: Path to the input file.

    Returns:
        List of Record objects.

    Raises:
        UnsupportedFormatError: If file extension is not recognized.
        FileNotFoundError: If file does not exist.
    """
    path = Path(path)
    ext = path.suffix.lower()

    # Check extension first so unsupported formats fail fast
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFormatError(ext, sorted(SUPPORTED_EXTENSIONS))

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    source = str(path)

    if ext == ".ris":
        raw_records = _read_ris(path)
        fmt = "ris"
    elif ext == ".bib":
        raw_records = _read_bibtex(path)
        fmt = "bibtex"
    elif ext == ".csv":
        raw_records = _read_csv(path)
        fmt = "csv"
    elif ext == ".xml":
        raw_records = _read_pubmed_xml(path)
        fmt = "xml"
    elif ext == ".xlsx":
        raw_records = _read_excel(path)
        fmt = "excel"
    else:
        # Should never reach here due to the check above
        raise UnsupportedFormatError(ext, sorted(SUPPORTED_EXTENSIONS))

    records = [normalize_record(r, fmt, source_file=source) for r in raw_records]
    logger.info("read_records", path=source, format=fmt, n_records=len(records))
    return records


def _read_ris(path: Path) -> list[dict[str, Any]]:
    """Read RIS file using rispy.

    Args:
        path: Path to .ris file.

    Returns:
        List of raw record dicts.
    """
    import rispy  # type: ignore[import-untyped]  # noqa: PLC0415

    try:
        with open(path, encoding="utf-8") as f:
            entries: list[dict[str, Any]] = rispy.load(f)
    except UnicodeDecodeError:
        with open(path, encoding="latin-1") as f:
            entries = rispy.load(f)
    return entries


def _read_bibtex(path: Path) -> list[dict[str, Any]]:
    """Read BibTeX file using bibtexparser v2.

    Args:
        path: Path to .bib file.

    Returns:
        List of raw record dicts.
    """
    import bibtexparser  # noqa: PLC0415

    library = bibtexparser.parse_string(path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    results: list[dict[str, Any]] = []
    for entry in library.entries:
        raw: dict[str, Any] = dict(entry.fields_dict)
        mapped: dict[str, Any] = {}
        for k, v in raw.items():
            mapped[k] = v.value if hasattr(v, "value") else str(v)
        results.append(mapped)
    return results


def _read_csv(path: Path) -> list[dict[str, Any]]:
    """Read CSV file with delimiter auto-detection.

    Args:
        path: Path to .csv file.

    Returns:
        List of raw record dicts.
    """
    text = _read_text_with_fallback(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4096])
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    return list(reader)


def _read_pubmed_xml(path: Path) -> list[dict[str, Any]]:
    """Read PubMed XML file.

    Args:
        path: Path to .xml file.

    Returns:
        List of raw record dicts with canonical field names.
    """
    tree = ET.parse(path)  # noqa: S314
    root = tree.getroot()
    results: list[dict[str, Any]] = []

    for article in root.iter("PubmedArticle"):
        raw: dict[str, Any] = {}

        pmid_el = article.find(".//PMID")
        if pmid_el is not None and pmid_el.text:
            raw["pmid"] = pmid_el.text

        title_el = article.find(".//ArticleTitle")
        if title_el is not None and title_el.text:
            raw["title"] = title_el.text

        abstract_parts: list[str] = []
        for abs_el in article.findall(".//AbstractText"):
            label = abs_el.get("Label", "")
            text = abs_el.text or ""
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        if abstract_parts:
            raw["abstract"] = " ".join(abstract_parts)

        authors: list[str] = []
        for author_el in article.findall(".//Author"):
            collective = author_el.find("CollectiveName")
            if collective is not None and collective.text:
                authors.append(collective.text)
            else:
                last = author_el.find("LastName")
                first = author_el.find("ForeName")
                if last is not None and last.text:
                    name = last.text
                    if first is not None and first.text:
                        name = f"{last.text}, {first.text}"
                    authors.append(name)
        if authors:
            raw["authors"] = authors

        year_el = article.find(".//PubMedPubDate[@PubStatus='pubmed']/Year")
        if year_el is not None and year_el.text:
            raw["year"] = year_el.text

        doi_el = article.find(".//ArticleId[@IdType='doi']")
        if doi_el is not None and doi_el.text:
            raw["doi"] = doi_el.text

        journal_el = article.find(".//Journal/Title")
        if journal_el is not None and journal_el.text:
            raw["journal"] = journal_el.text

        mesh_terms: list[str] = []
        for mesh_el in article.findall(".//MeshHeading/DescriptorName"):
            if mesh_el.text:
                mesh_terms.append(mesh_el.text)
        if mesh_terms:
            raw["keywords"] = mesh_terms

        lang_el = article.find(".//Language")
        if lang_el is not None and lang_el.text:
            raw["language"] = lang_el.text

        results.append(raw)

    return results


def _read_excel(path: Path) -> list[dict[str, Any]]:
    """Read Excel file via pandas.

    Args:
        path: Path to .xlsx file.

    Returns:
        List of raw record dicts.
    """
    import pandas as pd  # noqa: PLC0415

    df = pd.read_excel(path, engine="openpyxl")
    return df.where(df.notna(), None).to_dict(orient="records")  # type: ignore[no-any-return]


def _read_text_with_fallback(path: Path) -> str:
    """Read text file with encoding fallback (UTF-8 -> latin-1).

    Args:
        path: Path to text file.

    Returns:
        File content as string.
    """
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")
