"""metascreener evaluate — Evaluation and calibration command."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import structlog
import typer

from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import ScreeningDecision
from metascreener.evaluation.calibrator import EvaluationRunner
from metascreener.evaluation.metrics import format_lancet
from metascreener.evaluation.visualizer import (
    plot_calibration_curve,
    plot_roc_curve,
    plot_score_distribution,
    plot_threshold_analysis,
)

logger = structlog.get_logger(__name__)

evaluate_app = typer.Typer(help="Evaluate screening performance and calibrate thresholds.")


def _load_gold_labels(path: Path) -> dict[str, Decision]:
    """Load gold standard labels from CSV file.

    Expected columns: record_id, label (INCLUDE/EXCLUDE).

    Args:
        path: Path to the CSV file.

    Returns:
        Dict mapping record_id to Decision.

    Raises:
        typer.BadParameter: If the file cannot be read or has invalid format.
    """
    if not path.exists():
        raise typer.BadParameter(f"Labels file not found: {path}")

    labels: dict[str, Decision] = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "record_id" not in reader.fieldnames:
            raise typer.BadParameter(
                f"Labels CSV must have 'record_id' and 'label' columns: {path}"
            )
        for row in reader:
            try:
                labels[row["record_id"]] = Decision(row["label"].strip().upper())
            except (ValueError, KeyError) as exc:
                raise typer.BadParameter(
                    f"Invalid label in {path}: {exc}"
                ) from exc
    return labels


def _load_predictions(path: Path) -> list[ScreeningDecision]:
    """Load predictions from JSON file.

    Expected format: list of objects with record_id, decision, final_score,
    tier, ensemble_confidence.

    Args:
        path: Path to the JSON file.

    Returns:
        List of ScreeningDecision objects.

    Raises:
        typer.BadParameter: If the file cannot be read.
    """
    if not path.exists():
        raise typer.BadParameter(f"Predictions file not found: {path}")

    data = json.loads(path.read_text())
    decisions: list[ScreeningDecision] = []
    for item in data:
        decisions.append(
            ScreeningDecision(
                record_id=item["record_id"],
                stage=ScreeningStage(item.get("stage", "ta")),
                decision=Decision(item["decision"]),
                tier=Tier(item.get("tier", 1)),
                final_score=float(item.get("final_score", 0.5)),
                ensemble_confidence=float(item.get("ensemble_confidence", 0.5)),
            )
        )
    return decisions


@evaluate_app.callback(invoke_without_command=True)
def evaluate(
    ctx: typer.Context,  # noqa: ARG001
    labels: Path = typer.Option(  # noqa: B008
        ..., "--labels", "-l", help="Gold standard labels CSV (record_id, label)"
    ),
    predictions: Path | None = typer.Option(  # noqa: B008
        None, "--predictions", "-p", help="Predictions JSON file"
    ),
    visualize: bool = typer.Option(  # noqa: B008
        False, "--visualize", help="Generate HTML visualization charts"
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("results"), "--output", "-o", help="Output directory"
    ),
    seed: int = typer.Option(42, "--seed", "-s", help="Bootstrap random seed"),  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate inputs only"),  # noqa: B008
) -> None:
    """Evaluate screening performance and compute metrics."""
    # Validate inputs
    gold_labels = _load_gold_labels(labels)
    typer.echo(f"Loaded {len(gold_labels)} gold labels from {labels}")

    if predictions is None:
        raise typer.BadParameter("--predictions is required")

    preds = _load_predictions(predictions)
    typer.echo(f"Loaded {len(preds)} predictions from {predictions}")

    if dry_run:
        typer.echo("Dry run: inputs validated successfully.")
        return

    # Run evaluation
    runner = EvaluationRunner()
    report = runner.evaluate_screening(preds, gold_labels, seed=seed)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write report JSON
    report_path = output_dir / "evaluation_report.json"
    report_path.write_text(report.model_dump_json(indent=2))
    typer.echo(f"Report saved to {report_path}")

    # Display summary
    m = report.metrics
    typer.echo("\n--- Screening Metrics ---")
    typer.echo(f"  Sensitivity: {m.sensitivity:.4f}")
    typer.echo(f"  Specificity: {m.specificity:.4f}")
    typer.echo(f"  Precision:   {m.precision:.4f}")
    typer.echo(f"  F1:          {m.f1:.4f}")
    typer.echo(f"  WSS@95:      {m.wss_at_95:.4f}")
    typer.echo(f"  AUROC:       {report.auroc.auroc:.4f}")
    typer.echo(f"  ECE:         {report.calibration.ece:.4f}")
    typer.echo(f"  Brier:       {report.calibration.brier:.4f}")
    typer.echo(f"  N:           {m.n_total}")

    # Display bootstrap CIs in Lancet format
    if report.bootstrap_cis:
        typer.echo("\n--- Bootstrap 95% CIs (Lancet format) ---")
        for name, ci in report.bootstrap_cis.items():
            typer.echo(f"  {name}: {format_lancet(ci.point, ci.ci_lower, ci.ci_upper)}")

    # Generate visualizations
    if visualize:
        typer.echo("\nGenerating visualizations...")

        roc_fig = plot_roc_curve(report.auroc)
        roc_fig.write_html(str(output_dir / "roc_curve.html"))

        cal_fig = plot_calibration_curve(report.calibration)
        cal_fig.write_html(str(output_dir / "calibration_curve.html"))

        scores = [
            d.final_score for d in preds if d.record_id in gold_labels
        ]
        int_labels = [
            1 if gold_labels[d.record_id] == Decision.INCLUDE else 0
            for d in preds
            if d.record_id in gold_labels
        ]

        dist_fig = plot_score_distribution(scores, int_labels)
        dist_fig.write_html(str(output_dir / "score_distribution.html"))

        thresh_fig = plot_threshold_analysis(scores, int_labels)
        thresh_fig.write_html(str(output_dir / "threshold_analysis.html"))

        typer.echo(f"Visualizations saved to {output_dir}/")
