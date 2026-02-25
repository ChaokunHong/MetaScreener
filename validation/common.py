"""Shared utilities for MetaScreener validation experiments.

Provides helper functions for loading gold-standard labels, saving
experiment results, setting up LLM backends (mock and real), and
computing screening metrics with bootstrap confidence intervals.

All experiments should import from this module rather than
reimplementing common logic.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from metascreener.core.enums import Decision
from metascreener.llm.base import LLMBackend

logger = structlog.get_logger(__name__)

# Label column names recognized in gold-standard CSV files
_LABEL_COLUMNS = ("label", "included", "relevant", "label_included", "is_relevant")

# MetaScreener version for result metadata
_VERSION = "2.0.0a1"


def load_gold_labels(path: Path) -> dict[str, Decision]:
    """Load gold-standard labels from a CSV file.

    Expects columns: ``record_id`` (or any column containing "id") and
    one of ``label``, ``included``, ``relevant``, ``label_included``, or
    ``is_relevant``. Values must be 1 (INCLUDE) or 0 (EXCLUDE).

    Args:
        path: Path to the CSV file with gold-standard labels.

    Returns:
        Mapping from record ID to Decision (INCLUDE or EXCLUDE).

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If no recognized label column is found.
    """
    if not path.exists():
        msg = f"Gold-standard label file not found: {path}"
        raise FileNotFoundError(msg)

    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    # Find record ID column
    id_col: str | None = None
    if "record_id" in df.columns:
        id_col = "record_id"
    else:
        for col in df.columns:
            if "id" in col:
                id_col = col
                break

    if id_col is None:
        msg = "No record ID column found (expected 'record_id' or column containing 'id')"
        raise ValueError(msg)

    # Find label column
    label_col: str | None = None
    for candidate in _LABEL_COLUMNS:
        if candidate in df.columns:
            label_col = candidate
            break

    if label_col is None:
        msg = (
            f"No recognized label column found. "
            f"Expected one of: {', '.join(_LABEL_COLUMNS)}"
        )
        raise ValueError(msg)

    logger.info(
        "gold_labels_loaded",
        path=str(path),
        id_col=id_col,
        label_col=label_col,
        n_records=len(df),
    )

    labels: dict[str, Decision] = {}
    for _, row in df.iterrows():
        record_id = str(row[id_col])
        value = int(row[label_col])
        labels[record_id] = Decision.INCLUDE if value == 1 else Decision.EXCLUDE

    return labels


def save_results(
    results: dict[str, Any],
    experiment_name: str,
    output_dir: Path,
    seed: int = 42,
) -> Path:
    """Save experiment results as JSON with metadata.

    The output file includes a ``_metadata`` key with timestamp, seed,
    version, and experiment name for reproducibility.

    Args:
        results: Experiment results dictionary.
        experiment_name: Name of the experiment (used in filename).
        output_dir: Directory to write the JSON file to.
        seed: Random seed used in the experiment.

    Returns:
        Path to the saved JSON file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).isoformat()
    filename = f"{experiment_name}_{timestamp.replace(':', '-').split('.')[0]}.json"
    output_path = output_dir / filename

    output_data: dict[str, Any] = {
        **results,
        "_metadata": {
            "experiment_name": experiment_name,
            "timestamp": timestamp,
            "seed": seed,
            "version": _VERSION,
        },
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    logger.info(
        "results_saved",
        experiment_name=experiment_name,
        path=str(output_path),
        seed=seed,
    )

    return output_path


def setup_mock_backends() -> list[LLMBackend]:
    """Create 4 mock LLM backends with distinct model IDs.

    Each backend returns INCLUDE with confidence 0.85 and score 0.80.
    Model IDs: mock-qwen3, mock-deepseek, mock-llama4, mock-mistral.

    Returns:
        List of 4 MockLLMAdapter instances.
    """
    from metascreener.llm.adapters.mock import MockLLMAdapter

    mock_response = {
        "decision": "INCLUDE",
        "confidence": 0.85,
        "score": 0.80,
        "pico_assessment": {},
        "rationale": "Mock response for validation experiments.",
    }

    model_ids = ["mock-qwen3", "mock-deepseek", "mock-llama4", "mock-mistral"]

    backends: list[LLMBackend] = [
        MockLLMAdapter(model_id=mid, response_json=mock_response)
        for mid in model_ids
    ]

    logger.info("mock_backends_created", count=len(backends))
    return backends


def setup_backends(api_key: str | None = None) -> list[LLMBackend]:
    """Create real OpenRouter LLM backends from config.

    Reads model definitions from ``configs/models.yaml`` and creates
    one OpenRouterAdapter per model. The API key is read from the
    ``OPENROUTER_API_KEY`` environment variable if not provided.

    Args:
        api_key: OpenRouter API key. Falls back to env var if None.

    Returns:
        List of OpenRouterAdapter instances, one per configured model.

    Raises:
        ValueError: If no API key is available.
    """
    from metascreener.config import load_model_config
    from metascreener.llm.adapters.openrouter import OpenRouterAdapter

    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        msg = (
            "No OpenRouter API key provided. "
            "Set OPENROUTER_API_KEY environment variable or pass api_key argument."
        )
        raise ValueError(msg)

    config_path = Path(__file__).parent.parent / "configs" / "models.yaml"
    config = load_model_config(config_path)

    backends: list[LLMBackend] = []
    for name, entry in config.models.items():
        adapter = OpenRouterAdapter(
            model_id=name,
            openrouter_model_name=entry.model_id,
            api_key=key,
            model_version=entry.version,
            timeout_s=config.inference.timeout_s,
            max_retries=config.inference.max_retries,
        )
        backends.append(adapter)

    logger.info(
        "backends_created",
        count=len(backends),
        models=[b.model_id for b in backends],
    )

    return backends


def compute_metrics_with_ci(
    y_true: list[int],
    y_pred: list[int],
    y_score: list[float],
    seed: int = 42,
    n_bootstrap: int = 1000,
) -> dict[str, dict[str, float]]:
    """Compute screening metrics with bootstrap 95% confidence intervals.

    Converts binary predictions (0/1) to Decision enums, computes
    screening metrics via ``compute_screening_metrics()``, and wraps
    each metric in a bootstrap CI via ``bootstrap_ci()``.

    Args:
        y_true: Binary ground-truth labels (1 = INCLUDE, 0 = EXCLUDE).
        y_pred: Binary predicted labels (1 = INCLUDE, 0 = EXCLUDE).
        y_score: Predicted relevance scores (not used for metrics but
            passed through for future AUROC CI computation).
        seed: Random seed for reproducibility.
        n_bootstrap: Number of bootstrap iterations.

    Returns:
        Dictionary mapping metric names to dicts with ``point``,
        ``ci_lower``, and ``ci_upper`` keys. Metrics included:
        sensitivity, specificity, precision, f1, wss_at_95,
        automation_rate.
    """
    from metascreener.evaluation.metrics import (
        bootstrap_ci,
        compute_screening_metrics,
    )

    # Convert binary labels to Decision enums
    decisions = [Decision.INCLUDE if p == 1 else Decision.EXCLUDE for p in y_pred]
    labels = [Decision.INCLUDE if t == 1 else Decision.EXCLUDE for t in y_true]

    # Point estimate via the existing API
    base_metrics = compute_screening_metrics(decisions, labels)

    # Define metric extraction functions for bootstrap_ci
    metric_names = [
        "sensitivity",
        "specificity",
        "precision",
        "f1",
        "wss_at_95",
        "automation_rate",
    ]

    def _make_metric_fn(
        attr: str,
    ) -> Callable[[tuple[Any, ...]], float]:
        """Create a bootstrap-compatible function for a given metric attribute.

        Args:
            attr: Name of the ScreeningMetrics attribute to extract.

        Returns:
            A callable that takes a tuple of (y_pred_list, y_true_list)
            and returns the metric value as a float.
        """

        def metric_fn(data: tuple[Any, ...]) -> float:
            preds = [Decision.INCLUDE if p == 1 else Decision.EXCLUDE for p in data[0]]
            trues = [Decision.INCLUDE if t == 1 else Decision.EXCLUDE for t in data[1]]
            m = compute_screening_metrics(preds, trues)
            return float(getattr(m, attr))

        return metric_fn

    result: dict[str, dict[str, float]] = {}
    data_tuple = (y_pred, y_true)

    for attr in metric_names:
        fn = _make_metric_fn(attr)
        ci = bootstrap_ci(fn, data_tuple, n_iter=n_bootstrap, seed=seed)
        result[attr] = {
            "point": getattr(base_metrics, attr),
            "ci_lower": ci.ci_lower,
            "ci_upper": ci.ci_upper,
        }

    logger.info(
        "metrics_with_ci_computed",
        n_records=len(y_true),
        n_bootstrap=n_bootstrap,
        seed=seed,
    )

    return result
