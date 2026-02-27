"""FastAPI application for MetaScreener 2.0 Web UI."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import metascreener

_WEB_DIR = Path(__file__).parent.parent / "web"
_TEMPLATES_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"


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

    # CORS — allow Vite dev server and same-origin requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routers
    from metascreener.api.routes.evaluation import router as evaluation_router
    from metascreener.api.routes.extraction import router as extraction_router
    from metascreener.api.routes.quality import router as quality_router
    from metascreener.api.routes.screening import router as screening_router
    from metascreener.api.routes.settings import router as settings_router

    app.include_router(settings_router)
    app.include_router(screening_router)
    app.include_router(evaluation_router)
    app.include_router(extraction_router)
    app.include_router(quality_router)

    # Health check
    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Return server health status."""
        return {"status": "ok", "version": metascreener.__version__}

    # Static files (CSS, JS, images)
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Jinja2 templates
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    version = metascreener.__version__

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        """Serve the dashboard page."""
        return templates.TemplateResponse(
            "index.html", {"request": request, "active": "home", "version": version}
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        """Serve the settings page."""
        return templates.TemplateResponse(
            "settings.html", {"request": request, "active": "settings", "version": version}
        )

    @app.get("/screening", response_class=HTMLResponse)
    async def screening_page(request: Request) -> HTMLResponse:
        """Serve the screening page."""
        return templates.TemplateResponse(
            "screening.html", {"request": request, "active": "screening", "version": version}
        )

    @app.get("/evaluation", response_class=HTMLResponse)
    async def evaluation_page(request: Request) -> HTMLResponse:
        """Serve the evaluation page."""
        return templates.TemplateResponse(
            "evaluation.html", {"request": request, "active": "evaluation", "version": version}
        )

    @app.get("/extraction", response_class=HTMLResponse)
    async def extraction_page(request: Request) -> HTMLResponse:
        """Serve the extraction page."""
        return templates.TemplateResponse(
            "extraction.html", {"request": request, "active": "extraction", "version": version}
        )

    @app.get("/quality", response_class=HTMLResponse)
    async def quality_page(request: Request) -> HTMLResponse:
        """Serve the quality assessment page."""
        return templates.TemplateResponse(
            "quality.html", {"request": request, "active": "quality", "version": version}
        )

    return app
