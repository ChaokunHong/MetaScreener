"""Tests for the settings API routes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestSettingsAPI:
    """Test settings CRUD endpoints."""

    def _client(self) -> TestClient:
        """Create a test client for the FastAPI app.

        Returns:
            TestClient wired to the MetaScreener FastAPI app.
        """
        from metascreener.api.main import create_app

        return TestClient(create_app())

    def test_get_settings_returns_defaults(self, tmp_path: Path) -> None:
        """GET /api/settings returns default settings when no config exists."""
        with patch(
            "metascreener.api.routes.settings._config_path",
            return_value=tmp_path / "config.yaml",
        ):
            client = self._client()
            resp = client.get("/api/settings")
            assert resp.status_code == 200
            data = resp.json()
            assert "api_keys" in data
            assert "inference" in data
            assert data["inference"]["temperature"] == 0.0
            assert data["inference"]["seed"] == 42

    def test_put_settings_updates_api_key(self, tmp_path: Path) -> None:
        """PUT /api/settings persists changes to disk."""
        with patch(
            "metascreener.api.routes.settings._config_path",
            return_value=tmp_path / "config.yaml",
        ):
            client = self._client()
            resp = client.put(
                "/api/settings",
                json={"api_keys": {"openrouter": "sk-test-123456789"}},
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}
            assert (tmp_path / "config.yaml").exists()

    def test_put_then_get_roundtrip(self, tmp_path: Path) -> None:
        """PUT then GET returns the persisted settings."""
        with patch(
            "metascreener.api.routes.settings._config_path",
            return_value=tmp_path / "config.yaml",
        ):
            client = self._client()
            client.put(
                "/api/settings",
                json={
                    "api_keys": {"openrouter": "sk-roundtrip-key"},
                    "inference": {"temperature": 0.0, "seed": 99},
                },
            )
            resp = client.get("/api/settings")
            assert resp.status_code == 200
            data = resp.json()
            assert data["api_keys"]["openrouter"] == "sk-roundtrip-key"
            assert data["inference"]["seed"] == 99

    def test_put_partial_update_preserves_other_fields(self, tmp_path: Path) -> None:
        """PUT with only api_keys preserves existing inference settings."""
        with patch(
            "metascreener.api.routes.settings._config_path",
            return_value=tmp_path / "config.yaml",
        ):
            client = self._client()
            # First set inference
            client.put(
                "/api/settings",
                json={"inference": {"seed": 77}},
            )
            # Then update only api_keys
            client.put(
                "/api/settings",
                json={"api_keys": {"together": "tok-abc"}},
            )
            resp = client.get("/api/settings")
            data = resp.json()
            assert data["inference"]["seed"] == 77
            assert data["api_keys"]["together"] == "tok-abc"

    def test_get_models_returns_model_list(self) -> None:
        """GET /api/settings/models returns available models."""
        client = self._client()
        resp = client.get("/api/settings/models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Verify expected fields on the first model
        model = data[0]
        assert "model_id" in model
        assert "name" in model
        assert "provider" in model
        assert "version" in model
        assert "license" in model

    def test_get_models_contains_known_models(self) -> None:
        """GET /api/settings/models includes the four configured models."""
        client = self._client()
        resp = client.get("/api/settings/models")
        model_ids = {m["model_id"] for m in resp.json()}
        assert "qwen3" in model_ids
        assert "deepseek" in model_ids

    def test_test_key_empty_returns_invalid(self) -> None:
        """POST /api/settings/test-key with empty key returns invalid."""
        client = self._client()
        resp = client.post(
            "/api/settings/test-key",
            json={"provider": "openrouter", "api_key": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "empty" in data["message"].lower()

    def test_test_key_short_returns_invalid(self) -> None:
        """POST /api/settings/test-key with short key returns invalid."""
        client = self._client()
        resp = client.post(
            "/api/settings/test-key",
            json={"provider": "openrouter", "api_key": "abc"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "short" in data["message"].lower()

    def test_test_key_valid_format(self) -> None:
        """POST /api/settings/test-key with plausible key returns valid."""
        client = self._client()
        resp = client.post(
            "/api/settings/test-key",
            json={"provider": "openrouter", "api_key": "sk-or-v1-abcdefghijklmnop"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_put_enabled_models(self, tmp_path: Path) -> None:
        """PUT /api/settings with enabled_models persists model list."""
        with patch(
            "metascreener.api.routes.settings._config_path",
            return_value=tmp_path / "config.yaml",
        ):
            client = self._client()
            resp = client.put(
                "/api/settings",
                json={"enabled_models": ["qwen3", "deepseek"]},
            )
            assert resp.status_code == 200
            resp = client.get("/api/settings")
            data = resp.json()
            assert data["enabled_models"] == ["qwen3", "deepseek"]
