"""Tests for geometric ECS computation."""

import numpy as np
import pytest

from metascreener.core.enums import ConflictPattern
from metascreener.core.models_consensus import ElementConsensus, ECSResult
from metascreener.module1_screening.layer3.element_consensus import (
    compute_ecs_geometric,
    compute_ecs,
)


def _make_consensus(name: str, support_ratio: float | None) -> ElementConsensus:
    if support_ratio is None:
        return ElementConsensus(
            name=name, required=True, exclusion_relevant=True,
            n_match=0, n_mismatch=0, n_unclear=4,
        )
    n_match = int(support_ratio * 4)
    n_mismatch = 4 - n_match
    return ElementConsensus(
        name=name, required=True, exclusion_relevant=True,
        n_match=n_match, n_mismatch=n_mismatch, n_unclear=0,
        support_ratio=support_ratio,
    )


class TestGeometricECS:
    def test_all_high_scores(self) -> None:
        ec = {
            "population": _make_consensus("population", 0.9),
            "intervention": _make_consensus("intervention", 0.9),
            "outcome": _make_consensus("outcome", 0.9),
        }
        weights = {"population": 1.0, "intervention": 1.0, "outcome": 0.8}
        result = compute_ecs_geometric(ec, weights)
        assert 0.85 < result.score < 0.95

    def test_one_very_low_triggers_conditional_min(self) -> None:
        ec = {
            "population": _make_consensus("population", 0.9),
            "intervention": _make_consensus("intervention", 0.05),
            "outcome": _make_consensus("outcome", 0.9),
        }
        weights = {"population": 1.0, "intervention": 1.0, "outcome": 0.8}
        result = compute_ecs_geometric(ec, weights, min_threshold=0.20)
        assert result.score < 0.10

    def test_all_zero_returns_near_epsilon(self) -> None:
        ec = {
            "population": _make_consensus("population", 0.0),
            "intervention": _make_consensus("intervention", 0.0),
        }
        weights = {"population": 1.0, "intervention": 1.0}
        result = compute_ecs_geometric(ec, weights, epsilon=0.01)
        assert result.score < 0.05

    def test_single_element(self) -> None:
        ec = {"population": _make_consensus("population", 0.7)}
        weights = {"population": 1.0}
        result = compute_ecs_geometric(ec, weights)
        assert abs(result.score - (0.7 + 0.01)) < 0.05

    def test_trim_clips_outlier(self) -> None:
        ec = {
            "p": _make_consensus("p", 0.01),
            "i": _make_consensus("i", 0.8),
            "c": _make_consensus("c", 0.8),
            "o": _make_consensus("o", 0.8),
        }
        weights = {"p": 1.0, "i": 1.0, "c": 1.0, "o": 1.0}
        result_trimmed = compute_ecs_geometric(ec, weights, trim_percentile=0.10, min_threshold=0.0)
        result_untrimmed = compute_ecs_geometric(ec, weights, trim_percentile=0.0, min_threshold=0.0)
        assert result_trimmed.score > result_untrimmed.score

    def test_empty_consensus_returns_half(self) -> None:
        result = compute_ecs_geometric({}, {})
        assert abs(result.score - 0.5) < 1e-10

    def test_returns_ecs_result_type(self) -> None:
        ec = {"p": _make_consensus("p", 0.8)}
        result = compute_ecs_geometric(ec, {"p": 1.0})
        assert isinstance(result, ECSResult)
        assert "p" in result.element_scores

    def test_geometric_lower_than_arithmetic_with_spread(self) -> None:
        ec = {
            "p": _make_consensus("p", 0.3),
            "i": _make_consensus("i", 0.9),
        }
        weights = {"p": 1.0, "i": 1.0}
        geo = compute_ecs_geometric(ec, weights, min_threshold=0.0)
        arith = compute_ecs(ec, weights)
        assert geo.score <= arith.score + 0.01
