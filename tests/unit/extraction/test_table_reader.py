"""Unit tests for TableReader — DIRECT_TABLE extraction strategy."""
from __future__ import annotations

import pytest

from metascreener.doc_engine.models import StructuredDocument
from metascreener.module2_extraction.engine.table_reader import TableReader
from metascreener.module2_extraction.models import ExtractionStrategy, SourceHint
from tests.helpers.doc_builder import MockDocumentBuilder


@pytest.fixture
def doc() -> StructuredDocument:
    return (
        MockDocumentBuilder()
        .with_metadata("Test", ["A"])
        .add_table(
            "table_1",
            "Baseline characteristics",
            headers=["Variable", "Intervention (n=60)", "Control (n=60)"],
            rows=[
                ["Age, years", "55.2", "54.8"],
                ["Male, n (%)", "35 (58.3)", "33 (55.0)"],
                ["BMI", "27.1", "26.8"],
            ],
        )
        .build()
    )


@pytest.fixture
def reader() -> TableReader:
    return TableReader()


# ---------------------------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------------------------


def test_read_single_value(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Intervention (n=60)")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.value == "55.2"
    assert result.strategy_used == ExtractionStrategy.DIRECT_TABLE
    assert result.error is None


def test_read_second_row(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Control (n=60)")
    result = reader.extract(doc=doc, hint=hint, row_index=1)
    assert result.value == "33 (55.0)"
    assert result.strategy_used == ExtractionStrategy.DIRECT_TABLE


def test_read_variable_column(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Variable")
    result = reader.extract(doc=doc, hint=hint, row_index=2)
    assert result.value == "BMI"


# ---------------------------------------------------------------------------
# extract_all_rows
# ---------------------------------------------------------------------------


def test_read_all_rows(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Variable")
    results = reader.extract_all_rows(doc=doc, hint=hint)
    assert len(results) == 3
    values = [r.value for r in results]
    assert "Age, years" in values
    assert "Male, n (%)" in values
    assert "BMI" in values


def test_extract_all_rows_all_succeed(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Intervention (n=60)")
    results = reader.extract_all_rows(doc=doc, hint=hint)
    assert all(r.error is None for r in results)
    assert [r.value for r in results] == ["55.2", "35 (58.3)", "27.1"]


# ---------------------------------------------------------------------------
# Column matching
# ---------------------------------------------------------------------------


def test_exact_column_match_case_insensitive(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="variable")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.value == "Age, years"


def test_fuzzy_column_match(reader: TableReader, doc: StructuredDocument) -> None:
    # "Intervention" is a substring of "Intervention (n=60)"
    hint = SourceHint(table_id="table_1", table_column="Intervention")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.value == "55.2"


def test_fuzzy_match_partial_column_name(reader: TableReader, doc: StructuredDocument) -> None:
    # "Control" is a substring of "Control (n=60)"
    hint = SourceHint(table_id="table_1", table_column="Control")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.value == "54.8"


# ---------------------------------------------------------------------------
# SourceLocation
# ---------------------------------------------------------------------------


def test_source_location_type(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Variable")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.evidence.type == "table"
    assert result.evidence.table_id == "table_1"
    assert result.evidence.row_index == 0


def test_source_location_column_index(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Control (n=60)")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.evidence.column_index == 2  # 0=Variable, 1=Intervention, 2=Control


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_missing_table(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_99", table_column="X")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.value is None
    assert result.error is not None
    assert "table_99" in result.error


def test_missing_column(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Nonexistent Column XYZ")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.value is None
    assert result.error is not None


def test_row_index_out_of_range(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Variable")
    result = reader.extract(doc=doc, hint=hint, row_index=99)
    assert result.value is None
    assert result.error is not None


def test_missing_table_id_in_hint(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id=None, table_column="Variable")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.value is None
    assert result.error is not None


def test_missing_column_in_hint(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column=None)
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.value is None
    assert result.error is not None


def test_extract_all_rows_missing_table(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_99", table_column="Variable")
    results = reader.extract_all_rows(doc=doc, hint=hint)
    assert len(results) == 1
    assert results[0].value is None
    assert results[0].error is not None


# ---------------------------------------------------------------------------
# Strategy and confidence
# ---------------------------------------------------------------------------


def test_strategy_is_direct_table(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Variable")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.strategy_used == ExtractionStrategy.DIRECT_TABLE


def test_confidence_prior_is_high(reader: TableReader, doc: StructuredDocument) -> None:
    hint = SourceHint(table_id="table_1", table_column="Variable")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.confidence_prior >= 0.9


def test_model_id_is_none(reader: TableReader, doc: StructuredDocument) -> None:
    """DIRECT_TABLE uses zero LLM calls — model_id must be None."""
    hint = SourceHint(table_id="table_1", table_column="Variable")
    result = reader.extract(doc=doc, hint=hint, row_index=0)
    assert result.model_id is None
