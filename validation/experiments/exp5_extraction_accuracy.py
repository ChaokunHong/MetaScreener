"""Exp5: Data Extraction Accuracy — Placeholder.

Validates Module 2 (data extraction) against manually extracted data.
This experiment requires the AMR dataset which is not yet prepared.

Paper Section: Results 3.4

Usage:
    python validation/experiments/exp5_extraction_accuracy.py --seed 42
"""
from __future__ import annotations

import argparse


def main() -> None:
    """Run Exp5: data extraction accuracy validation."""
    parser = argparse.ArgumentParser(description="Exp5: Data Extraction Accuracy")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="validation/results")
    parser.parse_args()

    raise NotImplementedError(
        "AMR dataset with extraction gold standard not yet available. "
        "See validation/datasets/README.md for details. "
        "Prepare the AMR dataset and update this script."
    )


if __name__ == "__main__":
    main()
