"""metascreener evaluate — Evaluation and calibration command."""
from pathlib import Path

import typer

evaluate_app = typer.Typer(help="Evaluate screening performance and calibrate thresholds.")


@evaluate_app.callback(invoke_without_command=True)
def evaluate(
    ctx: typer.Context,  # noqa: ARG001
    labels: Path = typer.Option(..., "--labels", "-l", help="Gold standard labels (RIS/CSV)"),  # noqa: B008
    predictions: Path | None = typer.Option(None, "--predictions", "-p"),  # noqa: B008
    visualize: bool = typer.Option(False, "--visualize", help="Open Streamlit charts"),  # noqa: B008
    output_dir: Path = typer.Option(Path("results"), "--output", "-o"),  # noqa: B008
) -> None:
    """Evaluate screening performance and compute metrics."""
    typer.echo("[evaluate] Not yet implemented — coming in Phase 3.")
