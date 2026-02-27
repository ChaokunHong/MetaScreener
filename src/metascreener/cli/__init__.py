"""MetaScreener 2.0 CLI — Typer application."""
from __future__ import annotations

import typer

from metascreener.cli.assess_cmd import assess_app
from metascreener.cli.evaluate_cmd import evaluate_app
from metascreener.cli.export_cmd import export_app
from metascreener.cli.extract_cmd import extract_app
from metascreener.cli.init_cmd import init_app
from metascreener.cli.screen_cmd import screen_app

app = typer.Typer(
    name="metascreener",
    help="MetaScreener 2.0: AI-assisted systematic review tool.",
    add_completion=False,
    invoke_without_command=True,
)


@app.callback()
def main(ctx: typer.Context) -> None:
    """MetaScreener 2.0: AI-assisted systematic review tool.

    Run without a subcommand to enter interactive mode with guided prompts.
    """
    if ctx.invoked_subcommand is None:
        from metascreener.cli.interactive import run_interactive  # noqa: PLC0415

        run_interactive()


app.add_typer(init_app, name="init")
app.add_typer(screen_app, name="screen")
app.add_typer(evaluate_app, name="evaluate")
app.add_typer(extract_app, name="extract")
app.add_typer(assess_app, name="assess-rob")
app.add_typer(export_app, name="export")


@app.command()
def ui() -> None:
    """Launch the Streamlit web dashboard."""
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    app_path = Path(__file__).parent.parent / "app" / "main.py"
    if not app_path.exists():
        typer.echo("Error: Streamlit app not found.", err=True)
        raise typer.Exit(code=1)

    typer.echo("Launching MetaScreener web dashboard...")
    typer.echo("Open http://localhost:8501 in your browser.")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path),
         "--server.headless=true"],
        check=False,
    )


@app.command()
def serve(
    port: int = typer.Option(8000, help="Port to listen on."),  # noqa: B008
    host: str = typer.Option("127.0.0.1", help="Host to bind to."),  # noqa: B008
    api_only: bool = typer.Option(  # noqa: B008
        False, "--api-only", help="Only start API server, skip frontend."
    ),
) -> None:
    """Launch the FastAPI web server with React UI."""
    import uvicorn  # noqa: PLC0415

    typer.echo(f"Starting MetaScreener server on http://{host}:{port}")
    if not api_only:
        typer.echo("Open your browser to start using the Web UI.")

    uvicorn.run(
        "metascreener.api.main:create_app",
        host=host,
        port=port,
        factory=True,
    )


@app.command()
def desktop(
    port: int = typer.Option(0, help="Port for local server (0 = auto-select free port)."),  # noqa: B008
    host: str = typer.Option("127.0.0.1", help="Host to bind local server."),  # noqa: B008
    width: int = typer.Option(1440, help="Desktop window width (px)."),  # noqa: B008
    height: int = typer.Option(960, help="Desktop window height (px)."),  # noqa: B008
    debug: bool = typer.Option(False, help="Enable pywebview debug mode."),  # noqa: B008
) -> None:
    """Launch the desktop shell (embedded Web UI window)."""
    from metascreener.desktop.launcher import launch_desktop  # noqa: PLC0415

    typer.echo("Starting MetaScreener desktop shell...")
    try:
        launch_desktop(
            host=host,
            port=port,
            width=width,
            height=height,
            debug=debug,
        )
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
