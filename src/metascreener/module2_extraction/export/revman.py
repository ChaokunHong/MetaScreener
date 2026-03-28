"""Cochrane RevMan XML exporter.

Produces an XML file in a Cochrane Review Manager (RevMan 5) compatible
format containing one ``DICH_DATA`` entry per study.  Continuous data is
also supported via ``CONT_DATA`` entries.

The exporter auto-detects the data type from ``field_tags``:
  - Two ``EVENTS_ARM`` tags present → dichotomous
  - Two ``MEAN`` tags present       → continuous
  - Falls back to a stub entry otherwise
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import structlog

from metascreener.core.enums import FieldSemanticTag
from metascreener.module2_extraction.export.effect_size_mapper import EffectSizeMapper

log = structlog.get_logger()


def export_to_revman(
    results: list[dict[str, str]],
    field_tags: dict[str, str],
    output_path: Path,
) -> Path:
    """Export extraction results to Cochrane RevMan XML format.

    Args:
        results: Cell data from repository — each entry is a dict with at
            minimum ``pdf_id``, ``field_name``, and ``value`` keys.
        field_tags: Mapping of field_name → FieldSemanticTag identifying the
            semantic role of each field.
        output_path: Destination path for the XML file.

    Returns:
        Path to the saved file.
    """
    # Group by pdf_id
    by_pdf: dict[str, dict[str, str]] = defaultdict(dict)
    for cell in results:
        by_pdf[cell["pdf_id"]][cell["field_name"]] = cell.get("value", "")

    mapper = EffectSizeMapper()

    # Determine data type from field_tags
    events_fields = [n for n, t in field_tags.items() if t == FieldSemanticTag.EVENTS_ARM]
    mean_fields   = [n for n, t in field_tags.items() if t == FieldSemanticTag.MEAN]
    is_dichotomous = len(events_fields) >= 2
    is_continuous  = (not is_dichotomous) and len(mean_fields) >= 2

    # Build XML tree
    review = ET.Element("COCHRANE_REVIEW")
    analyses = ET.SubElement(review, "ANALYSES_AND_DATA")
    comparison = ET.SubElement(
        analyses, "COMPARISON", attrib={"NO": "1", "TITLE": "Intervention vs Control"}
    )

    if is_dichotomous:
        outcome = ET.SubElement(
            comparison, "DICH_OUTCOME",
            attrib={"NO": "1", "TITLE": "Primary Outcome"},
        )
        for pdf_id, pdf_data in by_pdf.items():
            d = mapper.map_to_dichotomous(pdf_data, field_tags)
            if d is None:
                _append_stub_study(outcome, pdf_id)
                continue
            ET.SubElement(
                outcome, "DICH_DATA",
                attrib={
                    "STUDY_ID": d.study_id or pdf_id,
                    "EVENTS_1": str(d.events_e),
                    "TOTAL_1":  str(d.total_e),
                    "EVENTS_2": str(d.events_c),
                    "TOTAL_2":  str(d.total_c),
                },
            )
    elif is_continuous:
        outcome = ET.SubElement(
            comparison, "CONT_OUTCOME",
            attrib={"NO": "1", "TITLE": "Primary Outcome"},
        )
        for pdf_id, pdf_data in by_pdf.items():
            c = mapper.map_to_continuous(pdf_data, field_tags)
            if c is None:
                _append_stub_study(outcome, pdf_id)
                continue
            ET.SubElement(
                outcome, "CONT_DATA",
                attrib={
                    "STUDY_ID": c.study_id or pdf_id,
                    "MEAN_1":   str(c.mean_e),
                    "SD_1":     str(c.sd_e),
                    "TOTAL_1":  str(c.n_e),
                    "MEAN_2":   str(c.mean_c),
                    "SD_2":     str(c.sd_c),
                    "TOTAL_2":  str(c.n_c),
                },
            )
    else:
        # Generic: emit one STUDY element per PDF with study ID
        for pdf_id, pdf_data in by_pdf.items():
            study_id = _extract_study_id(pdf_data, field_tags) or pdf_id
            ET.SubElement(comparison, "STUDY", attrib={"STUDY_ID": study_id})

    # Indent for readability (Python ≥ 3.9)
    try:
        ET.indent(review, space="  ")
    except AttributeError:  # pragma: no cover — Python < 3.9
        pass

    tree = ET.ElementTree(review)
    tree.write(output_path, encoding="unicode", xml_declaration=True)

    log.info("revman_exported", path=str(output_path), pdf_count=len(by_pdf))
    return output_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _append_stub_study(parent: ET.Element, pdf_id: str) -> None:
    ET.SubElement(parent, "STUDY", attrib={"STUDY_ID": pdf_id, "STATUS": "incomplete"})


def _extract_study_id(pdf_data: dict[str, str], field_tags: dict[str, str]) -> str:
    for name, tag in field_tags.items():
        if tag == FieldSemanticTag.STUDY_ID:
            return pdf_data.get(name, "")
    return ""
