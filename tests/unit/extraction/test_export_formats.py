"""Tests for CSV, RevMan XML, R meta, and EffectSizeMapper exporters."""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from metascreener.core.enums import FieldSemanticTag
from metascreener.module2_extraction.export.csv_export import export_to_csv
from metascreener.module2_extraction.export.effect_size_mapper import (
    ContinuousData,
    DichotomousData,
    EffectSizeMapper,
)
from metascreener.module2_extraction.export.r_meta import export_to_r_meta
from metascreener.module2_extraction.export.revman import export_to_revman


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FIELD_NAMES = ["Study ID", "Events E", "N E", "Events C", "N C"]

DICH_RESULTS = [
    {"pdf_id": "pdf_001", "field_name": "Study ID",  "value": "Smith 2020", "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "Events E",  "value": "30",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "N E",        "value": "60",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "Events C",  "value": "20",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "N C",        "value": "60",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_002", "field_name": "Study ID",  "value": "Jones 2021", "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_002", "field_name": "Events E",  "value": "15",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_002", "field_name": "N E",        "value": "40",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_002", "field_name": "Events C",  "value": "25",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_002", "field_name": "N C",        "value": "40",         "confidence": "high", "evidence_json": ""},
]

DICH_FIELD_TAGS = {
    "Study ID": FieldSemanticTag.STUDY_ID,
    "Events E": FieldSemanticTag.EVENTS_ARM,
    "N E":       FieldSemanticTag.SAMPLE_SIZE_ARM,
    "Events C": FieldSemanticTag.EVENTS_ARM,
    "N C":       FieldSemanticTag.SAMPLE_SIZE_ARM,
}

CONT_RESULTS = [
    {"pdf_id": "pdf_001", "field_name": "Study ID", "value": "Li 2019",    "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "Mean E",   "value": "5.2",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "SD E",     "value": "1.1",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "N E",      "value": "50",          "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "Mean C",   "value": "4.8",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "SD C",     "value": "1.3",         "confidence": "high", "evidence_json": ""},
    {"pdf_id": "pdf_001", "field_name": "N C",      "value": "50",          "confidence": "high", "evidence_json": ""},
]

CONT_FIELD_TAGS = {
    "Study ID": FieldSemanticTag.STUDY_ID,
    "Mean E":   FieldSemanticTag.MEAN,
    "SD E":     FieldSemanticTag.SD,
    "N E":      FieldSemanticTag.SAMPLE_SIZE_ARM,
    "Mean C":   FieldSemanticTag.MEAN,
    "SD C":     FieldSemanticTag.SD,
    "N C":      FieldSemanticTag.SAMPLE_SIZE_ARM,
}


# ---------------------------------------------------------------------------
# CSV export tests
# ---------------------------------------------------------------------------


def test_csv_export(tmp_path: Path) -> None:
    """Basic CSV output with correct headers and data rows."""
    output = tmp_path / "results.csv"
    returned = export_to_csv(
        results=DICH_RESULTS,
        field_names=FIELD_NAMES,
        output_path=output,
    )

    assert returned == output
    assert output.exists()

    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    assert set(rows[0].keys()) == set(FIELD_NAMES)
    assert len(rows) == 2  # two PDFs

    study_ids = {r["Study ID"] for r in rows}
    assert "Smith 2020" in study_ids
    assert "Jones 2021" in study_ids


def test_csv_export_empty(tmp_path: Path) -> None:
    """Empty results should write headers only."""
    output = tmp_path / "empty.csv"
    export_to_csv(results=[], field_names=FIELD_NAMES, output_path=output)

    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    assert rows == []
    assert set(reader.fieldnames or []) == set(FIELD_NAMES)


# ---------------------------------------------------------------------------
# RevMan XML tests
# ---------------------------------------------------------------------------


def test_revman_basic(tmp_path: Path) -> None:
    """RevMan XML must contain required structural elements."""
    output = tmp_path / "revman.xml"
    returned = export_to_revman(
        results=DICH_RESULTS,
        field_tags=DICH_FIELD_TAGS,
        output_path=output,
    )

    assert returned == output
    assert output.exists()

    tree = ET.parse(output)
    root = tree.getroot()

    # Root must be COCHRANE_REVIEW or have ANALYSES_AND_DATA descendant
    xml_str = ET.tostring(root, encoding="unicode")
    assert "COCHRANE_REVIEW" in xml_str or "ANALYSES_AND_DATA" in xml_str


def test_revman_has_studies(tmp_path: Path) -> None:
    """RevMan XML should contain study entries for each PDF."""
    output = tmp_path / "revman_studies.xml"
    export_to_revman(
        results=DICH_RESULTS,
        field_tags=DICH_FIELD_TAGS,
        output_path=output,
    )

    xml_str = output.read_text(encoding="utf-8")
    # Each study_id value should appear in XML
    assert "Smith 2020" in xml_str
    assert "Jones 2021" in xml_str


# ---------------------------------------------------------------------------
# R meta export tests
# ---------------------------------------------------------------------------


def test_r_meta_dichotomous(tmp_path: Path) -> None:
    """R meta CSV for dichotomous data must have ai/n1i/ci/n2i columns."""
    output = tmp_path / "r_dich.csv"
    returned = export_to_r_meta(
        results=DICH_RESULTS,
        field_tags=DICH_FIELD_TAGS,
        output_path=output,
    )

    assert returned == output
    assert output.exists()

    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    required = {"ai", "n1i", "ci", "n2i"}
    assert required.issubset(set(reader.fieldnames or []))
    assert len(rows) == 2

    row0 = {r["ai"]: r for r in rows}
    assert "30" in row0  # events_e for Smith 2020


def test_r_meta_continuous(tmp_path: Path) -> None:
    """R meta CSV for continuous data must have m1i/sd1i/n1i/m2i/sd2i/n2i columns."""
    cont_field_names = ["Study ID", "Mean E", "SD E", "N E", "Mean C", "SD C", "N C"]
    output = tmp_path / "r_cont.csv"
    returned = export_to_r_meta(
        results=CONT_RESULTS,
        field_tags=CONT_FIELD_TAGS,
        output_path=output,
    )

    assert returned == output
    assert output.exists()

    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    required = {"m1i", "sd1i", "n1i", "m2i", "sd2i", "n2i"}
    assert required.issubset(set(reader.fieldnames or []))
    assert len(rows) == 1

    assert rows[0]["m1i"] == "5.2"
    assert rows[0]["sd1i"] == "1.1"
    assert rows[0]["n1i"] == "50"
    assert rows[0]["m2i"] == "4.8"
    assert rows[0]["sd2i"] == "1.3"
    assert rows[0]["n2i"] == "50"


# ---------------------------------------------------------------------------
# EffectSizeMapper tests
# ---------------------------------------------------------------------------


def test_effect_size_mapper_dichotomous() -> None:
    """EffectSizeMapper should produce correct DichotomousData."""
    mapper = EffectSizeMapper()
    pdf_data = {
        "Study ID": "Smith 2020",
        "Events E": "30",
        "N E": "60",
        "Events C": "20",
        "N C": "60",
    }
    result = mapper.map_to_dichotomous(pdf_data, DICH_FIELD_TAGS)

    assert isinstance(result, DichotomousData)
    assert result.study_id == "Smith 2020"
    assert result.events_e == 30
    assert result.total_e == 60
    assert result.events_c == 20
    assert result.total_c == 60


def test_effect_size_mapper_continuous() -> None:
    """EffectSizeMapper should produce correct ContinuousData."""
    mapper = EffectSizeMapper()
    pdf_data = {
        "Study ID": "Li 2019",
        "Mean E": "5.2",
        "SD E": "1.1",
        "N E": "50",
        "Mean C": "4.8",
        "SD C": "1.3",
        "N C": "50",
    }
    result = mapper.map_to_continuous(pdf_data, CONT_FIELD_TAGS)

    assert isinstance(result, ContinuousData)
    assert result.study_id == "Li 2019"
    assert result.mean_e == pytest.approx(5.2)
    assert result.sd_e == pytest.approx(1.1)
    assert result.n_e == 50
    assert result.mean_c == pytest.approx(4.8)
    assert result.sd_c == pytest.approx(1.3)
    assert result.n_c == 50


def test_effect_size_mapper_missing_fields() -> None:
    """mapper should return None when required fields are absent."""
    mapper = EffectSizeMapper()
    incomplete_data = {"Study ID": "Nobody"}
    incomplete_tags = {
        "Study ID": FieldSemanticTag.STUDY_ID,
    }

    assert mapper.map_to_dichotomous(incomplete_data, incomplete_tags) is None
    assert mapper.map_to_continuous(incomplete_data, incomplete_tags) is None


def test_effect_size_mapper_non_numeric_returns_none() -> None:
    """Non-numeric values for numeric fields should yield None."""
    mapper = EffectSizeMapper()
    bad_data = {
        "Study ID": "Bad Study",
        "Events E": "N/A",
        "N E": "not a number",
        "Events C": "20",
        "N C": "60",
    }
    result = mapper.map_to_dichotomous(bad_data, DICH_FIELD_TAGS)
    assert result is None
