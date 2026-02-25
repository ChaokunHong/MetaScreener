"""Exp1: AMR Internal Validation — Placeholder.

Validates MetaScreener on the authors' own AMR systematic review dataset.
This experiment requires the AMR dataset which is not yet prepared.

Paper Section: Results 3.1

Usage:
    python validation/experiments/exp1_amr_internal.py --seed 42
"""
from __future__ import annotations

import argparse


def main() -> None:
    """Run Exp1: AMR internal validation."""
    parser = argparse.ArgumentParser(description="Exp1: AMR Internal Validation")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="validation/results")
    parser.parse_args()

    raise NotImplementedError(
        "AMR dataset not yet available. "
        "See validation/datasets/README.md for details. "
        "Prepare the AMR dataset and update this script."
    )


if __name__ == "__main__":
    main()
