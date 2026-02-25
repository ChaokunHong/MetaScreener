"""MetaScreener interactive REPL with slash commands and guided prompts."""
from __future__ import annotations

import subprocess
import sys
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
[dim]Tip: Enter [bold]7[/bold] or [bold]/ui[/bold] to open the web dashboard[/dim]
"""

# Numbered menu items: (number, slash_cmd, description, handler_name)
MENU_ITEMS: list[tuple[str, str, str]] = [
    ("/init", "Define review criteria (PICO/PEO/SPIDER/PCC)", "_handle_init"),
    ("/screen", "Screen literature (title/abstract or full-text)", "_handle_screen"),
    ("/extract", "Extract structured data from PDFs", "_handle_extract"),
    ("/assess-rob", "Assess risk of bias (RoB 2 / ROBINS-I / QUADAS-2)", "_handle_assess_rob"),
    ("/evaluate", "Evaluate screening performance", "_handle_evaluate"),
    ("/export", "Export results (CSV, JSON, Excel, RIS)", "_handle_export"),
    ("/ui", "Open web dashboard (Streamlit)", "_handle_ui"),
]

COMMANDS: dict[str, str] = {
    "/init": "Generate structured review criteria (PICO/PEO/SPIDER/PCC)",
    "/screen": "Screen literature (title/abstract or full-text)",
    "/extract": "Extract structured data from PDFs",
    "/assess-rob": "Assess risk of bias (RoB 2 / ROBINS-I / QUADAS-2)",
    "/evaluate": "Evaluate screening performance and compute metrics",
    "/export": "Export results (CSV, JSON, Excel, RIS)",
    "/ui": "Open web dashboard (Streamlit)",
    "/help": "Show this help message",
    "/status": "Show current working files and project state",
    "/quit": "Exit MetaScreener",
}

# Map slash commands to handler functions
_HANDLERS: dict[str, str] = {
    "/init": "_handle_init",
    "/screen": "_handle_screen",
    "/extract": "_handle_extract",
    "/assess-rob": "_handle_assess_rob",
    "/evaluate": "_handle_evaluate",
    "/export": "_handle_export",
    "/ui": "_handle_ui",
}


def run_interactive() -> None:
    """Launch the interactive REPL."""
    console.print(Panel(BANNER, border_style="cyan", padding=(1, 2)))
    _show_main_menu()

    while True:
        console.print()
        try:
            user_input = Prompt.ask(
                "[bold cyan]>>>[/bold cyan] Enter a number (1-7), "
                "a command (/help), or /quit",
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            _show_main_menu()
            continue

        # Handle numbered selection (1-7)
        if user_input.isdigit():
            idx = int(user_input)
            if 1 <= idx <= len(MENU_ITEMS):
                cmd_name, desc, handler_name = MENU_ITEMS[idx - 1]
                console.print(f"\n[bold green]{cmd_name}[/bold green] — {desc}\n")
                handler = globals()[handler_name]
                handler()
                console.print()
                _show_main_menu()
                continue
            else:
                console.print(
                    f"[yellow]Please enter a number between 1 and {len(MENU_ITEMS)}.[/yellow]"
                )
                continue

        cmd = user_input.split()[0].lower()

        if cmd in ("/quit", "/exit", "/q", "quit", "exit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break
        elif cmd in ("/help", "help", "h", "?"):
            _show_help()
        elif cmd in ("/status", "status"):
            _show_status()
        elif cmd in ("/menu", "menu", "m"):
            _show_main_menu()
        elif cmd in _HANDLERS:
            handler = globals()[_HANDLERS[cmd]]
            handler()
            console.print()
            _show_main_menu()
        elif cmd.startswith("/"):
            console.print(
                f"[yellow]Unknown command: {cmd}[/yellow]\n"
                "Type [bold green]/help[/bold green] or a number (1-7)."
            )
        else:
            console.print(
                "[yellow]Tip: Enter a number (1-7) to select a command, "
                "or type /help for all options.[/yellow]"
            )


def _show_main_menu() -> None:
    """Show the main numbered menu."""
    table = Table(
        title="What would you like to do?",
        show_header=False,
        border_style="cyan",
        padding=(0, 2),
        title_style="bold",
    )
    table.add_column("No.", style="bold yellow", width=4, justify="right")
    table.add_column("Command", style="bold green", width=14)
    table.add_column("Description", style="white")

    for i, (cmd, desc, _handler) in enumerate(MENU_ITEMS, 1):
        table.add_row(str(i), cmd, desc)

    console.print(table)
    console.print(
        "[dim]  Also: /help  /status  /quit[/dim]"
    )


def _show_help() -> None:
    """Display help with all available commands."""
    table = Table(title="All Commands", border_style="cyan")
    table.add_column("Command", style="bold green", width=16)
    table.add_column("Description", style="white")
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(table)
    console.print(
        "\n[dim]You can type a number (1-7) or a /command. "
        "Each command guides you step-by-step.[/dim]"
    )


def _show_status() -> None:
    """Show current project state — detect existing files."""
    cwd = Path.cwd()
    console.print(f"\n[bold]Working directory:[/bold] {cwd}")

    # Check for common project files
    found: list[tuple[str, str]] = []

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

    if found:
        table = Table(title="Found Files", border_style="green", show_header=False)
        table.add_column("File", style="green")
        table.add_column("Description")
        for path, label in found:
            table.add_row(path, label)
        console.print(table)
    else:
        console.print("[yellow]No MetaScreener output files found in this directory.[/yellow]")
        console.print("[dim]Start with 1 (/init) to create review criteria.[/dim]")


# ---------------------------------------------------------------------------
# /init — Criteria Wizard
# ---------------------------------------------------------------------------
def _handle_init() -> None:
    """Guide user through criteria initialization."""
    console.print(Panel(
        "[bold]Step 0: Initialize Review Criteria[/bold]\n\n"
        "MetaScreener will help you create structured criteria (criteria.yaml)\n"
        "for screening. Choose how you'd like to provide your criteria:\n\n"
        "  [yellow]1[/yellow]  [bold]text[/bold]  — Provide a text file with your criteria\n"
        "  [yellow]2[/yellow]  [bold]topic[/bold] — Provide a topic, AI generates criteria",
        border_style="cyan",
    ))

    mode = Prompt.ask(
        "Select mode (1=text, 2=topic)",
        choices=["1", "2", "text", "topic"],
        default="1",
    )
    mode = "text" if mode in ("1", "text") else "topic"

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
    console.print(f"\n[dim]Command: metascreener init {raw_input_flag} --output {output}[/dim]")
    if not Confirm.ask("Run this command?", default=True):
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
        "4 LLMs analyze each paper and reach consensus via calibrated aggregation.\n\n"
        "[dim]Required: input file (.ris/.bib/.csv) + criteria.yaml[/dim]",
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
    console.print(
        "\nScreening stage:\n"
        "  [yellow]1[/yellow]  [bold]ta[/bold]   — Title/Abstract only (fast)\n"
        "  [yellow]2[/yellow]  [bold]ft[/bold]   — Full-text only\n"
        "  [yellow]3[/yellow]  [bold]both[/bold] — Both stages sequentially"
    )
    stage_input = Prompt.ask(
        "Select stage (1/2/3)",
        choices=["1", "2", "3", "ta", "ft", "both"],
        default="1",
    )
    stage_map = {"1": "ta", "2": "ft", "3": "both"}
    stage = stage_map.get(stage_input, stage_input)
    stage_labels = {"ta": "Title/Abstract", "ft": "Full-text", "both": "Both stages"}
    console.print(f"  Selected: [cyan]{stage_labels[stage]}[/cyan]")

    # Output
    output_dir = Prompt.ask("Output directory", default="results")

    # Seed
    seed = Prompt.ask("Random seed (for reproducibility)", default="42")

    # Confirm
    console.print(
        f"\n[dim]Command: metascreener screen "
        f"--input {input_path} --criteria {criteria_path} "
        f"--stage {stage} --output {output_dir} --seed {seed}[/dim]"
    )
    if not Confirm.ask("Run this command?", default=True):
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
        "You need an extraction form (YAML) defining what to extract.\n\n"
        "  [yellow]1[/yellow]  I have an extraction_form.yaml\n"
        "  [yellow]2[/yellow]  Generate a form for me (from research topic)",
        border_style="cyan",
    ))

    choice = Prompt.ask("Select (1 or 2)", choices=["1", "2"], default="1")

    if choice == "2":
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
            f'\n[dim]Command: metascreener extract init-form '
            f'--topic "{topic}" --output {form_output}[/dim]'
        )
        if not Confirm.ask("Run this command?", default=True):
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
        f"\n[dim]Command: metascreener extract "
        f"--pdfs {pdfs_dir} --form {form_path_str} --output {output_dir}[/dim]"
    )
    if not Confirm.ask("Run this command?", default=True):
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
        "Choose a tool based on your study design:\n\n"
        "  [yellow]1[/yellow]  [bold]rob2[/bold]      — RoB 2 for RCTs\n"
        "  [yellow]2[/yellow]  [bold]robins-i[/bold]  — ROBINS-I for observational\n"
        "  [yellow]3[/yellow]  [bold]quadas2[/bold]   — QUADAS-2 for diagnostic",
        border_style="cyan",
    ))

    tool_input = Prompt.ask(
        "Select tool (1/2/3)",
        choices=["1", "2", "3", "rob2", "robins-i", "quadas2"],
        default="1",
    )
    tool_map = {"1": "rob2", "2": "robins-i", "3": "quadas2"}
    tool = tool_map.get(tool_input, tool_input)
    console.print(f"  Selected: [cyan]{tool}[/cyan]")

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
        f"\n[dim]Command: metascreener assess-rob "
        f"--pdfs {pdfs_dir} --tool {tool} --output {output_dir} --seed {seed}[/dim]"
    )
    if not Confirm.ask("Run this command?", default=True):
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
        "Compare screening results against gold-standard labels.\n"
        "Computes: sensitivity, specificity, F1, WSS@95, AUROC, ECE, Brier, kappa.\n\n"
        "[dim]Required: labels CSV + predictions JSON[/dim]",
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
        f"\n[dim]Command: metascreener evaluate "
        f"--labels {labels_path} --predictions {preds_path}"
        f"{viz_flag} --output {output_dir} --seed {seed}[/dim]"
    )
    if not Confirm.ask("Run this command?", default=True):
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
        "Export screening results in one or more formats:\n\n"
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

    console.print("\nSelect export formats (comma-separated, e.g. csv,json):")
    formats = Prompt.ask("Formats", default="csv,json")

    output_dir = Prompt.ask("Output directory", default="export")

    console.print(
        f"\n[dim]Command: metascreener export "
        f"--results {results_path} --format {formats} --output {output_dir}[/dim]"
    )
    if not Confirm.ask("Run this command?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    _run_typer_command([
        "export",
        "--results", str(results_path),
        "--format", formats,
        "--output", output_dir,
    ])


# ---------------------------------------------------------------------------
# /ui — Launch Streamlit Web Dashboard
# ---------------------------------------------------------------------------
def _handle_ui() -> None:
    """Launch the Streamlit web dashboard in the user's browser."""
    app_path = Path(__file__).parent.parent / "app" / "main.py"
    if not app_path.exists():
        console.print("[red]Streamlit app not found. Reinstall MetaScreener.[/red]")
        return

    console.print(
        "[cyan]Launching Streamlit dashboard...[/cyan]\n"
        "[dim]Opening http://localhost:8501 in your browser.[/dim]\n"
        "[dim]Press Ctrl+C to stop the server and return here.[/dim]"
    )
    try:
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path),
             "--server.headless=true"],
            check=False,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Streamlit server stopped.[/dim]")


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
