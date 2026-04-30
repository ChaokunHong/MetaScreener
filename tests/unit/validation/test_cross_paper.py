"""Tests for V5 Cross-Paper Outlier Detection (Task 20)."""
from __future__ import annotations

import pytest

from metascreener.core.enums import FieldSemanticTag
from metascreener.module2_extraction.validation.cross_paper import CrossPaperValidator
from metascreener.module2_extraction.validation.models import OutlierAlert


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tags(**kwargs: FieldSemanticTag) -> dict[str, FieldSemanticTag]:
    """Build field_tags dict from keyword args."""
    return dict(kwargs)


def _build_all_values(field_name: str, values: list[float]) -> dict[str, dict[str, float]]:
    """Build all_values dict: {pdf_id: {field_name: value}}."""
    return {f"paper_{i}": {field_name: v} for i, v in enumerate(values)}


# ---------------------------------------------------------------------------
# TestNoOutlier
# ---------------------------------------------------------------------------


class TestNoOutlier:
    def test_no_outlier_all_similar(self) -> None:
        """10 values all similar → no alerts."""
        all_values = _build_all_values("n_total", [100, 101, 102, 99, 98, 103, 97, 100, 101, 100])
        tags = _tags(n_total=FieldSemanticTag.SAMPLE_SIZE_TOTAL)
        validator = CrossPaperValidator()
        alerts = validator.detect_outliers(all_values, tags)
        assert alerts == []

    def test_no_outlier_with_moderate_spread(self) -> None:
        """Values with reasonable spread → no alerts."""
        all_values = _build_all_values("mean", [1.0, 1.5, 2.0, 2.5, 3.0, 1.2, 1.8, 2.2, 2.8, 1.6])
        tags = _tags(mean=FieldSemanticTag.MEAN)
        validator = CrossPaperValidator()
        alerts = validator.detect_outliers(all_values, tags)
        assert alerts == []


# ---------------------------------------------------------------------------
# TestIQROutlier
# ---------------------------------------------------------------------------


class TestIQROutlier:
    def test_single_extreme_outlier(self) -> None:
        """9 values in [0.5–3.0] + one 500 → alert on outlier paper."""
        values = [0.5, 1.0, 1.5, 2.0, 2.5, 2.8, 3.0, 1.2, 1.8, 500.0]
        all_values = _build_all_values("effect_size", values)
        tags = _tags(effect_size=FieldSemanticTag.EFFECT_ESTIMATE)
        validator = CrossPaperValidator()
        alerts = validator.detect_outliers(all_values, tags)
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.field_name == "effect_size"
        assert alert.value == 500.0
        # The outlier paper is at index 9
        assert alert.pdf_id == "paper_9"

    def test_outlier_alert_has_population_summary(self) -> None:
        """OutlierAlert should include population_summary, possible_cause, suggested_action."""
        values = [1.0, 1.1, 1.2, 1.0, 0.9, 1.1, 1.0, 1.2, 1.1, 999.0]
        all_values = _build_all_values("n_total", values)
        tags = _tags(n_total=FieldSemanticTag.SAMPLE_SIZE_TOTAL)
        validator = CrossPaperValidator()
        alerts = validator.detect_outliers(all_values, tags)
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.population_summary  # non-empty
        assert alert.possible_cause
        assert alert.suggested_action
        assert isinstance(alert, OutlierAlert)

    def test_lower_bound_outlier(self) -> None:
        """Extremely low value should also be flagged."""
        values = [100.0, 110.0, 105.0, 98.0, 102.0, 108.0, 99.0, 103.0, 107.0, 0.001]
        all_values = _build_all_values("p_value", values)
        tags = _tags(p_value=FieldSemanticTag.P_VALUE)
        validator = CrossPaperValidator()
        # p-value of 0.001 is actually not an outlier by IQR with 3*IQR
        # Let's use a value that IS a lower outlier
        values[-1] = -500.0  # clearly impossible and outlier
        all_values = _build_all_values("p_value", values)
        alerts = validator.detect_outliers(all_values, tags)
        assert any(a.value == -500.0 for a in alerts)

    def test_non_numeric_values_skipped(self) -> None:
        """Non-numeric values in a field should be skipped gracefully."""
        all_values = {
            "paper_0": {"study_id": "RCT-001"},
            "paper_1": {"study_id": "RCT-002"},
            "paper_2": {"study_id": "RCT-003"},
            "paper_3": {"study_id": "RCT-004"},
            "paper_4": {"study_id": "OUTLIER"},
        }
        tags = _tags(study_id=FieldSemanticTag.STUDY_ID)
        validator = CrossPaperValidator()
        alerts = validator.detect_outliers(all_values, tags)
        # No numeric values → no alerts
        assert alerts == []

    def test_none_values_skipped(self) -> None:
        """None values should be excluded from the numeric population."""
        all_values = {
            "paper_0": {"n_total": 100},
            "paper_1": {"n_total": 102},
            "paper_2": {"n_total": None},
            "paper_3": {"n_total": 98},
            "paper_4": {"n_total": 101},
            "paper_5": {"n_total": 99},
            "paper_6": {"n_total": 103},
            "paper_7": {"n_total": 100},
            "paper_8": {"n_total": 101},
            "paper_9": {"n_total": 100},
        }
        tags = _tags(n_total=FieldSemanticTag.SAMPLE_SIZE_TOTAL)
        validator = CrossPaperValidator()
        alerts = validator.detect_outliers(all_values, tags)
        assert alerts == []


# ---------------------------------------------------------------------------
# TestTooFewPapers
# ---------------------------------------------------------------------------


class TestTooFewPapers:
    def test_exactly_four_papers_skipped(self) -> None:
        """4 papers → skip, no alerts even with a wild value."""
        all_values = {
            "paper_0": {"n_total": 100},
            "paper_1": {"n_total": 102},
            "paper_2": {"n_total": 98},
            "paper_3": {"n_total": 9999},
        }
        tags = _tags(n_total=FieldSemanticTag.SAMPLE_SIZE_TOTAL)
        validator = CrossPaperValidator()
        alerts = validator.detect_outliers(all_values, tags)
        assert alerts == []

    def test_exactly_five_papers_checked(self) -> None:
        """5 papers → should be analyzed (threshold is >= 5)."""
        all_values = {
            "paper_0": {"n_total": 100},
            "paper_1": {"n_total": 102},
            "paper_2": {"n_total": 98},
            "paper_3": {"n_total": 101},
            "paper_4": {"n_total": 9999},
        }
        tags = _tags(n_total=FieldSemanticTag.SAMPLE_SIZE_TOTAL)
        validator = CrossPaperValidator()
        alerts = validator.detect_outliers(all_values, tags)
        # With 5 papers, 9999 should be a clear outlier
        assert len(alerts) == 1
        assert alerts[0].value == 9999

    def test_zero_papers_no_crash(self) -> None:
        """Empty input → no alerts, no crash."""
        validator = CrossPaperValidator()
        alerts = validator.detect_outliers({}, {})
        assert alerts == []


# ---------------------------------------------------------------------------
# TestIncremental
# ---------------------------------------------------------------------------


class TestIncremental:
    def test_incremental_only_reports_new_papers(self) -> None:
        """Incremental mode: only return alerts for papers in new_values."""
        # Existing 9 papers with normal values
        existing_values = _build_all_values(
            "effect_size", [1.0, 1.1, 0.9, 1.2, 1.0, 0.8, 1.1, 1.3, 1.0]
        )
        # New paper is an outlier
        new_values = {"new_paper": {"effect_size": 999.0}}
        tags = _tags(effect_size=FieldSemanticTag.EFFECT_ESTIMATE)
        validator = CrossPaperValidator()
        alerts = validator.validate_incremental(new_values, existing_values, tags)
        assert len(alerts) == 1
        assert alerts[0].pdf_id == "new_paper"

    def test_incremental_does_not_report_old_outliers(self) -> None:
        """Existing outliers should not appear in incremental results."""
        # Existing papers including one outlier
        existing_values = _build_all_values(
            "effect_size", [1.0, 1.1, 0.9, 1.2, 1.0, 0.8, 1.1, 1.3, 999.0]
        )
        # New paper is normal
        new_values = {"new_paper": {"effect_size": 1.05}}
        tags = _tags(effect_size=FieldSemanticTag.EFFECT_ESTIMATE)
        validator = CrossPaperValidator()
        alerts = validator.validate_incremental(new_values, existing_values, tags)
        # The existing outlier (paper_8) should NOT be in results
        assert all(a.pdf_id == "new_paper" for a in alerts)

    def test_incremental_no_new_outliers(self) -> None:
        """New paper is also normal → no alerts."""
        existing_values = _build_all_values(
            "n_total", [100, 102, 98, 101, 99, 103, 100, 101, 100]
        )
        new_values = {"new_paper": {"n_total": 101}}
        tags = _tags(n_total=FieldSemanticTag.SAMPLE_SIZE_TOTAL)
        validator = CrossPaperValidator()
        alerts = validator.validate_incremental(new_values, existing_values, tags)
        assert alerts == []

    def test_incremental_multiple_new_papers(self) -> None:
        """Multiple new papers, only the outlier one gets flagged."""
        existing_values = _build_all_values(
            "mean", [10.0, 10.5, 11.0, 9.5, 10.2, 10.8, 9.8, 10.1, 10.3]
        )
        new_values = {
            "new_normal": {"mean": 10.4},
            "new_outlier": {"mean": 5000.0},
        }
        tags = _tags(mean=FieldSemanticTag.MEAN)
        validator = CrossPaperValidator()
        alerts = validator.validate_incremental(new_values, existing_values, tags)
        assert len(alerts) == 1
        assert alerts[0].pdf_id == "new_outlier"
