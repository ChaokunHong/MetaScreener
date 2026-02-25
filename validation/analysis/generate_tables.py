"""Paper table generator for Lancet Digital Health submission.

Produces 5 markdown tables from validation experiment results using
Lancet-format decimal notation (middle dot U+00B7) and CI ranges
(en dash U+2013). Tables map directly to the paper's Results section.

Table 1: Model Registry (from configs/models.yaml)
Table 2: Cohen 2006 Benchmark Results (Exp2)
Table 3: ASReview Benchmark Results (Exp3)
Table 4: Ablation Study (Exp4)
Table 5: Cost and Time Analysis (Exp7)

Usage:
    python -m validation.analysis.generate_tables \\
        --results-dir validation/results \\
        --output-dir paper/tables
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import structlog

from metascreener.config import load_model_config
from metascreener.evaluation.metrics import format_lancet

logger = structlog.get_logger(__name__)

# Default config path relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "configs" / "models.yaml"

# Metric columns displayed in benchmark tables
_BENCHMARK_METRICS = [
    "sensitivity",
    "specificity",
    "f1",
    "wss_at_95",
    "precision",
    "automation_rate",
]

# Human-readable metric labels for table headers
_METRIC_LABELS = {
    "sensitivity": "Sensitivity",
    "specificity": "Specificity",
    "f1": "F1",
    "wss_at_95": "WSS@95",
    "precision": "Precision",
    "automation_rate": "Automation Rate",
}

# Ablation metrics (subset)
_ABLATION_METRICS = ["sensitivity", "specificity", "f1", "wss_at_95"]


def _load_results(results_dir: Path, experiment_name: str) -> dict[str, Any] | None:
    """Load experiment results JSON from the results directory.

    Args:
        results_dir: Path to the directory containing result JSON files.
        experiment_name: Experiment filename without extension
            (e.g., "exp2_cohen_benchmark").

    Returns:
        Parsed JSON dict, or None if the file does not exist.
    """
    path = results_dir / f"{experiment_name}.json"
    if not path.exists():
        logger.warning("results_file_not_found", path=str(path))
        return None
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _fmt(m: dict[str, float]) -> str:
    """Format a metric dict as a Lancet-style string.

    Args:
        m: Dict with "point", "ci_lower", "ci_upper" keys.

    Returns:
        Lancet-formatted string, e.g. "0\\u00b795 (0\\u00b792\\u20130\\u00b797)".
    """
    return format_lancet(m["point"], m["ci_lower"], m["ci_upper"])


def generate_table1_models(
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> str:
    """Generate Table 1: Model Registry.

    Lists all LLM models from the configuration file with their
    versions, providers, and licenses.

    Args:
        config_path: Path to the models.yaml configuration file.

    Returns:
        Markdown table string.
    """
    config = load_model_config(config_path)

    lines: list[str] = []
    lines.append("**Table 1.** Model registry for MetaScreener 2.0 HCN ensemble.")
    lines.append("")
    lines.append("| Model | Version | Provider | Model ID | License |")
    lines.append("|-------|---------|----------|----------|---------|")

    for _key, entry in config.models.items():
        lines.append(
            f"| {entry.name} | {entry.version} | {entry.provider} "
            f"| {entry.model_id} | {entry.license_} |"
        )

    lines.append("")
    return "\n".join(lines)


def _generate_benchmark_table(
    data: dict[str, Any],
    table_num: int,
    caption: str,
    items_key: str,
    item_name_key: str,
) -> str:
    """Generate a benchmark results table (shared logic for Table 2 and 3).

    Args:
        data: Parsed experiment results dict.
        table_num: Table number (2 or 3).
        caption: Table caption text.
        items_key: Key for the per-item list ("per_topic" or "per_dataset").
        item_name_key: Key for the item name ("topic" or "dataset").

    Returns:
        Markdown table string.
    """
    metric_headers = " | ".join(
        _METRIC_LABELS.get(m, m) for m in _BENCHMARK_METRICS
    )

    lines: list[str] = []
    lines.append(f"**Table {table_num}.** {caption}")
    lines.append("")
    lines.append(f"| {item_name_key.capitalize()} | N | Included | {metric_headers} |")

    # Separator line
    sep_parts = ["---", "---", "---"] + ["---"] * len(_BENCHMARK_METRICS)
    lines.append("| " + " | ".join(sep_parts) + " |")

    # Per-item rows
    items = data.get(items_key, [])
    for item in items:
        name = item.get(item_name_key, "Unknown")
        n_records = item.get("n_records", "")
        n_included = item.get("n_included", "")
        metrics = item.get("metrics", {})

        metric_values = " | ".join(
            _fmt(metrics[m]) if m in metrics else "\u2014" for m in _BENCHMARK_METRICS
        )

        lines.append(f"| {name} | {n_records} | {n_included} | {metric_values} |")

    # Macro average row
    aggregate = data.get("macro_average") or data.get("aggregate", {})
    if aggregate:
        agg_values = " | ".join(
            _fmt(aggregate[m]) if m in aggregate else "\u2014"
            for m in _BENCHMARK_METRICS
        )
        lines.append(f"| **Macro Average** | \u2014 | \u2014 | {agg_values} |")

    lines.append("")
    lines.append(
        "*Values are point estimates with 95% bootstrap confidence intervals.*"
    )
    lines.append("")
    return "\n".join(lines)


def generate_table2_cohen(results_dir: Path) -> str:
    """Generate Table 2: Cohen 2006 Benchmark Results.

    Args:
        results_dir: Path to the directory containing experiment results.

    Returns:
        Markdown table string, or a fallback message if results are missing.
    """
    data = _load_results(results_dir, "exp2_cohen_benchmark")
    if data is None:
        return (
            "**Table 2.** No results available for Cohen 2006 benchmark. "
            "Run `python -m validation.experiments.exp2_cohen_benchmark` first."
        )

    return _generate_benchmark_table(
        data=data,
        table_num=2,
        caption=(
            "Screening performance on the Cohen 2006 benchmark "
            f"({data.get('n_topics', '?')} systematic review topics)."
        ),
        items_key="per_topic",
        item_name_key="topic",
    )


def generate_table3_asreview(results_dir: Path) -> str:
    """Generate Table 3: ASReview Benchmark Results.

    Args:
        results_dir: Path to the directory containing experiment results.

    Returns:
        Markdown table string, or a fallback message if results are missing.
    """
    data = _load_results(results_dir, "exp3_asreview_benchmark")
    if data is None:
        return (
            "**Table 3.** No results available for ASReview benchmark. "
            "Run `python -m validation.experiments.exp3_asreview_benchmark` first."
        )

    return _generate_benchmark_table(
        data=data,
        table_num=3,
        caption=(
            "Screening performance on the ASReview benchmark "
            f"({data.get('n_datasets', '?')} datasets)."
        ),
        items_key="per_dataset",
        item_name_key="dataset",
    )


def generate_table4_ablation(results_dir: Path) -> str:
    """Generate Table 4: Ablation Study.

    Compares different HCN configurations (single model, ensemble
    without rules, full HCN) to quantify component contributions.

    Args:
        results_dir: Path to the directory containing experiment results.

    Returns:
        Markdown table string, or a fallback message if results are missing.
    """
    data = _load_results(results_dir, "exp4_ablation_study")
    if data is None:
        return (
            "**Table 4.** No results available for ablation study. "
            "Run `python -m validation.experiments.exp4_ablation_study` first."
        )

    metric_headers = " | ".join(
        _METRIC_LABELS.get(m, m) for m in _ABLATION_METRICS
    )

    lines: list[str] = []
    lines.append(
        "**Table 4.** Ablation study: contribution of HCN components "
        "to screening performance."
    )
    lines.append("")
    lines.append(f"| Configuration | {metric_headers} |")

    sep_parts = ["---"] + ["---"] * len(_ABLATION_METRICS)
    lines.append("| " + " | ".join(sep_parts) + " |")

    configurations = data.get("configurations", [])
    for config in configurations:
        name = config.get("name", "Unknown")
        metrics = config.get("metrics", {})

        metric_values = " | ".join(
            _fmt(metrics[m]) if m in metrics else "\u2014"
            for m in _ABLATION_METRICS
        )
        lines.append(f"| {name} | {metric_values} |")

    lines.append("")
    lines.append(
        "*Values are point estimates with 95% bootstrap confidence intervals.*"
    )
    lines.append("")
    return "\n".join(lines)


def generate_table5_cost(results_dir: Path) -> str:
    """Generate Table 5: Cost and Time Analysis.

    Summarises per-record processing time and API cost estimates.

    Args:
        results_dir: Path to the directory containing experiment results.

    Returns:
        Markdown table string, or a fallback message if results are missing.
    """
    data = _load_results(results_dir, "exp7_cost_time")
    if data is None:
        return (
            "**Table 5.** No results available for cost/time analysis. "
            "Run `python -m validation.experiments.exp7_cost_time` first."
        )

    summary = data.get("summary", {})

    lines: list[str] = []
    lines.append(
        "**Table 5.** Processing time and API cost analysis."
    )
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total records processed | {summary.get('total_records', '?')} |")
    lines.append(f"| Number of LLM models | {summary.get('n_models', '?')} |")
    lines.append(
        f"| Mean time per record (s) | {summary.get('mean_time_s', '?'):.2f} |"
    )
    lines.append(
        f"| Median time per record (s) | {summary.get('median_time_s', '?'):.2f} |"
    )
    lines.append(
        f"| Mean cost per record (USD) | ${summary.get('mean_cost_usd', '?'):.4f} |"
    )
    lines.append(
        f"| Estimated cost per 1000 records (USD) "
        f"| ${summary.get('est_cost_per_1000', '?'):.2f} |"
    )
    lines.append("")
    return "\n".join(lines)


def generate_all_tables(
    results_dir: Path,
    output_dir: Path,
) -> None:
    """Generate all 5 paper tables and write to a single markdown file.

    Args:
        results_dir: Path to the directory containing experiment result
            JSON files.
        output_dir: Path to the directory where paper_tables.md will
            be written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    sections = [
        generate_table1_models(),
        generate_table2_cohen(results_dir),
        generate_table3_asreview(results_dir),
        generate_table4_ablation(results_dir),
        generate_table5_cost(results_dir),
    ]

    combined = "\n---\n\n".join(sections)
    header = (
        "# MetaScreener 2.0 \u2014 Paper Tables\n\n"
        "*Generated for Lancet Digital Health submission.*\n\n"
    )

    output_path = output_dir / "paper_tables.md"
    output_path.write_text(header + combined)

    logger.info(
        "paper_tables_generated",
        output_path=str(output_path),
        n_tables=5,
    )


def main() -> None:
    """CLI entry point for table generation."""
    parser = argparse.ArgumentParser(
        description="Generate Lancet-format paper tables from experiment results.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=_PROJECT_ROOT / "validation" / "results",
        help="Directory containing experiment result JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_PROJECT_ROOT / "paper" / "tables",
        help="Output directory for paper_tables.md.",
    )

    args = parser.parse_args()
    generate_all_tables(args.results_dir, args.output_dir)


if __name__ == "__main__":
    main()
