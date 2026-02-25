"""metascreener screen — Literature screening command."""
from __future__ import annotations

import asyncio
import collections.abc
import json
from enum import StrEnum
from pathlib import Path

import structlog
import typer

from metascreener.config import MetaScreenerConfig, load_model_config

logger = structlog.get_logger(__name__)

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
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducibility"),  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate inputs without running"),  # noqa: B008
) -> None:
    """Screen literature using the Hierarchical Consensus Network (HCN)."""
    cfg = _load_config(config)

    if dry_run:
        _validate_inputs(input, criteria, output_dir, stage, cfg)
        return

    from metascreener.io.readers import read_records  # noqa: PLC0415
    from metascreener.llm.factory import create_backends  # noqa: PLC0415
    from metascreener.module1_screening.ta_screener import TAScreener  # noqa: PLC0415

    # Validate criteria first (before API key check)
    if not criteria:
        typer.echo(
            "Error: --criteria is required for screening. "
            "Run 'metascreener init' first to generate criteria.yaml.",
            err=True,
        )
        raise typer.Exit(code=1)
    if not criteria.exists():
        typer.echo(f"Error: Criteria file not found: {criteria}", err=True)
        raise typer.Exit(code=1)

    records = read_records(input)
    typer.echo(f"[screen] Loaded {len(records)} records from {input}")
    typer.echo(f"[screen] Stage: {stage.value}")
    typer.echo(f"[screen] Models: {', '.join(cfg.models.keys())}")

    backends = create_backends(cfg)

    from metascreener.criteria.schema import CriteriaSchema  # noqa: PLC0415

    review_criteria = CriteriaSchema.load(criteria)
    typer.echo(f"[screen] Criteria: {review_criteria.framework.value}")

    screener = TAScreener(backends=backends, timeout_s=cfg.inference.timeout_s)
    typer.echo(f"[screen] Screening {len(records)} records with seed={seed}...")

    decisions = asyncio.run(
        screener.screen_batch(records, review_criteria, seed=seed)
    )

    # Save results
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "screening_results.json"
    results_data = [d.model_dump(mode="json") for d in decisions]
    results_path.write_text(json.dumps(results_data, indent=2, ensure_ascii=False))

    # Summary
    from metascreener.core.enums import Decision  # noqa: PLC0415

    n_include = sum(1 for d in decisions if d.decision == Decision.INCLUDE)
    n_exclude = sum(1 for d in decisions if d.decision == Decision.EXCLUDE)
    n_review = sum(1 for d in decisions if d.decision == Decision.HUMAN_REVIEW)

    typer.echo(f"\n[screen] Done. Results saved to {results_path}")
    typer.echo(f"  INCLUDE: {n_include}  |  EXCLUDE: {n_exclude}  |  HUMAN_REVIEW: {n_review}")

    # Save audit trail
    audit_path = output_dir / "audit_trail.json"
    audit_entries = [
        screener.build_audit_entry(record, review_criteria, decision).model_dump(mode="json")
        for record, decision in zip(records, decisions, strict=True)
    ]
    audit_path.write_text(json.dumps(audit_entries, indent=2, ensure_ascii=False))
    typer.echo(f"  Audit trail: {audit_path}")


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
    records: collections.abc.Sequence[object] = []

    if not input_path.exists():
        errors.append(f"Input file not found: {input_path}")

    if criteria_path is not None and not criteria_path.exists():
        errors.append(f"Criteria file not found: {criteria_path}")

    # Try to parse the input file
    if not errors and input_path.exists():
        from metascreener.io.readers import read_records  # noqa: PLC0415

        try:
            records = read_records(input_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Cannot parse input file: {exc}")

    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"[dry-run] Loaded {len(records)} records from {input_path}")
    model_names = ", ".join(cfg.models.keys()) if cfg.models else "(default)"
    typer.echo("[dry-run] Validation passed:")
    typer.echo(f"  Input: {input_path}")
    typer.echo(f"  Stage: {stage.value}")
    typer.echo(f"  Output: {output_dir}")
    if criteria_path:
        typer.echo(f"  Criteria: {criteria_path}")
    typer.echo(f"  Models: {len(cfg.models)} ({model_names})")
    typer.echo(f"  Sensitivity target: {cfg.thresholds.target_sensitivity}")
