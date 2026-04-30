"""R metafor-compatible CSV exporter.

Exports extraction results as a CSV file formatted for direct use with the
R ``metafor`` package:

* **Dichotomous**: columns ``study_id``, ``ai``, ``n1i``, ``ci``, ``n2i``
  (ai = events experimental, n1i = total experimental,
   ci = events control, n2i = total control).
* **Continuous**: columns ``study_id``, ``m1i``, ``sd1i``, ``n1i``,
  ``m2i``, ``sd2i``, ``n2i``.
* **Generic / fallback**: columns ``study_id``, ``yi``, ``vi``
  (effect estimate + variance, if tagged).

Data type is inferred automatically from ``field_tags``.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import structlog

from metascreener.core.enums import FieldSemanticTag
from metascreener.module2_extraction.export.effect_size_mapper import EffectSizeMapper

log = structlog.get_logger()

def export_to_r_meta(
    results: list[dict[str, str]],
    field_tags: dict[str, str],
    output_path: Path,
) -> Path:
    """Export extraction results as an R metafor-compatible CSV.

    Args:
        results: Cell data from repository — each entry is a dict with at
            minimum ``pdf_id``, ``field_name``, and ``value`` keys.
        field_tags: Mapping of field_name → FieldSemanticTag.
        output_path: Destination path for the CSV file.

    Returns:
        Path to the saved file.
    """
    # Group results by pdf_id → field_name → value
    by_pdf: dict[str, dict[str, str]] = defaultdict(dict)
    for cell in results:
        by_pdf[cell["pdf_id"]][cell["field_name"]] = cell.get("value", "")

    mapper = EffectSizeMapper()

    # Detect data type
    events_fields = [n for n, t in field_tags.items() if t == FieldSemanticTag.EVENTS_ARM]
    mean_fields   = [n for n, t in field_tags.items() if t == FieldSemanticTag.MEAN]
    effect_fields = [n for n, t in field_tags.items() if t == FieldSemanticTag.EFFECT_ESTIMATE]
    var_fields    = [n for n, t in field_tags.items() if t == FieldSemanticTag.SE]

    is_dichotomous = len(events_fields) >= 2
    is_continuous  = (not is_dichotomous) and len(mean_fields) >= 2

    if is_dichotomous:
        _write_dichotomous(by_pdf, mapper, field_tags, output_path)
    elif is_continuous:
        _write_continuous(by_pdf, mapper, field_tags, output_path)
    else:
        _write_generic(by_pdf, field_tags, effect_fields, var_fields, output_path)

    log.info("r_meta_exported", path=str(output_path), pdf_count=len(by_pdf))
    return output_path

def _write_dichotomous(
    by_pdf: dict[str, dict[str, str]],
    mapper: EffectSizeMapper,
    field_tags: dict[str, str],
    output_path: Path,
) -> None:
    fieldnames = ["study_id", "ai", "n1i", "ci", "n2i"]
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for pdf_id, pdf_data in by_pdf.items():
            d = mapper.map_to_dichotomous(pdf_data, field_tags)
            if d is None:
                writer.writerow(dict.fromkeys(fieldnames, "") | {"study_id": pdf_id})
                continue
            writer.writerow({
                "study_id": d.study_id or pdf_id,
                "ai":  str(d.events_e),
                "n1i": str(d.total_e),
                "ci":  str(d.events_c),
                "n2i": str(d.total_c),
            })

def _write_continuous(
    by_pdf: dict[str, dict[str, str]],
    mapper: EffectSizeMapper,
    field_tags: dict[str, str],
    output_path: Path,
) -> None:
    fieldnames = ["study_id", "m1i", "sd1i", "n1i", "m2i", "sd2i", "n2i"]
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for pdf_id, pdf_data in by_pdf.items():
            c = mapper.map_to_continuous(pdf_data, field_tags)
            if c is None:
                writer.writerow(dict.fromkeys(fieldnames, "") | {"study_id": pdf_id})
                continue
            writer.writerow({
                "study_id": c.study_id or pdf_id,
                "m1i":  str(c.mean_e),
                "sd1i": str(c.sd_e),
                "n1i":  str(c.n_e),
                "m2i":  str(c.mean_c),
                "sd2i": str(c.sd_c),
                "n2i":  str(c.n_c),
            })

def _write_generic(
    by_pdf: dict[str, dict[str, str]],
    field_tags: dict[str, str],
    effect_fields: list[str],
    var_fields: list[str],
    output_path: Path,
) -> None:
    fieldnames = ["study_id", "yi", "vi"]
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for pdf_id, pdf_data in by_pdf.items():
            study_id = _extract_study_id(pdf_data, field_tags) or pdf_id
            yi = pdf_data.get(effect_fields[0], "") if effect_fields else ""
            vi = pdf_data.get(var_fields[0], "")    if var_fields else ""
            writer.writerow({"study_id": study_id, "yi": yi, "vi": vi})

def _extract_study_id(pdf_data: dict[str, str], field_tags: dict[str, str]) -> str:
    for name, tag in field_tags.items():
        if tag == FieldSemanticTag.STUDY_ID:
            return pdf_data.get(name, "")
    return ""
