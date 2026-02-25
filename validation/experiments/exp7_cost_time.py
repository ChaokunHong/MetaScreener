"""Exp7: Cost and Time Analysis.

Measures wall-clock time and estimates API cost per record for the
full HCN screening pipeline. Provides per-record breakdowns of
timing, token usage, and estimated cost at OpenRouter rates.

Paper Section: Results 3.6

Usage:
    python validation/experiments/exp7_cost_time.py --data path/to/data.csv --seed 42
    python validation/experiments/exp7_cost_time.py --data path/to/data.csv --mock
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from metascreener.core.models import PICOCriteria, Record
from metascreener.module1_screening.ta_screener import TAScreener
from validation.common import (
    save_results,
    setup_backends,
    setup_mock_backends,
)

logger = structlog.get_logger(__name__)

# Approximate OpenRouter pricing (USD per 1M tokens) as of 2026-02.
_PRICING: dict[str, dict[str, float]] = {
    "qwen3": {"input": 0.20, "output": 0.60},
    "deepseek": {"input": 0.30, "output": 0.88},
    "llama": {"input": 0.15, "output": 0.60},
    "mistral": {"input": 0.10, "output": 0.30},
    # Mock variants (same pricing as real counterparts)
    "mock-qwen3": {"input": 0.20, "output": 0.60},
    "mock-deepseek": {"input": 0.30, "output": 0.88},
    "mock-llama4": {"input": 0.15, "output": 0.60},
    "mock-mistral": {"input": 0.10, "output": 0.30},
}

# Default output tokens per model per record (screening response ~200 tokens).
_OUTPUT_TOKENS_PER_MODEL = 200

# Generic PICO criteria for cost/time benchmarking.
_COST_CRITERIA = PICOCriteria(
    population_include=["humans"],
    intervention_include=["any intervention"],
    outcome_primary=["clinical outcomes"],
)


def _estimate_input_tokens(title: str, abstract: str | None) -> int:
    """Estimate the number of input tokens for a single model call.

    Uses the rough heuristic of 1 token per 4 characters, with a
    minimum of 100 tokens to account for the prompt template overhead.

    Args:
        title: Paper title.
        abstract: Paper abstract (may be None).

    Returns:
        Estimated input token count for one model.
    """
    text = title + (abstract or "")
    return max(len(text) // 4, 100)


def _estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a single model call.

    Looks up the model in the pricing table. If the model ID is not
    found, falls back to the most expensive rate to avoid underestimates.

    Args:
        model_id: Identifier of the model (e.g., "mock-qwen3").
        input_tokens: Estimated input token count.
        output_tokens: Estimated output token count.

    Returns:
        Estimated cost in USD.
    """
    # Try exact match first, then prefix match
    rates = _PRICING.get(model_id)
    if rates is None:
        for key in _PRICING:
            if key in model_id or model_id in key:
                rates = _PRICING[key]
                break
    if rates is None:
        # Fallback: use highest rates to avoid underestimation
        rates = {"input": 0.30, "output": 0.88}

    cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    return cost


def _load_cost_csv(
    data_path: Path,
    max_records: int | None = None,
) -> list[Record]:
    """Load a CSV file and build Record objects.

    Args:
        data_path: Path to the CSV file with columns record_id, title,
            abstract (and optionally label).
        max_records: If set, limit to the first N rows.

    Returns:
        List of Record objects.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
    """
    if not data_path.exists():
        msg = f"Cost analysis data CSV not found: {data_path}"
        raise FileNotFoundError(msg)

    df = pd.read_csv(data_path)

    if max_records is not None:
        df = df.head(max_records)

    records: list[Record] = []

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

    logger.info(
        "cost_data_loaded",
        path=str(data_path),
        n_records=len(records),
    )

    return records


async def run_cost_analysis(
    data_path: Path,
    seed: int = 42,
    use_mock: bool = True,
    max_records: int | None = None,
    output_dir: Path = Path("validation/results"),
) -> dict[str, Any]:
    """Run cost and time analysis on a dataset.

    Screens each record individually, measuring wall-clock time and
    estimating token usage and API cost per record. Produces both
    per-record statistics and an aggregate summary.

    Args:
        data_path: Path to the CSV file with columns record_id, title,
            abstract (and optionally label).
        seed: Random seed for reproducibility.
        use_mock: If True, use mock LLM backends for offline testing.
        max_records: If set, limit to the first N records.
        output_dir: Directory to save the results JSON.

    Returns:
        Dictionary with keys: ``experiment``, ``per_record_stats``
        (list of per-record dicts), ``summary`` (aggregate stats).

    Raises:
        FileNotFoundError: If the data CSV does not exist.
    """
    records = _load_cost_csv(data_path, max_records=max_records)

    # Set up backends
    backends = setup_mock_backends() if use_mock else setup_backends()
    n_models = len(backends)
    model_ids = [b.model_id for b in backends]
    screener = TAScreener(backends=backends)

    logger.info(
        "cost_analysis_started",
        n_records=len(records),
        n_models=n_models,
        model_ids=model_ids,
        use_mock=use_mock,
        seed=seed,
    )

    per_record_stats: list[dict[str, Any]] = []

    for record in records:
        # Estimate tokens for this record
        input_tokens_per_model = _estimate_input_tokens(record.title, record.abstract)
        total_input_tokens = input_tokens_per_model * n_models
        total_output_tokens = _OUTPUT_TOKENS_PER_MODEL * n_models

        # Estimate cost across all models
        record_cost = 0.0
        for mid in model_ids:
            record_cost += _estimate_cost(
                mid, input_tokens_per_model, _OUTPUT_TOKENS_PER_MODEL
            )

        # Time the screening call
        t_start = time.perf_counter()
        decision = await screener.screen_single(record, _COST_CRITERIA, seed=seed)
        t_end = time.perf_counter()
        elapsed_s = t_end - t_start

        per_record_stats.append({
            "record_id": record.record_id,
            "time_s": round(elapsed_s, 6),
            "est_input_tokens": total_input_tokens,
            "est_output_tokens": total_output_tokens,
            "est_cost_usd": round(record_cost, 8),
            "decision": decision.decision.value,
            "tier": decision.tier.value,
        })

        logger.debug(
            "record_screened",
            record_id=record.record_id,
            time_s=round(elapsed_s, 4),
            est_cost_usd=round(record_cost, 8),
            decision=decision.decision.value,
        )

    # Compute summary statistics
    times = [s["time_s"] for s in per_record_stats]
    costs = [s["est_cost_usd"] for s in per_record_stats]
    total_records = len(per_record_stats)

    summary: dict[str, Any] = {
        "total_records": total_records,
        "total_time_s": round(sum(times), 4),
        "mean_time_s": round(statistics.mean(times), 6) if times else 0.0,
        "median_time_s": round(statistics.median(times), 6) if times else 0.0,
        "mean_cost_usd": round(statistics.mean(costs), 8) if costs else 0.0,
        "est_cost_per_1000": round(statistics.mean(costs) * 1000, 6) if costs else 0.0,
        "n_models": n_models,
        "model_ids": model_ids,
    }

    result: dict[str, Any] = {
        "experiment": "exp7_cost_time",
        "per_record_stats": per_record_stats,
        "summary": summary,
    }

    # Save results
    save_results(
        results=result,
        experiment_name="exp7_cost_time",
        output_dir=output_dir,
        seed=seed,
    )

    logger.info(
        "cost_analysis_complete",
        total_records=total_records,
        total_time_s=summary["total_time_s"],
        mean_time_s=summary["mean_time_s"],
        mean_cost_usd=summary["mean_cost_usd"],
        est_cost_per_1000=summary["est_cost_per_1000"],
    )

    return result


def main() -> None:
    """CLI entry point for Exp7: Cost and Time Analysis."""
    parser = argparse.ArgumentParser(
        description="Exp7: Cost and Time Analysis — per-record timing and cost estimation"
    )
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path to the CSV dataset (record_id, title, abstract)",
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
        help="Limit to the first N records for quick testing",
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
        run_cost_analysis(
            data_path=Path(args.data),
            seed=args.seed,
            use_mock=args.mock,
            max_records=args.max_records,
            output_dir=Path(args.output_dir),
        )
    )


if __name__ == "__main__":
    main()
