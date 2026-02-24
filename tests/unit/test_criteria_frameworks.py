"""Tests for criteria framework element definitions."""
from __future__ import annotations

from metascreener.core.enums import CriteriaFramework
from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS


def test_all_frameworks_have_definitions() -> None:
    """Every CriteriaFramework value must have an entry in FRAMEWORK_ELEMENTS."""
    for fw in CriteriaFramework:
        assert fw in FRAMEWORK_ELEMENTS, f"Missing definition for {fw}"


def test_pico_framework_structure() -> None:
    """PICO has population+intervention required, comparison+outcome optional."""
    pico = FRAMEWORK_ELEMENTS[CriteriaFramework.PICO]
    assert "population" in pico["required"]
    assert "intervention" in pico["required"]
    assert "comparison" in pico["optional"]
    assert "outcome" in pico["optional"]
    assert len(pico["labels"]) == len(pico["required"]) + len(pico["optional"])


def test_framework_labels_match_keys() -> None:
    """Every required/optional key must have a corresponding label."""
    for fw, defn in FRAMEWORK_ELEMENTS.items():
        all_keys = list(defn["required"]) + list(defn["optional"])
        for key in all_keys:
            assert key in defn["labels"], f"{fw}: missing label for '{key}'"


def test_custom_framework_has_empty_elements() -> None:
    """CUSTOM framework should have empty required/optional lists."""
    custom = FRAMEWORK_ELEMENTS[CriteriaFramework.CUSTOM]
    assert custom["required"] == []
    assert custom["optional"] == []
    assert custom["labels"] == {}
