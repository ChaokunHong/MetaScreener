"""Exp4b: Full-Text Ablation Study — Chunking & Penalty Sensitivity.

Sweeps chunking threshold and FT penalty multiplier to empirically
justify the engineering defaults (30K threshold, 1.3× multiplier).
Generates sensitivity/specificity curves across 9 configurations:

| Config            | chunk_threshold | ft_penalty_multiplier |
|-------------------|----------------|-----------------------|
| threshold_15k     | 15,000         | 1.3                   |
| threshold_25k     | 25,000         | 1.3                   |
| threshold_30k     | 30,000         | 1.3 (default)         |
| threshold_35k     | 35,000         | 1.3                   |
| no_chunking       | sys.maxsize    | 1.3                   |
| multiplier_1_0    | 30,000         | 1.0                   |
| multiplier_1_2    | 30,000         | 1.2                   |
| multiplier_1_4    | 30,000         | 1.4                   |
| full_ft_default   | 30,000         | 1.3 (baseline)        |

Paper Section: Results 3.3 (companion to Exp4)

Usage:
    python validation/experiments/exp4b_ft_ablation.py --data path/to/ft_data.csv --seed 42
    python validation/experiments/exp4b_ft_ablation.py --data path/to/ft_data.csv --mock
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from metascreener.core.enums import Decision
from metascreener.core.models import PICOCriteria, Record
from metascreener.module1_screening.ft_screener import FTScreener
from metascreener.module1_screening.layer2.rule_engine import RuleEngine
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

# Ablation configurations: (name, chunk_threshold, ft_penalty_multiplier)
_CONFIGURATIONS: list[tuple[str, int, float]] = [
    ("threshold_15k", 15_000, 1.3),
    ("threshold_25k", 25_000, 1.3),
    ("threshold_30k", 30_000, 1.3),
    ("threshold_35k", 35_000, 1.3),
    ("no_chunking", sys.maxsize, 1.3),
    ("multiplier_1_0", 30_000, 1.0),
    ("multiplier_1_2", 30_000, 1.2),
    ("multiplier_1_4", 30_000, 1.4),
    ("full_ft_default", 30_000, 1.3),
]


def _generate_synthetic_ft_records(
    n: int = 50,
    seed: int = 42,
) -> tuple[list[Record], dict[str, int]]:
    """Generate synthetic full-text records for mock testing.

    Creates records with realistic text lengths (10K-50K chars) and
    balanced labels. Uses paragraph-like text with sentence boundaries
    to exercise section detection and chunking.

    Args:
        n: Number of records to generate.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (list of Record objects, dict mapping record_id to
        binary gold label).
    """
    rng = random.Random(seed)

    _sections = [
        "Introduction",
        "Methods",
        "Results",
        "Discussion",
        "Conclusion",
    ]

    records: list[Record] = []
    gold_labels: dict[str, int] = {}

    for i in range(n):
        record_id = f"ft_synth_{i:04d}"
        text_len = rng.randint(10_000, 50_000)
        label = 1 if i < n // 2 else 0

        # Build text with section markers and paragraph structure
        paragraphs: list[str] = []
        remaining = text_len
        for section in _sections:
            paragraphs.append(f"\n{section}\n")
            section_len = remaining // (len(_sections) - _sections.index(section))
            while section_len > 0:
                para_len = min(rng.randint(200, 800), section_len)
                words = []
                char_count = 0
                while char_count < para_len:
                    word_len = rng.randint(3, 10)
                    word = "".join(
                        rng.choice("abcdefghijklmnopqrstuvwxyz")
                        for _ in range(word_len)
                    )
                    words.append(word)
                    char_count += word_len + 1
                # Add sentence-ending punctuation periodically
                sentence = " ".join(words)
                sentence = sentence[:para_len] + "."
                paragraphs.append(sentence)
                section_len -= para_len
                remaining -= para_len

        full_text = "\n\n".join(paragraphs)

        records.append(
            Record(
                record_id=record_id,
                title=f"Synthetic FT Study {i}",
                abstract=f"Abstract for synthetic study {i}.",
                full_text=full_text,
            )
        )
        gold_labels[record_id] = label

    logger.info(
        "synthetic_ft_records_generated",
        n_records=len(records),
        n_included=sum(gold_labels.values()),
        avg_text_len=sum(len(r.full_text or "") for r in records) // len(records),
    )

    return records, gold_labels


def _load_ft_csv(
    data_path: Path,
) -> tuple[list[Record], dict[str, int]]:
    """Load full-text records from a CSV file.

    Expects columns: record_id, title, abstract, full_text, label.

    Args:
        data_path: Path to the CSV file.

    Returns:
        Tuple of (list of Record objects, dict mapping record_id to
        binary gold label).

    Raises:
        FileNotFoundError: If the CSV file does not exist.
    """
    if not data_path.exists():
        msg = f"FT ablation data CSV not found: {data_path}"
        raise FileNotFoundError(msg)

    df = pd.read_csv(data_path)

    records: list[Record] = []
    gold_labels: dict[str, int] = {}

    for _, row in df.iterrows():
        record_id = str(row["record_id"])
        title = str(row["title"]).strip() if pd.notna(row["title"]) else ""
        abstract = str(row["abstract"]) if pd.notna(row.get("abstract")) else None
        full_text = str(row["full_text"]) if pd.notna(row.get("full_text")) else None

        if not title:
            logger.warning("skipping_empty_title", record_id=record_id)
            continue

        records.append(
            Record(
                record_id=record_id,
                title=title,
                abstract=abstract,
                full_text=full_text,
            )
        )
        gold_labels[record_id] = int(row["label"])

    logger.info(
        "ft_data_loaded",
        path=str(data_path),
        n_records=len(records),
        n_with_fulltext=sum(1 for r in records if r.full_text),
        n_included=sum(gold_labels.values()),
    )

    return records, gold_labels


async def _run_single_config(
    config_name: str,
    screener: FTScreener,
    records: list[Record],
    gold_labels: dict[str, int],
    seed: int = 42,
    use_mock: bool = False,
) -> dict[str, Any]:
    """Run a single FT ablation configuration and compute metrics.

    Args:
        config_name: Name of the configuration.
        screener: The FTScreener instance for this configuration.
        records: List of Record objects to screen.
        gold_labels: Gold-standard labels for metric computation.
        seed: Random seed for reproducibility.
        use_mock: Whether mock backends are in use.

    Returns:
        Dictionary with config name, record count, metrics, and
        FT-specific statistics.
    """
    logger.info(
        "ft_config_started",
        config=config_name,
        n_records=len(records),
    )

    decisions = await screener.screen_batch(records, _ABLATION_CRITERIA, seed=seed)

    # Convert to binary arrays
    y_true: list[int] = []
    y_pred: list[int] = []
    y_score: list[float] = []

    n_chunked = 0
    total_chunks = 0

    for dec in decisions:
        if dec.record_id not in gold_labels:
            continue

        y_true.append(gold_labels[dec.record_id])
        y_pred.append(
            1 if dec.decision in (Decision.INCLUDE, Decision.HUMAN_REVIEW) else 0
        )
        y_score.append(dec.final_score)

        if dec.chunking_applied:
            n_chunked += 1
            total_chunks += dec.n_chunks or 0

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
        "ft_stats": {
            "n_chunked": n_chunked,
            "chunking_rate": round(n_chunked / len(records), 4) if records else 0.0,
            "avg_n_chunks": round(total_chunks / n_chunked, 2) if n_chunked else 0.0,
        },
    }

    logger.info(
        "ft_config_complete",
        config=config_name,
        sensitivity=metrics.get("sensitivity", {}).get("point"),
        specificity=metrics.get("specificity", {}).get("point"),
        chunking_rate=result["ft_stats"]["chunking_rate"],
    )

    return result


async def run_ft_ablation(
    data_path: Path | None = None,
    seed: int = 42,
    use_mock: bool = True,
    output_dir: Path = Path("validation/results"),
) -> dict[str, Any]:
    """Run the full FT ablation study across all 9 configurations.

    If ``data_path`` is None and ``use_mock`` is True, generates
    synthetic full-text records for offline testing.

    Args:
        data_path: Path to the CSV file, or None for synthetic data.
        seed: Random seed for reproducibility.
        use_mock: If True, use mock LLM backends for offline testing.
        output_dir: Directory to save the results JSON.

    Returns:
        Dictionary with experiment metadata and per-config results.
    """
    if data_path is not None:
        records, gold_labels = _load_ft_csv(data_path)
    else:
        records, gold_labels = _generate_synthetic_ft_records(n=50, seed=seed)

    all_backends = setup_mock_backends() if use_mock else setup_backends()

    logger.info(
        "ft_ablation_started",
        n_records=len(records),
        n_backends=len(all_backends),
        n_configurations=len(_CONFIGURATIONS),
        use_mock=use_mock,
        seed=seed,
    )

    configurations: list[dict[str, Any]] = []

    for config_name, chunk_threshold, ft_penalty_multiplier in _CONFIGURATIONS:
        rule_engine = RuleEngine(ft_penalty_multiplier=ft_penalty_multiplier)

        screener = FTScreener(
            backends=all_backends,
            rule_engine=rule_engine,
            chunk_threshold=chunk_threshold,
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
        "experiment": "exp4b_ft_ablation",
        "n_configurations": len(configurations),
        "configurations": configurations,
    }

    save_results(
        results=result,
        experiment_name="exp4b_ft_ablation",
        output_dir=output_dir,
        seed=seed,
    )

    logger.info(
        "ft_ablation_complete",
        n_configurations=len(configurations),
    )

    return result


def main() -> None:
    """CLI entry point for Exp4b: FT Ablation Study."""
    parser = argparse.ArgumentParser(
        description="Exp4b: FT Ablation Study — Chunking & Penalty Sensitivity"
    )
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="Path to the CSV dataset (record_id, title, abstract, full_text, label)",
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
        run_ft_ablation(
            data_path=Path(args.data) if args.data else None,
            seed=args.seed,
            use_mock=args.mock,
            output_dir=Path(args.output_dir),
        )
    )


if __name__ == "__main__":
    main()
