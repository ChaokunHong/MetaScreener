"""Unit tests for section_parser module."""
from __future__ import annotations

import pytest

from metascreener.doc_engine.section_parser import parse_sections


class TestStandardIMRAD:
    def test_standard_imrad(self) -> None:
        markdown = """\
# Abstract
This study examines...

# Introduction
Background information here.

# Methods
We recruited 100 patients.

# Results
We found significant differences.

# Discussion
These results suggest...
"""
        sections = parse_sections(markdown)
        headings = [s.heading for s in sections]
        assert "Abstract" in headings
        assert "Introduction" in headings
        assert "Methods" in headings
        assert "Results" in headings
        assert "Discussion" in headings
        assert len(sections) == 5

    def test_content_assigned_to_section(self) -> None:
        markdown = """\
# Introduction
Background information here.

# Methods
We recruited 100 patients.
"""
        sections = parse_sections(markdown)
        intro = next(s for s in sections if s.heading == "Introduction")
        assert "Background information" in intro.content


class TestNestedSubsections:
    def test_nested_subsections(self) -> None:
        markdown = """\
# Methods
Overview of methods.

## Study Population
Details about population.

## Statistical Analysis
Details about statistics.

# Results
Main results here.
"""
        sections = parse_sections(markdown)
        assert len(sections) == 2
        methods = sections[0]
        assert methods.heading == "Methods"
        assert len(methods.children) == 2
        child_headings = [c.heading for c in methods.children]
        assert "Study Population" in child_headings
        assert "Statistical Analysis" in child_headings

    def test_deeply_nested(self) -> None:
        markdown = """\
# Methods
## Study Design
### Randomisation
Details here.
"""
        sections = parse_sections(markdown)
        assert len(sections) == 1
        methods = sections[0]
        assert len(methods.children) == 1
        study_design = methods.children[0]
        assert len(study_design.children) == 1
        assert study_design.children[0].heading == "Randomisation"


class TestNumberedSections:
    def test_numbered_sections(self) -> None:
        markdown = """\
# 1. Introduction
Background here.

# 2. Methods
Study design.

## 2.1 Participants
Inclusion criteria.
"""
        sections = parse_sections(markdown)
        assert len(sections) == 2
        headings = [s.heading for s in sections]
        assert "1. Introduction" in headings
        assert "2. Methods" in headings
        methods = next(s for s in sections if "Methods" in s.heading)
        assert len(methods.children) == 1
        assert "2.1 Participants" in methods.children[0].heading


class TestNoHeadings:
    def test_no_headings(self) -> None:
        markdown = "This is plain text without any headings. Just a paragraph."
        sections = parse_sections(markdown)
        assert len(sections) == 1
        assert sections[0].heading == "Untitled"
        assert "plain text" in sections[0].content

    def test_no_headings_full_content_preserved(self) -> None:
        text = "Line one.\nLine two.\nLine three."
        sections = parse_sections(text)
        assert sections[0].content == text


class TestTableReferencesDetected:
    def test_table_references_detected(self) -> None:
        markdown = """\
# Results
See Table 1 for primary outcomes. Table 2 shows secondary endpoints.
"""
        sections = parse_sections(markdown)
        results = sections[0]
        assert "table_1" in results.tables_in_section
        assert "table_2" in results.tables_in_section

    def test_lowercase_table_reference(self) -> None:
        markdown = """\
# Results
As shown in table 3, the results were significant.
"""
        sections = parse_sections(markdown)
        assert "table_3" in sections[0].tables_in_section

    def test_figure_references_detected(self) -> None:
        markdown = """\
# Results
Figure 1 shows the CONSORT diagram. See Figure 2 for the forest plot.
"""
        sections = parse_sections(markdown)
        results = sections[0]
        assert "figure_1" in results.figures_in_section
        assert "figure_2" in results.figures_in_section


class TestEmptyInput:
    def test_empty_input(self) -> None:
        sections = parse_sections("")
        assert sections == []

    def test_whitespace_only(self) -> None:
        sections = parse_sections("   \n\n  ")
        assert sections == []


class TestSectionLevels:
    def test_section_level_assigned_correctly(self) -> None:
        markdown = """\
# Top Level
## Second Level
### Third Level
"""
        sections = parse_sections(markdown)
        assert sections[0].level == 1
        assert sections[0].children[0].level == 2
        assert sections[0].children[0].children[0].level == 3

    def test_page_range_default(self) -> None:
        markdown = "# Introduction\nSome text."
        sections = parse_sections(markdown)
        assert sections[0].page_range == (0, 0)
