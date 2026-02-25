"""Exp4: Ablation Study — Component Contribution Analysis.

Compares 6 configurations to quantify the contribution of each HCN component:
1. Single model (Qwen3 only)
2. Single model (DeepSeek only)
3. Single model (Llama 4 only)
4. Single model (Mistral only)
5. Ensemble without Layer 2 rules
6. Full HCN pipeline

Paper Section: Results 3.3

Usage:
    python validation/experiments/exp4_ablation_study.py --data path/to/data.csv --seed 42
    python validation/experiments/exp4_ablation_study.py --data path/to/data.csv --mock
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import PICOCriteria, Record
from metascreener.module1_screening.layer2.rule_engine import RuleEngine
from metascreener.module1_screening.ta_screener import TAScreener
from validation.common import (
    compute_metrics_with_ci,
    save_results,
    setup_backends,
    setup_mock_backends,
)

logger = structlog.get_logger(__name__)

# Generic PICO criteria for ablation experiments.
_ABLATION_CRITERIA = PICOCriteria(
    population_include=["humans"],
    intervention_include=["any intervention"],
    outcome_primary=["clinical outcomes"],
)

# Configuration definitions: (name, backend_indices, use_rules)
# backend_indices=None means all backends; list[int] selects specific ones.
_CONFIGURATIONS: list[tuple[str, list[int] | None, bool]] = [
    ("single_qwen3", [0], True),
    ("single_deepseek", [1], True),
    ("single_llama4", [2], True),
    ("single_mistral", [3], True),
    ("ensemble_no_rules", None, False),
    ("full_hcn", None, True),
]


def _load_ablation_csv(
    data_path: Path,
) -> tuple[list[Record], dict[str, int]]:
    """Load a single CSV file and build Record objects with gold labels.

    Args:
        data_path: Path to the CSV file with columns record_id, title,
            abstract, and label (1 = include, 0 = exclude).

    Returns:
        Tuple of (list of Record objects, dict mapping record_id to
        binary gold label).

    Raises:
        FileNotFoundError: If the CSV file does not exist.
    """
    if not data_path.exists():
        msg = f"Ablation data CSV not found: {data_path}"
        raise FileNotFoundError(msg)

    df = pd.read_csv(data_path)

    records: list[Record] = []
    gold_labels: dict[str, int] = {}

    for _, row in df.iterrows():
        record_id = str(row["record_id"])
        title = str(row["title"]).strip() if pd.notna(row["title"]) else ""
        abstract = str(row["abstract"]) if pd.notna(row.get("abstract")) else None

        # Skip rows with empty titles (Pydantic min_length=1)
        if not title:
            logger.warning("skipping_empty_title", record_id=record_id)
            continue

        records.append(
            Record(
                record_id=record_id,
                title=title,
                abstract=abstract,
            )
        )
        gold_labels[record_id] = int(row["label"])

    logger.info(
        "ablation_data_loaded",
        path=str(data_path),
        n_records=len(records),
        n_included=sum(gold_labels.values()),
        n_excluded=len(gold_labels) - sum(gold_labels.values()),
    )

    return records, gold_labels


async def _run_single_config(
    config_name: str,
    screener: TAScreener,
    records: list[Record],
    gold_labels: dict[str, int],
    seed: int = 42,
    use_mock: bool = False,
) -> dict[str, Any]:
    """Run a single ablation configuration and compute metrics.

    Args:
        config_name: Name of the configuration.
        screener: The TAScreener instance for this configuration.
        records: List of Record objects to screen.
        gold_labels: Gold-standard labels for metric computation.
        seed: Random seed for reproducibility.
        use_mock: Whether mock backends are in use (affects bootstrap N).

    Returns:
        Dictionary with config name, record count, and metrics.
    """
    logger.info(
        "config_started",
        config=config_name,
        n_records=len(records),
    )

    decisions = await screener.screen_batch(records, _ABLATION_CRITERIA, seed=seed)

    # Convert to binary arrays aligned by record_id
    y_true: list[int] = []
    y_pred: list[int] = []
    y_score: list[float] = []

    for dec in decisions:
        if dec.record_id not in gold_labels:
            logger.warning("missing_gold_label", record_id=dec.record_id)
            continue

        y_true.append(gold_labels[dec.record_id])
        y_pred.append(1 if dec.decision == Decision.INCLUDE else 0)
        y_score.append(dec.final_score)

    # Compute metrics with bootstrap CI
    n_bootstrap = 50 if use_mock else 1000
    metrics = compute_metrics_with_ci(
        y_true=y_true,
        y_pred=y_pred,
        y_score=y_score,
        seed=seed,
        n_bootstrap=n_bootstrap,
    )

    result: dict[str, Any] = {
        "name": config_name,
        "n_records": len(records),
        "metrics": metrics,
    }

    logger.info(
        "config_complete",
        config=config_name,
        sensitivity=metrics.get("sensitivity", {}).get("point"),
        specificity=metrics.get("specificity", {}).get("point"),
    )

    return result


async def run_ablation(
    data_path: Path,
    seed: int = 42,
    use_mock: bool = True,
    output_dir: Path = Path("validation/results"),
) -> dict[str, Any]:
    """Run the full ablation study across all 6 configurations.

    Loads the dataset, creates backends, runs each configuration
    (single-model, ensemble without rules, full HCN), and computes
    per-configuration metrics with bootstrap confidence intervals.

    Args:
        data_path: Path to the CSV file with columns record_id, title,
            abstract, and label.
        seed: Random seed for reproducibility.
        use_mock: If True, use mock LLM backends for offline testing.
        output_dir: Directory to save the results JSON.

    Returns:
        Dictionary with keys: ``experiment``, ``n_configurations``,
        ``configurations`` (list of per-config results).

    Raises:
        FileNotFoundError: If the data CSV does not exist.
    """
    records, gold_labels = _load_ablation_csv(data_path)

    # Set up backends
    all_backends = setup_mock_backends() if use_mock else setup_backends()

    logger.info(
        "ablation_started",
        n_records=len(records),
        n_backends=len(all_backends),
        n_configurations=len(_CONFIGURATIONS),
        use_mock=use_mock,
        seed=seed,
    )

    configurations: list[dict[str, Any]] = []

    for config_name, backend_indices, use_rules in _CONFIGURATIONS:
        # Select backends for this configuration
        if backend_indices is not None:
            selected_backends = [all_backends[i] for i in backend_indices]
        else:
            selected_backends = all_backends

        # Build rule engine: empty rules if use_rules is False
        rule_engine = None if use_rules else RuleEngine(rules=[])

        # Create screener for this configuration
        screener = TAScreener(
            backends=selected_backends,
            rule_engine=rule_engine,
        )

        config_result = await _run_single_config(
            config_name=config_name,
            screener=screener,
            records=records,
            gold_labels=gold_labels,
            seed=seed,
            use_mock=use_mock,
        )
        configurations.append(config_result)

    result: dict[str, Any] = {
        "experiment": "exp4_ablation_study",
        "n_configurations": len(configurations),
        "configurations": configurations,
    }

    # Save results
    save_results(
        results=result,
        experiment_name="exp4_ablation_study",
        output_dir=output_dir,
        seed=seed,
    )

    logger.info(
        "ablation_complete",
        n_configurations=len(configurations),
    )

    return result


def main() -> None:
    """CLI entry point for Exp4: Ablation Study."""
    parser = argparse.ArgumentParser(
        description="Exp4: Ablation Study — Component Contribution Analysis"
    )
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path to the CSV dataset (record_id, title, abstract, label)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock LLM backends (offline, no API calls)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="validation/results",
        help="Directory to save experiment results",
    )
    args = parser.parse_args()

    asyncio.run(
        run_ablation(
            data_path=Path(args.data),
            seed=args.seed,
            use_mock=args.mock,
            output_dir=Path(args.output_dir),
        )
    )


if __name__ == "__main__":
    main()
