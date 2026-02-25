"""MetaScreener interactive REPL with slash commands and guided prompts."""
from __future__ import annotations

from pathlib import Path

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

logger = structlog.get_logger(__name__)

console = Console()

VERSION = "2.0.0a3"

BANNER = f"""\
[bold cyan]MetaScreener {VERSION}[/bold cyan]
[dim]AI-assisted systematic review tool[/dim]
[dim]Hierarchical Consensus Network (HCN) with 4 open-source LLMs[/dim]

Type [bold green]/help[/bold green] for commands, [bold green]/quit[/bold green] to exit.
"""

COMMANDS: dict[str, str] = {
    "/init": "Generate structured review criteria (PICO/PEO/SPIDER/PCC)",
    "/screen": "Screen literature (title/abstract or full-text)",
    "/extract": "Extract structured data from PDFs",
    "/assess-rob": "Assess risk of bias (RoB 2 / ROBINS-I / QUADAS-2)",
    "/evaluate": "Evaluate screening performance and compute metrics",
    "/export": "Export results (CSV, JSON, Excel, RIS)",
    "/help": "Show this help message",
    "/status": "Show current working files and project state",
    "/quit": "Exit MetaScreener",
}


def run_interactive() -> None:
    """Launch the interactive REPL."""
    console.print(Panel(BANNER, border_style="cyan", padding=(1, 2)))
    _show_quick_start()

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]metascreener[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        cmd = user_input.split()[0].lower()

        if cmd in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye![/dim]")
            break
        elif cmd == "/help":
            _show_help()
        elif cmd == "/status":
            _show_status()
        elif cmd == "/init":
            _handle_init()
        elif cmd == "/screen":
            _handle_screen()
        elif cmd == "/extract":
            _handle_extract()
        elif cmd == "/assess-rob":
            _handle_assess_rob()
        elif cmd == "/evaluate":
            _handle_evaluate()
        elif cmd == "/export":
            _handle_export()
        elif cmd.startswith("/"):
            console.print(
                f"[yellow]Unknown command: {cmd}[/yellow]\n"
                "Type [bold green]/help[/bold green] to see available commands."
            )
        else:
            console.print(
                "[yellow]Please use a slash command.[/yellow]\n"
                "Type [bold green]/help[/bold green] to see available commands."
            )


def _show_quick_start() -> None:
    """Show quick start guide for new users."""
    table = Table(
        title="Quick Start — Typical Workflow",
        show_header=False,
        border_style="dim",
        padding=(0, 2),
    )
    table.add_column("Step", style="bold cyan", width=6)
    table.add_column("Command", style="green", width=14)
    table.add_column("Description", style="white")
    table.add_row("1", "/init", "Define your review criteria (PICO, topic, or text)")
    table.add_row("2", "/screen", "Screen papers against your criteria")
    table.add_row("3", "/evaluate", "Evaluate screening accuracy (if gold labels available)")
    table.add_row("4", "/extract", "Extract structured data from included PDFs")
    table.add_row("5", "/assess-rob", "Assess risk of bias for included studies")
    table.add_row("6", "/export", "Export results in your preferred format")
    console.print(table)


def _show_help() -> None:
    """Display help with all available commands."""
    table = Table(title="Available Commands", border_style="cyan")
    table.add_column("Command", style="bold green", width=16)
    table.add_column("Description", style="white")
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(table)
    console.print(
        "\n[dim]Each command will guide you step-by-step through the required inputs.[/dim]"
    )


def _show_status() -> None:
    """Show current project state — detect existing files."""
    cwd = Path.cwd()
    console.print(f"\n[bold]Working directory:[/bold] {cwd}")

    # Check for common project files
    found: list[tuple[str, str]] = []
    not_found: list[str] = []

    checks = [
        ("criteria.yaml", "Review criteria"),
        ("results/screening_results.json", "Screening results"),
        ("results/audit_trail.json", "Audit trail"),
        ("results/evaluation_report.json", "Evaluation report"),
        ("results/extraction_results.json", "Extraction results"),
        ("extraction_form.yaml", "Extraction form"),
        ("export/results.csv", "Exported CSV"),
    ]

    for path, label in checks:
        if (cwd / path).exists():
            found.append((path, label))
        else:
            not_found.append(label)

    if found:
        table = Table(title="Found Files", border_style="green", show_header=False)
        table.add_column("File", style="green")
        table.add_column("Description")
        for path, label in found:
            table.add_row(path, label)
        console.print(table)
    else:
        console.print("[yellow]No MetaScreener output files found in this directory.[/yellow]")
        console.print("[dim]Start with /init to create review criteria.[/dim]")


# ---------------------------------------------------------------------------
# /init — Criteria Wizard
# ---------------------------------------------------------------------------
def _handle_init() -> None:
    """Guide user through criteria initialization."""
    console.print(Panel(
        "[bold]Step 0: Initialize Review Criteria[/bold]\n\n"
        "MetaScreener will help you create structured criteria (criteria.yaml)\n"
        "for screening. Choose how you'd like to provide your criteria:",
        border_style="cyan",
    ))

    mode = Prompt.ask(
        "How would you like to create criteria?",
        choices=["text", "topic"],
        default="text",
    )

    if mode == "text":
        console.print(
            "\n[bold]Mode A: User-Provided Text[/bold]\n"
            "Provide a text file with your review criteria (e.g., PICO elements).\n"
            "MetaScreener will validate, refine, and structure it.\n"
        )
        criteria_path = _ask_file_path(
            "Path to your criteria text file",
            must_exist=True,
            example="criteria.txt",
        )
        if criteria_path is None:
            return
        raw_input_flag = f"--criteria {criteria_path}"
    else:
        console.print(
            "\n[bold]Mode B: AI-Generated from Topic[/bold]\n"
            "Provide a research topic and MetaScreener will generate complete\n"
            "criteria using multi-LLM consensus.\n"
        )
        topic = Prompt.ask("Enter your research topic")
        if not topic.strip():
            console.print("[yellow]No topic provided. Cancelled.[/yellow]")
            return
        raw_input_flag = f'--topic "{topic}"'

    output = Prompt.ask("Output path for criteria.yaml", default="criteria.yaml")

    # Confirm and run
    console.print(f"\n[dim]Running: metascreener init {raw_input_flag} --output {output}[/dim]")
    if not Confirm.ask("Proceed?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    _run_typer_command(["init", *_split_flag(raw_input_flag), "--output", output])


# ---------------------------------------------------------------------------
# /screen — Literature Screening
# ---------------------------------------------------------------------------
def _handle_screen() -> None:
    """Guide user through literature screening."""
    console.print(Panel(
        "[bold]Module 1: Literature Screening[/bold]\n\n"
        "Screen papers using the Hierarchical Consensus Network (HCN).\n"
        "4 LLMs analyze each paper and reach consensus via calibrated aggregation.",
        border_style="cyan",
    ))

    # Input file
    input_path = _ask_file_path(
        "Path to your input file (RIS/BibTeX/CSV)",
        must_exist=True,
        example="search_results.ris",
    )
    if input_path is None:
        return

    # Criteria file
    criteria_path = _ask_file_path(
        "Path to criteria.yaml",
        must_exist=True,
        example="criteria.yaml",
        default="criteria.yaml",
    )
    if criteria_path is None:
        return

    # Stage
    stage = Prompt.ask(
        "Screening stage",
        choices=["ta", "ft", "both"],
        default="ta",
    )
    stage_labels = {"ta": "Title/Abstract", "ft": "Full-text", "both": "Both stages"}
    console.print(f"  Stage: [cyan]{stage_labels[stage]}[/cyan]")

    # Output
    output_dir = Prompt.ask("Output directory", default="results")

    # Seed
    seed = Prompt.ask("Random seed (for reproducibility)", default="42")

    # Confirm
    console.print(
        f"\n[dim]Running: metascreener screen "
        f"--input {input_path} --criteria {criteria_path} "
        f"--stage {stage} --output {output_dir} --seed {seed}[/dim]"
    )
    if not Confirm.ask("Proceed?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    _run_typer_command([
        "screen",
        "--input", str(input_path),
        "--criteria", str(criteria_path),
        "--stage", stage,
        "--output", output_dir,
        "--seed", seed,
    ])


# ---------------------------------------------------------------------------
# /extract — Data Extraction
# ---------------------------------------------------------------------------
def _handle_extract() -> None:
    """Guide user through data extraction."""
    console.print(Panel(
        "[bold]Module 2: Data Extraction[/bold]\n\n"
        "Extract structured data from full-text PDFs using multi-LLM consensus.\n"
        "You need an extraction form (YAML) defining what to extract.",
        border_style="cyan",
    ))

    has_form = Confirm.ask("Do you already have an extraction_form.yaml?", default=True)

    if not has_form:
        console.print(
            "\n[bold]Generate Extraction Form[/bold]\n"
            "MetaScreener can generate a form based on your research topic.\n"
        )
        topic = Prompt.ask("Enter your research topic")
        if not topic.strip():
            console.print("[yellow]No topic provided. Cancelled.[/yellow]")
            return
        form_output = Prompt.ask("Output path for form", default="extraction_form.yaml")

        console.print(
            f"\n[dim]Running: metascreener extract init-form "
            f'--topic "{topic}" --output {form_output}[/dim]'
        )
        if not Confirm.ask("Proceed?", default=True):
            console.print("[yellow]Cancelled.[/yellow]")
            return

        _run_typer_command([
            "extract", "init-form",
            "--topic", topic,
            "--output", form_output,
        ])

        console.print(
            f"\n[green]Form generated![/green] "
            f"You can edit [bold]{form_output}[/bold] before running extraction."
        )
        if not Confirm.ask("Continue to extraction now?", default=True):
            return
        form_path_str = form_output
    else:
        fp = _ask_file_path(
            "Path to extraction_form.yaml",
            must_exist=True,
            example="extraction_form.yaml",
            default="extraction_form.yaml",
        )
        if fp is None:
            return
        form_path_str = str(fp)

    # PDF directory
    pdfs_dir = _ask_dir_path(
        "Directory containing PDF files",
        must_exist=True,
        example="papers/",
    )
    if pdfs_dir is None:
        return

    output_dir = Prompt.ask("Output directory", default="results")

    console.print(
        f"\n[dim]Running: metascreener extract "
        f"--pdfs {pdfs_dir} --form {form_path_str} --output {output_dir}[/dim]"
    )
    if not Confirm.ask("Proceed?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    _run_typer_command([
        "extract",
        "--pdfs", str(pdfs_dir),
        "--form", form_path_str,
        "--output", output_dir,
    ])


# ---------------------------------------------------------------------------
# /assess-rob — Risk of Bias Assessment
# ---------------------------------------------------------------------------
def _handle_assess_rob() -> None:
    """Guide user through risk of bias assessment."""
    console.print(Panel(
        "[bold]Module 3: Risk of Bias Assessment[/bold]\n\n"
        "Assess risk of bias using standardized tools:\n"
        "  [cyan]rob2[/cyan]      — RoB 2 for randomized controlled trials (5 domains)\n"
        "  [cyan]robins-i[/cyan]  — ROBINS-I for observational studies (7 domains)\n"
        "  [cyan]quadas2[/cyan]   — QUADAS-2 for diagnostic accuracy studies (4 domains)",
        border_style="cyan",
    ))

    tool = Prompt.ask(
        "Which RoB tool?",
        choices=["rob2", "robins-i", "quadas2"],
        default="rob2",
    )

    pdfs_dir = _ask_dir_path(
        "Directory containing PDF files",
        must_exist=True,
        example="papers/",
    )
    if pdfs_dir is None:
        return

    output_dir = Prompt.ask("Output directory", default="results")
    seed = Prompt.ask("Random seed", default="42")

    console.print(
        f"\n[dim]Running: metascreener assess-rob "
        f"--pdfs {pdfs_dir} --tool {tool} --output {output_dir} --seed {seed}[/dim]"
    )
    if not Confirm.ask("Proceed?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    _run_typer_command([
        "assess-rob",
        "--pdfs", str(pdfs_dir),
        "--tool", tool,
        "--output", output_dir,
        "--seed", seed,
    ])


# ---------------------------------------------------------------------------
# /evaluate — Evaluation
# ---------------------------------------------------------------------------
def _handle_evaluate() -> None:
    """Guide user through screening evaluation."""
    console.print(Panel(
        "[bold]Evaluation Mode[/bold]\n\n"
        "Compare screening results against gold-standard labels to compute:\n"
        "sensitivity, specificity, F1, WSS@95, AUROC, ECE, Brier score, kappa.\n"
        "Optionally generate interactive Plotly visualizations.",
        border_style="cyan",
    ))

    labels_path = _ask_file_path(
        "Path to gold-standard labels CSV (columns: record_id, label)",
        must_exist=True,
        example="gold_labels.csv",
    )
    if labels_path is None:
        return

    preds_path = _ask_file_path(
        "Path to predictions JSON (screening_results.json)",
        must_exist=True,
        example="results/screening_results.json",
        default="results/screening_results.json",
    )
    if preds_path is None:
        return

    visualize = Confirm.ask("Generate visualizations (ROC, calibration, etc.)?", default=True)
    output_dir = Prompt.ask("Output directory", default="results")
    seed = Prompt.ask("Random seed", default="42")

    viz_flag = " --visualize" if visualize else ""
    console.print(
        f"\n[dim]Running: metascreener evaluate "
        f"--labels {labels_path} --predictions {preds_path}"
        f"{viz_flag} --output {output_dir} --seed {seed}[/dim]"
    )
    if not Confirm.ask("Proceed?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    args = [
        "evaluate",
        "--labels", str(labels_path),
        "--predictions", str(preds_path),
        "--output", output_dir,
        "--seed", seed,
    ]
    if visualize:
        args.append("--visualize")

    _run_typer_command(args)


# ---------------------------------------------------------------------------
# /export — Export Results
# ---------------------------------------------------------------------------
def _handle_export() -> None:
    """Guide user through exporting results."""
    console.print(Panel(
        "[bold]Export Results[/bold]\n\n"
        "Export screening results in one or more formats:\n"
        "  [cyan]csv[/cyan]    — Comma-separated values\n"
        "  [cyan]json[/cyan]   — Pretty-printed JSON\n"
        "  [cyan]excel[/cyan]  — Excel spreadsheet (.xlsx)\n"
        "  [cyan]ris[/cyan]    — Research Information Systems format\n"
        "  [cyan]audit[/cyan]  — Full audit trail JSON",
        border_style="cyan",
    ))

    results_path = _ask_file_path(
        "Path to results JSON file",
        must_exist=True,
        example="results/screening_results.json",
        default="results/screening_results.json",
    )
    if results_path is None:
        return

    console.print("\nSelect export formats (comma-separated):")
    formats = Prompt.ask("Formats", default="csv,json")

    output_dir = Prompt.ask("Output directory", default="export")

    console.print(
        f"\n[dim]Running: metascreener export "
        f"--results {results_path} --format {formats} --output {output_dir}[/dim]"
    )
    if not Confirm.ask("Proceed?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    _run_typer_command([
        "export",
        "--results", str(results_path),
        "--format", formats,
        "--output", output_dir,
    ])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ask_file_path(
    prompt: str,
    *,
    must_exist: bool = False,
    example: str = "",
    default: str | None = None,
) -> Path | None:
    """Ask user for a file path with validation.

    Args:
        prompt: Question to display.
        must_exist: Whether the file must already exist.
        example: Example path to show.
        default: Default value.

    Returns:
        Validated Path or None if user cancels.
    """
    hint = f" (e.g., {example})" if example else ""
    while True:
        raw = Prompt.ask(f"{prompt}{hint}", default=default or "")
        if not raw.strip():
            console.print("[yellow]No path provided. Cancelled.[/yellow]")
            return None

        path = Path(raw.strip())
        if must_exist and not path.exists():
            console.print(f"[red]File not found: {path}[/red]")
            if not Confirm.ask("Try again?", default=True):
                return None
            continue
        return path


def _ask_dir_path(
    prompt: str,
    *,
    must_exist: bool = False,
    example: str = "",
) -> Path | None:
    """Ask user for a directory path with validation.

    Args:
        prompt: Question to display.
        must_exist: Whether the directory must already exist.
        example: Example path to show.

    Returns:
        Validated Path or None if user cancels.
    """
    hint = f" (e.g., {example})" if example else ""
    while True:
        raw = Prompt.ask(f"{prompt}{hint}")
        if not raw.strip():
            console.print("[yellow]No path provided. Cancelled.[/yellow]")
            return None

        path = Path(raw.strip())
        if must_exist and not path.exists():
            console.print(f"[red]Directory not found: {path}[/red]")
            if not Confirm.ask("Try again?", default=True):
                return None
            continue
        if must_exist and not path.is_dir():
            console.print(f"[red]Not a directory: {path}[/red]")
            if not Confirm.ask("Try again?", default=True):
                return None
            continue
        return path


def _split_flag(flag_string: str) -> list[str]:
    """Split a flag string into a list, handling quoted values.

    Args:
        flag_string: Flag string like '--topic "some text"'.

    Returns:
        List of argument strings.
    """
    import shlex  # noqa: PLC0415

    return shlex.split(flag_string)


def _run_typer_command(args: list[str]) -> None:
    """Run a MetaScreener CLI command by invoking the Typer app.

    Args:
        args: List of command arguments (e.g., ["screen", "--input", "file.ris"]).
    """
    from metascreener.cli import app  # noqa: PLC0415

    console.print()
    try:
        app(args, standalone_mode=False)
    except SystemExit as e:
        if e.code and e.code != 0:
            console.print(f"\n[red]Command exited with code {e.code}[/red]")
        else:
            console.print("\n[green]Done![/green]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"\n[red]Error: {exc}[/red]")
        logger.error("interactive_command_error", error=str(exc), args=args)
    else:
        console.print("\n[green]Done![/green]")
