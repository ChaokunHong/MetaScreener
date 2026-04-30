"""Tests for the effect size computation engine."""
from __future__ import annotations
import math
import pytest

from metascreener.module2_extraction.engine.computation import ComputationEngine


@pytest.fixture
def engine() -> ComputationEngine:
    return ComputationEngine()


def test_odds_ratio(engine: ComputationEngine) -> None:
    result = engine.compute("odds_ratio", a=10, b=40, c=30, d=20)
    assert result is not None
    assert abs(result - (10 * 20) / (40 * 30)) < 1e-6


def test_risk_ratio(engine: ComputationEngine) -> None:
    result = engine.compute("risk_ratio", e1=10, n1=50, e2=30, n2=50)
    assert result is not None
    assert abs(result - (10 / 50) / (30 / 50)) < 1e-6


def test_mean_difference(engine: ComputationEngine) -> None:
    result = engine.compute("mean_difference", m1=55.2, m2=54.8)
    assert result is not None
    assert abs(result - 0.4) < 1e-6


def test_ci_from_or_and_se(engine: ComputationEngine) -> None:
    lower = engine.compute("ci_lower_or", or_val=0.75, se=0.3)
    upper = engine.compute("ci_upper_or", or_val=0.75, se=0.3)
    assert lower is not None
    assert upper is not None
    assert lower < 0.75 < upper


def test_nnt(engine: ComputationEngine) -> None:
    assert abs(engine.compute("nnt", arr=0.1) - 10.0) < 1e-6  # type: ignore[operator]


def test_nnt_zero_arr(engine: ComputationEngine) -> None:
    assert engine.compute("nnt", arr=0.0) is None


def test_se_from_ci(engine: ComputationEngine) -> None:
    result = engine.compute("se_from_ci", ci_lo=0.5, ci_hi=1.5)
    expected = (math.log(1.5) - math.log(0.5)) / 3.92
    assert result is not None
    assert abs(result - expected) < 1e-6


def test_missing_dependency(engine: ComputationEngine) -> None:
    assert engine.compute("odds_ratio", a=10, b=None, c=30, d=20) is None


def test_unknown_formula(engine: ComputationEngine) -> None:
    assert engine.compute("nonexistent", x=1) is None


def test_division_by_zero(engine: ComputationEngine) -> None:
    assert engine.compute("risk_ratio", e1=10, n1=50, e2=0, n2=50) is None


def test_odds_ratio_zero_denominator(engine: ComputationEngine) -> None:
    """b*c == 0 should return None."""
    assert engine.compute("odds_ratio", a=10, b=0, c=30, d=20) is None


def test_ci_lower_or_nonpositive(engine: ComputationEngine) -> None:
    """or_val <= 0 should return None."""
    assert engine.compute("ci_lower_or", or_val=0.0, se=0.3) is None
    assert engine.compute("ci_lower_or", or_val=-1.0, se=0.3) is None


def test_ci_upper_or_nonpositive(engine: ComputationEngine) -> None:
    """or_val <= 0 should return None."""
    assert engine.compute("ci_upper_or", or_val=0.0, se=0.3) is None


def test_se_from_ci_nonpositive(engine: ComputationEngine) -> None:
    """ci_lo <= 0 or ci_hi <= 0 should return None."""
    assert engine.compute("se_from_ci", ci_lo=0.0, ci_hi=1.5) is None
    assert engine.compute("se_from_ci", ci_lo=0.5, ci_hi=0.0) is None


def test_mean_difference_negative(engine: ComputationEngine) -> None:
    result = engine.compute("mean_difference", m1=50.0, m2=55.0)
    assert result is not None
    assert abs(result - (-5.0)) < 1e-6


def test_nnt_negative_arr(engine: ComputationEngine) -> None:
    """abs() ensures NNT is positive for negative ARR."""
    result = engine.compute("nnt", arr=-0.2)
    assert result is not None
    assert abs(result - 5.0) < 1e-6
