from __future__ import annotations

from experiments.scripts.fp_majority_vote import majority_vote


def test_majority_vote_returns_two_of_three() -> None:
    verdict, agreement, n_valid = majority_vote(
        ["label_error", "genuine_fp", "label_error"]
    )

    assert verdict == "label_error"
    assert agreement == "2/3"
    assert n_valid == 3


def test_majority_vote_no_majority_becomes_ambiguous() -> None:
    verdict, agreement, n_valid = majority_vote(
        ["label_error", "genuine_fp", "ambiguous"]
    )

    assert verdict == "ambiguous"
    assert agreement == "no_majority/3"
    assert n_valid == 3


def test_majority_vote_ignores_error_values() -> None:
    verdict, agreement, n_valid = majority_vote(["error", "label_error", "label_error"])

    assert verdict == "label_error"
    assert agreement == "2/2"
    assert n_valid == 2
