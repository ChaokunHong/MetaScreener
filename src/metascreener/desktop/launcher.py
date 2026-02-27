"""Desktop shell launcher (embedded Web UI via pywebview)."""
from __future__ import annotations

import socket
import time
from pathlib import Path
from threading import Thread
from types import ModuleType
from typing import cast

import httpx


def _resolve_port(host: str, port: int) -> int:
    """Resolve a port number, allowing ``0`` to mean 'choose a free port'."""
    if port > 0:
        return port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_for_health(url: str, timeout_s: float = 15.0) -> None:
    """Block until the FastAPI health endpoint responds or timeout."""
    deadline = time.monotonic() + timeout_s
    last_error: str | None = None

    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=1.5)
            if resp.status_code == 200:
                return
            last_error = f"HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.15)

    msg = f"Timed out waiting for local server at {url}"
    if last_error:
        msg = f"{msg} ({last_error})"
    raise RuntimeError(msg)


def _import_webview() -> ModuleType:
    """Import pywebview lazily so core installs don't require desktop deps."""
    try:
        import webview  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Desktop UI requires optional dependency 'pywebview'. "
            "Install with: uv pip install 'metascreener[desktop]'"
        ) from exc
    return cast(ModuleType, webview)


def _ensure_built_frontend() -> None:
    """Fail fast if the bundled React build is missing."""
    dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
    index_file = dist_dir / "index.html"
    if not index_file.is_file():
        raise RuntimeError(
            "Web UI bundle not found. Build frontend first (e.g. run 'npm run build' in frontend/)."
        )


def launch_desktop(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    width: int = 1440,
    height: int = 960,
    title: str = "MetaScreener",
    debug: bool = False,
) -> None:
    """Launch an embedded desktop window backed by the local FastAPI server."""
    _ensure_built_frontend()
    webview = _import_webview()

    import uvicorn  # noqa: PLC0415

    from metascreener.api.main import create_app  # noqa: PLC0415

    resolved_port = _resolve_port(host, port)
    app = create_app()
    config = uvicorn.Config(app, host=host, port=resolved_port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # type: ignore[attr-defined]

    thread = Thread(target=server.run, daemon=True, name="metascreener-desktop-server")
    thread.start()

    base_url = f"http://{host}:{resolved_port}"
    health_url = f"{base_url}/api/health"

    try:
        _wait_for_health(health_url)
        webview.create_window(
            title,
            url=base_url,
            width=width,
            height=height,
            min_size=(1000, 700),
            resizable=True,
        )
        webview.start(debug=debug)
    finally:
        server.should_exit = True
        if thread.is_alive():
            thread.join(timeout=5.0)

