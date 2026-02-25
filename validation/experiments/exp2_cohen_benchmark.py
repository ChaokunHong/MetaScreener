"""Exp2: Cohen 2006 Benchmark — 15 systematic review topics.

Validates MetaScreener's title/abstract screening against the Cohen et al.
(2006) benchmark dataset containing ~14,000 labelled papers across 15
drug-therapy systematic review topics.

Paper Section: Results 3.2

Usage:
    python validation/experiments/exp2_cohen_benchmark.py --seed 42
    python validation/experiments/exp2_cohen_benchmark.py --mock --max-records 20
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
from validation.datasets.download_cohen import COHEN_TOPICS

logger = structlog.get_logger(__name__)

# Generic PICO criteria for Cohen drug-therapy topics.
# All 15 Cohen topics are drug-therapy SRs in human populations,
# so a single set of broad criteria is appropriate for benchmarking.
_COHEN_CRITERIA = PICOCriteria(
    population_include=["humans"],
    intervention_include=["drug therapy"],
    outcome_primary=["clinical outcomes"],
)


def _load_topic_csv(
    topic_name: str,
    data_dir: Path,
    max_records: int | None = None,
) -> tuple[list[Record], dict[str, int]]:
    """Load a single Cohen topic CSV and build Record objects.

    Args:
        topic_name: Name of the Cohen topic (e.g., "ACEInhibitors").
        data_dir: Directory containing the topic CSV files.
        max_records: If set, limit to the first N rows.

    Returns:
        Tuple of (list of Record objects, dict mapping record_id to
        binary gold label where 1 = included and 0 = excluded).

    Raises:
        FileNotFoundError: If the topic CSV file does not exist.
    """
    csv_path = data_dir / f"{topic_name}.csv"
    if not csv_path.exists():
        msg = f"Cohen topic CSV not found: {csv_path}"
        raise FileNotFoundError(msg)

    df = pd.read_csv(csv_path)

    if max_records is not None:
        df = df.head(max_records)

    records: list[Record] = []
    gold_labels: dict[str, int] = {}

    for _, row in df.iterrows():
        record_id = str(row["record_id"])
        title = str(row["title"]).strip() if pd.notna(row["title"]) else ""
        abstract = str(row["abstract"]) if pd.notna(row.get("abstract")) else None

        # Skip rows with empty titles (Pydantic min_length=1)
        if not title:
            logger.warning("skipping_empty_title", record_id=record_id, topic=topic_name)
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
        "topic_loaded",
        topic=topic_name,
        n_records=len(records),
        n_included=sum(gold_labels.values()),
        n_excluded=len(gold_labels) - sum(gold_labels.values()),
    )

    return records, gold_labels


async def run_single_topic(
    topic_name: str,
    data_dir: Path,
    use_mock: bool = False,
    seed: int = 42,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Run the HCN screening pipeline on a single Cohen topic.

    Loads the topic CSV, screens all records via TAScreener, converts
    decisions to binary predictions, and computes metrics with bootstrap
    confidence intervals.

    Args:
        topic_name: Name of the Cohen topic (e.g., "ACEInhibitors").
        data_dir: Directory containing the topic CSV files.
        use_mock: If True, use mock LLM backends for offline testing.
        seed: Random seed for reproducibility.
        max_records: If set, limit to the first N records.

    Returns:
        Dictionary with keys: ``topic``, ``n_records``, ``n_included``,
        ``metrics`` (each metric has ``point``, ``ci_lower``, ``ci_upper``).

    Raises:
        FileNotFoundError: If the topic CSV file does not exist.
    """
    records, gold_labels = _load_topic_csv(topic_name, data_dir, max_records)

    # Set up backends
    backends = setup_mock_backends() if use_mock else setup_backends()
    screener = TAScreener(backends=backends)

    logger.info(
        "screening_started",
        topic=topic_name,
        n_records=len(records),
        use_mock=use_mock,
        seed=seed,
    )

    # Screen all records
    decisions = await screener.screen_batch(records, _COHEN_CRITERIA, seed=seed)

    # Convert to binary arrays aligned by record_id
    y_true: list[int] = []
    y_pred: list[int] = []
    y_score: list[float] = []

    for dec in decisions:
        if dec.record_id not in gold_labels:
            logger.warning("missing_gold_label", record_id=dec.record_id)
            continue

        y_true.append(gold_labels[dec.record_id])
        # Treat HUMAN_REVIEW as INCLUDE (recall-safe default)
        y_pred.append(
            1 if dec.decision in (Decision.INCLUDE, Decision.HUMAN_REVIEW) else 0
        )
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
        "topic": topic_name,
        "n_records": len(records),
        "n_included": sum(gold_labels.values()),
        "metrics": metrics,
    }

    logger.info(
        "topic_complete",
        topic=topic_name,
        n_records=len(records),
        sensitivity=metrics.get("sensitivity", {}).get("point"),
        specificity=metrics.get("specificity", {}).get("point"),
    )

    return result


async def run_all_topics(
    data_dir: Path,
    use_mock: bool = False,
    seed: int = 42,
    max_records: int | None = None,
    output_dir: Path = Path("validation/results"),
) -> dict[str, Any]:
    """Run the Cohen benchmark across all available topics.

    Iterates over all Cohen topics with available CSV files, runs
    screening for each, computes per-topic metrics, and aggregates
    macro-average metrics across all topics.

    Args:
        data_dir: Directory containing topic CSV files.
        use_mock: If True, use mock LLM backends.
        seed: Random seed for reproducibility.
        max_records: If set, limit records per topic.
        output_dir: Directory to save the results JSON.

    Returns:
        Dictionary with keys: ``per_topic`` (list of per-topic results),
        ``macro_average`` (averaged metrics across topics),
        ``n_topics`` (number of topics processed).
    """
    # Find available topic CSVs
    available_topics: list[str] = []
    for topic in COHEN_TOPICS:
        if (data_dir / f"{topic}.csv").exists():
            available_topics.append(topic)

    # Also pick up any non-standard topic CSVs (e.g., synthetic test data)
    for csv_file in sorted(data_dir.glob("*.csv")):
        topic = csv_file.stem
        if topic not in available_topics:
            available_topics.append(topic)

    logger.info(
        "benchmark_started",
        n_available=len(available_topics),
        n_total_cohen=len(COHEN_TOPICS),
        topics=available_topics,
    )

    per_topic: list[dict[str, Any]] = []
    for topic in available_topics:
        topic_result = await run_single_topic(
            topic_name=topic,
            data_dir=data_dir,
            use_mock=use_mock,
            seed=seed,
            max_records=max_records,
        )
        per_topic.append(topic_result)

    # Compute macro-average across topics with proper CI
    # CI is derived from the distribution of per-topic point estimates
    # (not by averaging per-topic CI bounds, which is statistically invalid)
    macro_average: dict[str, dict[str, float]] = {}
    if per_topic:
        metric_names = list(per_topic[0]["metrics"].keys())
        for metric_name in metric_names:
            points = [
                t["metrics"][metric_name]["point"]
                for t in per_topic
                if metric_name in t["metrics"]
            ]
            if points:
                mean_val = sum(points) / len(points)
                if len(points) >= 2:
                    # 95% CI from SD of per-topic point estimates
                    variance = sum((p - mean_val) ** 2 for p in points) / (
                        len(points) - 1
                    )
                    se = (variance / len(points)) ** 0.5
                    ci_lower = mean_val - 1.96 * se
                    ci_upper = mean_val + 1.96 * se
                else:
                    ci_lower = mean_val
                    ci_upper = mean_val
                macro_average[metric_name] = {
                    "point": mean_val,
                    "ci_lower": ci_lower,
                    "ci_upper": ci_upper,
                }

    aggregated: dict[str, Any] = {
        "per_topic": per_topic,
        "macro_average": macro_average,
        "n_topics": len(per_topic),
    }

    # Save results
    save_results(
        results=aggregated,
        experiment_name="exp2_cohen_benchmark",
        output_dir=output_dir,
        seed=seed,
    )

    logger.info(
        "benchmark_complete",
        n_topics=len(per_topic),
        macro_sensitivity=macro_average.get("sensitivity", {}).get("point"),
        macro_specificity=macro_average.get("specificity", {}).get("point"),
    )

    return aggregated


def main() -> None:
    """CLI entry point for Exp2: Cohen 2006 benchmark."""
    parser = argparse.ArgumentParser(
        description="Exp2: Cohen 2006 Benchmark — 15 systematic review topics"
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
        help="Limit records per topic for quick testing",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock LLM backends (offline, no API calls)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="validation/datasets/cohen",
        help="Directory containing Cohen topic CSV files",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="validation/results",
        help="Directory to save experiment results",
    )
    args = parser.parse_args()

    asyncio.run(
        run_all_topics(
            data_dir=Path(args.data_dir),
            use_mock=args.mock,
            seed=args.seed,
            max_records=args.max_records,
            output_dir=Path(args.output_dir),
        )
    )


if __name__ == "__main__":
    main()
