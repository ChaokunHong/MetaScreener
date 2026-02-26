"""FastAPI application for MetaScreener 2.0 Web UI."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import metascreener


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="MetaScreener",
        version=metascreener.__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # CORS for local dev (Vite on :5173)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Return server health status."""
        return {"status": "ok", "version": metascreener.__version__}

    # Serve React static files if dist/ exists
    dist_dir = Path(__file__).parent.parent / "web" / "dist"
    if dist_dir.is_dir():
        # Serve static assets (js, css, images)
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # SPA fallback: serve index.html for all non-API routes
        @app.get("/{path:path}")
        async def spa_fallback(path: str) -> FileResponse | JSONResponse:
            """Serve React SPA for non-API routes."""
            file_path = dist_dir / path
            if file_path.is_file():
                return FileResponse(str(file_path))
            index = dist_dir / "index.html"
            if index.is_file():
                return FileResponse(str(index))
            return JSONResponse({"error": "not found"}, status_code=404)

    return app
