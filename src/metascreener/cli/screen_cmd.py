"""metascreener screen — Literature screening command."""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import typer

from metascreener.config import MetaScreenerConfig, load_model_config

screen_app = typer.Typer(help="Screen literature (title/abstract or full-text).")

_DEFAULT_CONFIG = Path(__file__).parent.parent.parent.parent / "configs" / "models.yaml"


class ScreenStage(StrEnum):
    TA = "ta"
    FT = "ft"
    BOTH = "both"


@screen_app.callback(invoke_without_command=True)
def screen(
    ctx: typer.Context,  # noqa: ARG001
    input: Path = typer.Option(..., "--input", "-i", help="Input file (RIS/BibTeX/CSV)"),  # noqa: A002, B008
    stage: ScreenStage = typer.Option(ScreenStage.TA, "--stage", "-s", help="Screening stage"),  # noqa: B008
    criteria: Path | None = typer.Option(None, "--criteria", "-c", help="criteria.yaml"),  # noqa: B008
    output_dir: Path = typer.Option(Path("results"), "--output", "-o"),  # noqa: B008
    config: Path | None = typer.Option(None, "--config", help="models.yaml config file"),  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate inputs without running"),  # noqa: B008
) -> None:
    """Screen literature using the Hierarchical Consensus Network (HCN)."""
    cfg = _load_config(config)

    if dry_run:
        _validate_inputs(input, criteria, output_dir, stage, cfg)
        return

    typer.echo(f"[screen] Stage: {stage.value} | Input: {input}")
    typer.echo(f"[screen] Models: {', '.join(cfg.models.keys())}")
    typer.echo(f"[screen] Thresholds: tau_high={cfg.thresholds.tau_high}, "
               f"tau_mid={cfg.thresholds.tau_mid}, tau_low={cfg.thresholds.tau_low}")
    typer.echo(
        "[screen] Full screening requires data readers (RIS/BibTeX/CSV) "
        "— coming in a future phase."
    )


def _load_config(config_path: Path | None) -> MetaScreenerConfig:
    """Load MetaScreener config from file or defaults.

    Args:
        config_path: Optional path to config file.

    Returns:
        MetaScreenerConfig instance.
    """
    if config_path is not None:
        return load_model_config(config_path)
    if _DEFAULT_CONFIG.exists():
        return load_model_config(_DEFAULT_CONFIG)
    return MetaScreenerConfig()


def _validate_inputs(
    input_path: Path,
    criteria_path: Path | None,
    output_dir: Path,
    stage: ScreenStage,
    cfg: MetaScreenerConfig,
) -> None:
    """Validate inputs for dry-run mode.

    Args:
        input_path: Path to input file.
        criteria_path: Optional path to criteria file.
        output_dir: Output directory.
        stage: Screening stage.
        cfg: Loaded configuration.
    """
    errors: list[str] = []

    if not input_path.exists():
        errors.append(f"Input file not found: {input_path}")

    if criteria_path is not None and not criteria_path.exists():
        errors.append(f"Criteria file not found: {criteria_path}")

    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    model_names = ", ".join(cfg.models.keys()) if cfg.models else "(default)"
    typer.echo("[dry-run] Validation passed:")
    typer.echo(f"  Input: {input_path}")
    typer.echo(f"  Stage: {stage.value}")
    typer.echo(f"  Output: {output_dir}")
    if criteria_path:
        typer.echo(f"  Criteria: {criteria_path}")
    typer.echo(f"  Models: {len(cfg.models)} ({model_names})")
    typer.echo(f"  Sensitivity target: {cfg.thresholds.target_sensitivity}")
