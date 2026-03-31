"""Tests for Evidence Sentence Alignment Score (ESAS)."""

import pytest

from metascreener.module1_screening.layer3.evidence_alignment import (
    compute_esas,
    esas_modulation,
    token_jaccard,
)


class TestTokenJaccard:
    def test_identical_strings(self) -> None:
        assert token_jaccard("hello world", "hello world") == 1.0

    def test_completely_different(self) -> None:
        assert token_jaccard("hello world", "foo bar") == 0.0

    def test_partial_overlap(self) -> None:
        j = token_jaccard("the cat sat", "the dog sat")
        assert abs(j - 2.0 / 4.0) < 1e-10

    def test_empty_string(self) -> None:
        assert token_jaccard("", "hello") == 0.0
        assert token_jaccard("hello", "") == 0.0
        assert token_jaccard("", "") == 0.0


class TestESASModulation:
    def test_above_tau_boosts(self) -> None:
        result = esas_modulation(0.8, mean_esas=0.7, gamma=0.3, tau=0.5)
        expected = 0.8 * (1.0 + 0.3 * (0.7 - 0.5))
        assert abs(result - expected) < 1e-10

    def test_below_tau_no_change(self) -> None:
        result = esas_modulation(0.8, mean_esas=0.3, gamma=0.3, tau=0.5)
        assert result == 0.8

    def test_at_tau_no_change(self) -> None:
        result = esas_modulation(0.8, mean_esas=0.5, gamma=0.3, tau=0.5)
        assert result == 0.8

    def test_never_decreases(self) -> None:
        for esas in [0.0, 0.3, 0.5, 0.7, 1.0]:
            result = esas_modulation(0.5, mean_esas=esas)
            assert result >= 0.5 - 1e-10
