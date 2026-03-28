"""Unit tests for table_extractor module."""
from __future__ import annotations

import pytest

from metascreener.doc_engine.table_extractor import extract_tables_from_markdown


class TestSimpleMarkdownTable:
    def test_simple_markdown_table(self) -> None:
        markdown = """\
Table 1: Baseline characteristics

| Age | Sex | BMI |
|-----|-----|-----|
| 45  | M   | 24  |
| 52  | F   | 26  |
"""
        tables = extract_tables_from_markdown(markdown)
        assert len(tables) == 1
        table = tables[0]
        assert table.table_id == "table_1"
        assert "Baseline" in table.caption

    def test_header_cells_marked(self) -> None:
        markdown = """\
Table 1: Test

| Col A | Col B |
|-------|-------|
| val 1 | val 2 |
"""
        tables = extract_tables_from_markdown(markdown)
        assert len(tables) == 1
        header_row = tables[0].cells[0]
        for cell in header_row:
            assert cell.is_header is True

    def test_data_cells_not_header(self) -> None:
        markdown = """\
Table 1: Test

| Col A | Col B |
|-------|-------|
| val 1 | val 2 |
"""
        tables = extract_tables_from_markdown(markdown)
        data_row = tables[0].cells[1]
        for cell in data_row:
            assert cell.is_header is False

    def test_extraction_quality_score(self) -> None:
        markdown = """\
Table 1: Quality test

| A | B |
|---|---|
| 1 | 2 |
"""
        tables = extract_tables_from_markdown(markdown)
        assert tables[0].extraction_quality_score == 0.85


class TestMultipleTables:
    def test_multiple_tables(self) -> None:
        markdown = """\
Table 1: First table

| A | B |
|---|---|
| 1 | 2 |

Some text in between.

Table 2: Second table

| X | Y | Z |
|---|---|---|
| a | b | c |
"""
        tables = extract_tables_from_markdown(markdown)
        assert len(tables) == 2
        assert tables[0].table_id == "table_1"
        assert tables[1].table_id == "table_2"

    def test_multiple_tables_sequential_ids(self) -> None:
        markdown = """\
Table 3: Third table

| P | Q |
|---|---|
| x | y |

Table 4: Fourth table

| M | N |
|---|---|
| i | j |
"""
        tables = extract_tables_from_markdown(markdown)
        assert len(tables) == 2
        # IDs are sequential based on discovery order
        assert tables[0].table_id == "table_1"
        assert tables[1].table_id == "table_2"


class TestNoTables:
    def test_no_tables(self) -> None:
        markdown = """\
# Introduction
This is plain text with no tables.
Just paragraphs here.
"""
        tables = extract_tables_from_markdown(markdown)
        assert tables == []

    def test_empty_input(self) -> None:
        tables = extract_tables_from_markdown("")
        assert tables == []


class TestTableCaptionExtraction:
    def test_table_caption_extraction(self) -> None:
        markdown = """\
Table 3: Primary endpoints of the randomised controlled trial

| Outcome | Treatment | Control |
|---------|-----------|---------|
| HbA1c   | 7.2       | 8.1     |
"""
        tables = extract_tables_from_markdown(markdown)
        assert len(tables) == 1
        assert "Primary" in tables[0].caption

    def test_caption_with_period_separator(self) -> None:
        markdown = """\
Table 2. Secondary outcomes

| Metric | Value |
|--------|-------|
| BP     | 120   |
"""
        tables = extract_tables_from_markdown(markdown)
        assert len(tables) == 1
        assert "Secondary" in tables[0].caption

    def test_table_without_caption(self) -> None:
        markdown = """\
| A | B |
|---|---|
| 1 | 2 |
"""
        tables = extract_tables_from_markdown(markdown)
        assert len(tables) == 1
        # No caption found, but table still extracted
        assert tables[0].table_id == "table_1"

    def test_cells_content(self) -> None:
        markdown = """\
Table 1: Data

| Name | Value |
|------|-------|
| Alpha | 10   |
| Beta  | 20   |
"""
        tables = extract_tables_from_markdown(markdown)
        assert len(tables[0].cells) == 3  # header + 2 data rows
        data_values = [row[0].value.strip() for row in tables[0].cells[1:]]
        assert "Alpha" in data_values
        assert "Beta" in data_values
