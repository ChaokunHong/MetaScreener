"""Verify that all HCN screener modules can be imported without errors."""
from __future__ import annotations


def test_import_element_consensus() -> None:
    from metascreener.module1_screening.layer3.element_consensus import (
        build_element_consensus,
        compute_ecs,
    )
    assert callable(build_element_consensus)
    assert callable(compute_ecs)


def test_import_disagreement() -> None:
    from metascreener.module1_screening.layer3.disagreement import (
        classify_disagreement,
    )
    assert callable(classify_disagreement)


def test_import_heuristic_calibrator() -> None:
    from metascreener.module1_screening.layer3.heuristic_calibrator import (
        get_calibration_factors,
    )
    assert callable(get_calibration_factors)


def test_import_hcn_screener() -> None:
    from metascreener.module1_screening.hcn_screener import HCNScreener
    assert HCNScreener is not None


def test_import_ft_screener() -> None:
    from metascreener.module1_screening.ft_screener import FTScreener
    assert FTScreener is not None


def test_import_chunk_heterogeneity() -> None:
    from metascreener.module1_screening.chunk_heterogeneity import (
        compute_chunk_heterogeneity,
    )
    assert callable(compute_chunk_heterogeneity)
