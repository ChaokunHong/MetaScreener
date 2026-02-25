"""metascreener init — Criteria wizard CLI command."""
from __future__ import annotations

from pathlib import Path

import structlog
import typer

from metascreener.core.enums import CriteriaFramework, WizardMode

logger = structlog.get_logger(__name__)

init_app = typer.Typer(help="Initialize review criteria via the AI-powered wizard.")


@init_app.callback(invoke_without_command=True)
def init(  # noqa: C901
    ctx: typer.Context,  # noqa: ARG001
    criteria: Path | None = typer.Option(  # noqa: B008
        None,
        "--criteria",
        "-c",
        help="Criteria text file (Mode A: user-provided text).",
    ),
    topic: str | None = typer.Option(  # noqa: B008
        None,
        "--topic",
        "-t",
        help="Research topic (Mode B: AI-generated criteria).",
    ),
    mode: WizardMode = typer.Option(  # noqa: B008
        WizardMode.SMART,
        "--mode",
        "-m",
        help="Interaction mode.",
    ),
    output: Path = typer.Option(  # noqa: B008
        Path("criteria.yaml"),
        "--output",
        "-o",
        help="Output path for generated criteria.yaml.",
    ),
    framework: str | None = typer.Option(  # noqa: B008
        None,
        "--framework",
        "-f",
        help="Override auto-detected criteria framework.",
    ),
    template: str | None = typer.Option(  # noqa: B008
        None,
        "--template",
        help="Start from a preset template.",
    ),
    language: str | None = typer.Option(  # noqa: B008
        None,
        "--language",
        "-l",
        help="Force output language.",
    ),
    resume: bool = typer.Option(  # noqa: B008
        False,
        "--resume",
        help="Resume interrupted session.",
    ),
    clean_sessions: bool = typer.Option(  # noqa: B008
        False,
        "--clean-sessions",
        help="Remove old session files.",
    ),
) -> None:
    """Initialize review criteria using the AI-powered wizard.

    Two primary modes:

      Mode A (--criteria FILE): Provide your own criteria text; the wizard
      validates, refines, and structures it into criteria.yaml.

      Mode B (--topic TEXT): Provide a research topic; the wizard generates
      complete criteria via multi-LLM consensus.
    """
    # Handle session cleanup first (no other flags needed)
    if clean_sessions:
        from metascreener.criteria.session import SessionManager

        mgr = SessionManager()
        removed = mgr.cleanup()
        typer.echo(f"Cleaned {removed} old session(s).")
        logger.info("sessions_cleaned_via_cli", removed=removed)
        return

    # Handle resume
    if resume:
        typer.echo("[init] Resuming previous session...")
        typer.echo("Not fully implemented — coming soon.")
        logger.info("session_resume_requested")
        return

    # Validate mutual exclusion
    if criteria and topic:
        typer.echo(
            "Error: --criteria and --topic are mutually exclusive. "
            "Provide only one.",
            err=True,
        )
        raise typer.Exit(code=1)

    # Require at least one input source
    if not criteria and not topic and not template:
        typer.echo(
            "Error: Please provide --criteria FILE, --topic TEXT, "
            "or --template NAME.",
            err=True,
        )
        raise typer.Exit(code=1)

    # Parse and validate framework override
    fw_override: CriteriaFramework | None = None
    if framework:
        try:
            fw_override = CriteriaFramework(framework.lower())
        except ValueError:
            valid = ", ".join(f.value for f in CriteriaFramework)
            typer.echo(
                f"Error: Unknown framework '{framework}'. "
                f"Valid options: {valid}",
                err=True,
            )
            raise typer.Exit(code=1) from None

    # Handle template mode
    if template:
        typer.echo(f"[init] Starting from template: {template}")
        typer.echo("Template-based initialization — coming soon.")
        logger.info("template_mode_requested", template=template)
        return

    # Determine input mode and raw text
    if criteria:
        if not criteria.exists():
            typer.echo(f"Error: File not found: {criteria}", err=True)
            raise typer.Exit(code=1)
        raw_input = criteria.read_text()
        input_mode_str = "text"
    elif topic:
        raw_input = topic
        input_mode_str = "topic"
    else:
        # Should not reach here due to earlier validation
        raw_input = ""
        input_mode_str = "topic"

    fw_label = fw_override.value if fw_override else "auto"
    typer.echo(
        f"[init] Mode: {mode.value} | Framework: {fw_label} | Output: {output}"
    )

    preview = raw_input[:80]
    if len(raw_input) > 80:
        preview += "..."
    typer.echo(f"[init] Input ({input_mode_str}): {preview}")

    if language:
        typer.echo(f"[init] Language override: {language}")

    # Run the wizard with real LLM backends
    import asyncio  # noqa: PLC0415

    from metascreener.core.enums import CriteriaInputMode  # noqa: PLC0415
    from metascreener.criteria.wizard import CriteriaWizard  # noqa: PLC0415
    from metascreener.llm.factory import create_backends  # noqa: PLC0415

    backends = create_backends()
    wizard = CriteriaWizard(
        generation_backends=backends,
        detector_backend=backends[0],
        quality_backend=backends[0],
        output_dir=output.parent,
    )

    # CLI callbacks for interactive wizard
    async def _ask_user(question: str) -> str:
        typer.echo(f"\n{question}")
        return input("> ").strip()  # noqa: A001

    async def _show_status(msg: str) -> None:
        typer.echo(f"  {msg}")

    async def _confirm(question: str) -> bool:
        typer.echo(f"\n{question} [y/n]")
        return input("> ").strip().lower() in ("y", "yes")

    input_mode_enum = (
        CriteriaInputMode.TEXT if input_mode_str == "text"
        else CriteriaInputMode.TOPIC
    )

    typer.echo("[init] Starting criteria wizard...")
    result = asyncio.run(wizard.run(
        input_mode=input_mode_enum,
        wizard_mode=mode,
        raw_input=raw_input,
        ask_user=_ask_user,
        show_status=_show_status,
        confirm=_confirm,
        override_framework=fw_override,
        language=language,
    ))

    # Save to output path
    from metascreener.criteria.schema import CriteriaSchema  # noqa: PLC0415

    CriteriaSchema.save(result, output)
    typer.echo(f"\n[init] Criteria saved to {output}")
    typer.echo(f"  Framework: {result.framework.value}")
    typer.echo(f"  Elements: {', '.join(result.elements.keys())}")

    logger.info(
        "init_command_completed",
        input_mode=input_mode_str,
        framework=result.framework.value,
        output=str(output),
    )
