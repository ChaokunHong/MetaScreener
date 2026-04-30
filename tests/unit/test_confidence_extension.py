"""Tests for extended Confidence enum and new FieldSemanticTag enum."""
from __future__ import annotations

import pytest

from metascreener.core.enums import Confidence, FieldSemanticTag


def test_confidence_has_verified() -> None:
    assert Confidence.VERIFIED.value == "VERIFIED"


def test_confidence_has_failed() -> None:
    assert Confidence.FAILED.value == "FAILED"


def test_confidence_ordering() -> None:
    order = list(Confidence)
    assert order.index(Confidence.VERIFIED) < order.index(Confidence.HIGH)
    assert order.index(Confidence.SINGLE) < order.index(Confidence.FAILED)


def test_confidence_downgrade() -> None:
    assert Confidence.VERIFIED.downgrade() == Confidence.HIGH
    assert Confidence.HIGH.downgrade() == Confidence.MEDIUM
    assert Confidence.MEDIUM.downgrade() == Confidence.LOW
    assert Confidence.LOW.downgrade() == Confidence.SINGLE
    assert Confidence.SINGLE.downgrade() == Confidence.FAILED
    assert Confidence.FAILED.downgrade() == Confidence.FAILED


def test_confidence_needs_review() -> None:
    assert Confidence.VERIFIED.needs_review is False
    assert Confidence.HIGH.needs_review is False
    assert Confidence.MEDIUM.needs_review is False
    assert Confidence.SINGLE.needs_review is False
    assert Confidence.LOW.needs_review is True
    assert Confidence.FAILED.needs_review is True


def test_field_semantic_tag_values() -> None:
    assert FieldSemanticTag.SAMPLE_SIZE_TOTAL.value == "n_total"
    assert FieldSemanticTag.EFFECT_ESTIMATE.value == "effect_estimate"
    assert FieldSemanticTag.P_VALUE.value == "p_value"


def test_field_semantic_tag_all_members() -> None:
    """Ensure all expected members exist."""
    expected = {
        "SAMPLE_SIZE_TOTAL",
        "SAMPLE_SIZE_ARM",
        "EVENTS_ARM",
        "MEAN",
        "SD",
        "SE",
        "MEDIAN",
        "IQR_LOWER",
        "IQR_UPPER",
        "PROPORTION",
        "EFFECT_ESTIMATE",
        "CI_LOWER",
        "CI_UPPER",
        "P_VALUE",
        "AGE",
        "PERCENTAGE",
        "STUDY_ID",
        "INTERVENTION",
        "COMPARATOR",
        "OUTCOME",
        "FOLLOW_UP",
    }
    actual = {m.name for m in FieldSemanticTag}
    assert expected == actual


def test_confidence_existing_values_uppercase() -> None:
    """Confidence values must be uppercase for backward compatibility with DB storage."""
    assert Confidence.HIGH.value == "HIGH"
    assert Confidence.MEDIUM.value == "MEDIUM"
    assert Confidence.LOW.value == "LOW"
    assert Confidence.SINGLE.value == "SINGLE"
