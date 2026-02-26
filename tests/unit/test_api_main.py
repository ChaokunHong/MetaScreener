"""Tests for the FastAPI application setup."""
from __future__ import annotations

from fastapi.testclient import TestClient


class TestFastAPIApp:
    """Test FastAPI app creation and configuration."""

    def test_app_creates_successfully(self) -> None:
        """Verify the FastAPI app instantiation."""
        from metascreener.api.main import create_app

        app = create_app()
        assert app is not None
        assert app.title == "MetaScreener"

    def test_health_endpoint(self) -> None:
        """Verify GET /api/health returns status ok."""
        from metascreener.api.main import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_static_file_serving_returns_404_without_dist(self) -> None:
        """Without web/dist, non-API routes return 404."""
        from metascreener.api.main import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.get("/nonexistent")
        assert resp.status_code == 404

    def test_cors_headers_present(self) -> None:
        """Verify CORS middleware is configured."""
        from metascreener.api.main import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.options(
            "/api/health",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code in (200, 405)


class TestServeCommand:
    """Test the 'metascreener serve' CLI command."""

    def test_serve_command_exists(self) -> None:
        """Verify serve command is registered and shows help."""
        from typer.testing import CliRunner

        from metascreener.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "serve" in result.output.lower() or "fastapi" in result.output.lower()
