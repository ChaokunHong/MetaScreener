"""Tests for Streamlit page imports."""
from __future__ import annotations

import importlib


def test_screening_page_imports() -> None:
    """01_screening.py imports without error."""
    mod = importlib.import_module("metascreener.app.pages.01_screening")
    assert hasattr(mod, "main")


def test_evaluation_page_imports() -> None:
    """02_evaluation.py imports without error."""
    mod = importlib.import_module("metascreener.app.pages.02_evaluation")
    assert hasattr(mod, "main")


def test_extraction_page_imports() -> None:
    """03_extraction.py imports without error."""
    mod = importlib.import_module("metascreener.app.pages.03_extraction")
    assert hasattr(mod, "main")


def test_quality_page_imports() -> None:
    """04_quality.py imports without error."""
    mod = importlib.import_module("metascreener.app.pages.04_quality")
    assert hasattr(mod, "main")
