"""Exp6: RoB Reliability — Placeholder.

Validates Module 3 (RoB assessment) against human rater assessments.
This experiment requires the AMR dataset which is not yet prepared.

Paper Section: Results 3.5

Usage:
    python validation/experiments/exp6_rob_reliability.py --seed 42
"""
from __future__ import annotations

import argparse


def main() -> None:
    """Run Exp6: RoB reliability validation."""
    parser = argparse.ArgumentParser(description="Exp6: RoB Reliability")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="validation/results")
    parser.parse_args()

    raise NotImplementedError(
        "AMR dataset with human RoB ratings not yet available. "
        "See validation/datasets/README.md for details. "
        "Prepare the AMR dataset and update this script."
    )


if __name__ == "__main__":
    main()
