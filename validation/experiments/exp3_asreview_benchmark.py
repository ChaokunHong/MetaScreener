"""Exp3: ASReview Synergy Benchmark — External Validation.

Screens 26+ ASReview Synergy datasets using TAScreener and evaluates
against gold-standard labels.

Paper Section: Results 3.2

Usage:
    python validation/experiments/exp3_asreview_benchmark.py --seed 42
    python validation/experiments/exp3_asreview_benchmark.py --seed 42 --max-records 50 --mock
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
from metascreener.module1_screening.ta_screener import TAScreener
from validation.common import (
    compute_metrics_with_ci,
    save_results,
    setup_backends,
    setup_mock_backends,
)

logger = structlog.get_logger(__name__)

# Recognized label column names in ASReview Synergy CSVs.
# Checked after lowercasing all column names.
_LABEL_COLUMNS = ("label_included", "included", "label", "relevant")

# Generic PICO criteria for ASReview Synergy datasets.
# Synergy datasets span diverse topics (clinical, software engineering,
# animal studies, etc.), so broad criteria are used for benchmarking the
# ensemble pipeline rather than topic-specific performance.
_ASREVIEW_CRITERIA = PICOCriteria(
    population_include=["humans", "animals", "any study population"],
    intervention_include=["any intervention or exposure"],
    outcome_primary=["any reported outcomes"],
)


def _find_label_column(columns: list[str]) -> str | None:
    """Find the first recognized label column in a list of column names.

    Args:
        columns: Lowercase column names from a DataFrame.

    Returns:
        The recognized column name, or None if no match is found.
    """
    for candidate in _LABEL_COLUMNS:
        if candidate in columns:
            return candidate
    return None


def _find_id_column(columns: list[str]) -> str | None:
    """Find a suitable record ID column in a list of column names.

    Looks for ``record_id`` first, then any column containing ``id``.
    Falls back to the DataFrame index if nothing matches.

    Args:
        columns: Lowercase column names from a DataFrame.

    Returns:
        The column name to use as record ID, or None to use the index.
    """
    if "record_id" in columns:
        return "record_id"
    for col in columns:
        if "id" in col:
            return col
    return None


def _load_dataset_csv(
    dataset_name: str,
    data_dir: Path,
    max_records: int | None = None,
) -> tuple[list[Record], dict[str, int]] | None:
    """Load a single ASReview Synergy dataset CSV and build Record objects.

    Column names are normalized to lowercase. The function detects the
    label and ID columns automatically. Datasets without a recognized
    label column are skipped (returns None).

    Args:
        dataset_name: Name of the dataset (CSV filename stem).
        data_dir: Directory containing the ASReview CSV files.
        max_records: If set, limit to the first N rows.

    Returns:
        Tuple of (list of Record objects, dict mapping record_id to
        binary gold label where 1 = included and 0 = excluded), or
        None if no recognized label column is found.

    Raises:
        FileNotFoundError: If the dataset CSV file does not exist.
    """
    csv_path = data_dir / f"{dataset_name}.csv"
    if not csv_path.exists():
        msg = f"ASReview dataset CSV not found: {csv_path}"
        raise FileNotFoundError(msg)

    df = pd.read_csv(csv_path)

    # Normalize column names to lowercase
    df.columns = [c.strip().lower() for c in df.columns]

    # Find label column
    label_col = _find_label_column(list(df.columns))
    if label_col is None:
        logger.warning(
            "skipping_dataset_no_label_column",
            dataset=dataset_name,
            columns=list(df.columns),
        )
        return None

    # Find ID column
    id_col = _find_id_column(list(df.columns))

    if max_records is not None:
        df = df.head(max_records)

    records: list[Record] = []
    gold_labels: dict[str, int] = {}

    for idx, row in df.iterrows():
        # Use detected ID column or fall back to row index
        record_id = str(row[id_col]) if id_col else str(idx)

        # Title: try "title" column, fall back to empty
        title = ""
        if "title" in df.columns and pd.notna(row.get("title")):
            title = str(row["title"]).strip()

        # Abstract: try common abstract column names
        abstract: str | None = None
        for abs_col in ("abstract", "abstracts", "abstract_text"):
            if abs_col in df.columns and pd.notna(row.get(abs_col)):
                abstract = str(row[abs_col])
                break

        # Skip rows with empty titles (Pydantic min_length=1)
        if not title:
            logger.warning(
                "skipping_empty_title",
                record_id=record_id,
                dataset=dataset_name,
            )
            continue

        # Parse label — skip rows with missing labels
        label_val = row[label_col]
        if pd.isna(label_val):
            logger.warning(
                "skipping_missing_label",
                record_id=record_id,
                dataset=dataset_name,
            )
            continue

        records.append(
            Record(
                record_id=record_id,
                title=title,
                abstract=abstract,
            )
        )
        gold_labels[record_id] = int(label_val)

    logger.info(
        "dataset_loaded",
        dataset=dataset_name,
        n_records=len(records),
        n_included=sum(gold_labels.values()),
        n_excluded=len(gold_labels) - sum(gold_labels.values()),
        label_col=label_col,
        id_col=id_col or "index",
    )

    return records, gold_labels


async def run_single_dataset(
    dataset_name: str,
    data_dir: Path,
    use_mock: bool = False,
    seed: int = 42,
    max_records: int | None = None,
) -> dict[str, Any] | None:
    """Run the HCN screening pipeline on a single ASReview dataset.

    Loads the dataset CSV, screens all records via TAScreener, converts
    decisions to binary predictions, and computes metrics with bootstrap
    confidence intervals.

    Args:
        dataset_name: Name of the ASReview dataset (CSV filename stem).
        data_dir: Directory containing the ASReview CSV files.
        use_mock: If True, use mock LLM backends for offline testing.
        seed: Random seed for reproducibility.
        max_records: If set, limit to the first N records.

    Returns:
        Dictionary with keys: ``dataset``, ``n_records``, ``n_included``,
        ``metrics`` (each metric has ``point``, ``ci_lower``, ``ci_upper``),
        or None if the dataset was skipped (no label column found).

    Raises:
        FileNotFoundError: If the dataset CSV file does not exist.
    """
    loaded = _load_dataset_csv(dataset_name, data_dir, max_records)
    if loaded is None:
        return None

    records, gold_labels = loaded

    # Set up backends
    backends = setup_mock_backends() if use_mock else setup_backends()
    screener = TAScreener(backends=backends)

    logger.info(
        "screening_started",
        dataset=dataset_name,
        n_records=len(records),
        use_mock=use_mock,
        seed=seed,
    )

    # Screen all records
    decisions = await screener.screen_batch(records, _ASREVIEW_CRITERIA, seed=seed)

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
        "dataset": dataset_name,
        "n_records": len(records),
        "n_included": sum(gold_labels.values()),
        "metrics": metrics,
    }

    logger.info(
        "dataset_complete",
        dataset=dataset_name,
        n_records=len(records),
        sensitivity=metrics.get("sensitivity", {}).get("point"),
        specificity=metrics.get("specificity", {}).get("point"),
    )

    return result


async def run_all_datasets(
    data_dir: Path,
    use_mock: bool = False,
    seed: int = 42,
    max_records: int | None = None,
    output_dir: Path = Path("validation/results"),
) -> dict[str, Any]:
    """Run the ASReview Synergy benchmark across all available datasets.

    Discovers all CSV files in the data directory, runs screening for
    each, computes per-dataset metrics, and aggregates macro-average
    metrics across all datasets.

    Args:
        data_dir: Directory containing ASReview CSV files.
        use_mock: If True, use mock LLM backends.
        seed: Random seed for reproducibility.
        max_records: If set, limit records per dataset.
        output_dir: Directory to save the results JSON.

    Returns:
        Dictionary with keys: ``per_dataset`` (list of per-dataset results),
        ``macro_average`` (averaged metrics across datasets),
        ``n_datasets`` (number of datasets successfully processed),
        ``n_skipped`` (number of datasets skipped due to missing labels).
    """
    # Discover all CSV files in the ASReview data directory
    available_datasets: list[str] = sorted(
        csv_file.stem for csv_file in data_dir.glob("*.csv")
    )

    logger.info(
        "benchmark_started",
        n_available=len(available_datasets),
        datasets=available_datasets,
    )

    per_dataset: list[dict[str, Any]] = []
    n_skipped = 0

    for dataset_name in available_datasets:
        dataset_result = await run_single_dataset(
            dataset_name=dataset_name,
            data_dir=data_dir,
            use_mock=use_mock,
            seed=seed,
            max_records=max_records,
        )
        if dataset_result is None:
            n_skipped += 1
            continue
        per_dataset.append(dataset_result)

    # Compute macro-average across datasets
    macro_average: dict[str, dict[str, float]] = {}
    if per_dataset:
        # Collect all metric names from the first dataset
        metric_names = list(per_dataset[0]["metrics"].keys())
        for metric_name in metric_names:
            points = [
                d["metrics"][metric_name]["point"]
                for d in per_dataset
                if metric_name in d["metrics"]
            ]
            ci_lowers = [
                d["metrics"][metric_name]["ci_lower"]
                for d in per_dataset
                if metric_name in d["metrics"]
            ]
            ci_uppers = [
                d["metrics"][metric_name]["ci_upper"]
                for d in per_dataset
                if metric_name in d["metrics"]
            ]
            if points:
                macro_average[metric_name] = {
                    "point": sum(points) / len(points),
                    "ci_lower": sum(ci_lowers) / len(ci_lowers),
                    "ci_upper": sum(ci_uppers) / len(ci_uppers),
                }

    aggregated: dict[str, Any] = {
        "per_dataset": per_dataset,
        "macro_average": macro_average,
        "n_datasets": len(per_dataset),
        "n_skipped": n_skipped,
    }

    # Save results
    save_results(
        results=aggregated,
        experiment_name="exp3_asreview_benchmark",
        output_dir=output_dir,
        seed=seed,
    )

    logger.info(
        "benchmark_complete",
        n_datasets=len(per_dataset),
        n_skipped=n_skipped,
        macro_sensitivity=macro_average.get("sensitivity", {}).get("point"),
        macro_specificity=macro_average.get("specificity", {}).get("point"),
    )

    return aggregated


def main() -> None:
    """CLI entry point for Exp3: ASReview Synergy benchmark."""
    parser = argparse.ArgumentParser(
        description="Exp3: ASReview Synergy Benchmark — 26+ systematic review datasets"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Limit records per dataset for quick testing",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock LLM backends (offline, no API calls)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="validation/datasets/asreview",
        help="Directory containing ASReview Synergy CSV files",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="validation/results",
        help="Directory to save experiment results",
    )
    args = parser.parse_args()

    asyncio.run(
        run_all_datasets(
            data_dir=Path(args.data_dir),
            use_mock=args.mock,
            seed=args.seed,
            max_records=args.max_records,
            output_dir=Path(args.output_dir),
        )
    )


if __name__ == "__main__":
    main()
