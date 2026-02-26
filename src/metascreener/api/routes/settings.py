"""Settings management API routes."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter

from metascreener.api.deps import get_config
from metascreener.api.schemas import (
    ModelInfo,
    SettingsResponse,
    SettingsUpdate,
    TestKeyRequest,
    TestKeyResponse,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _config_path() -> Path:
    """Get path to user settings file.

    Returns:
        Path to ~/.metascreener/config.yaml.
    """
    p = Path.home() / ".metascreener" / "config.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_user_settings() -> dict[str, Any]:
    """Load user settings from disk.

    Returns:
        Settings dictionary, or empty dict if file doesn't exist.
    """
    p = _config_path()
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_user_settings(data: dict[str, Any]) -> None:
    """Save user settings to disk.

    Args:
        data: Settings dictionary to persist.
    """
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


@router.get("", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """Get current settings."""
    user = _load_user_settings()
    return SettingsResponse(**user)


@router.put("")
async def update_settings(update: SettingsUpdate) -> dict[str, str]:
    """Update settings and persist to disk.

    Args:
        update: Partial settings update payload.

    Returns:
        Status acknowledgement dict.
    """
    current = _load_user_settings()
    if update.api_keys is not None:
        current["api_keys"] = update.api_keys.model_dump()
    if update.inference is not None:
        current["inference"] = update.inference.model_dump()
    if update.enabled_models is not None:
        current["enabled_models"] = update.enabled_models
    _save_user_settings(current)
    return {"status": "ok"}


@router.get("/models", response_model=list[ModelInfo])
async def list_models() -> list[ModelInfo]:
    """List available LLM models from configuration."""
    try:
        config = get_config()
    except FileNotFoundError:
        return []
    return [
        ModelInfo(
            model_id=key,
            name=entry.name,
            provider=entry.provider,
            version=entry.version,
            license=entry.license_,
        )
        for key, entry in config.models.items()
    ]


@router.post("/test-key", response_model=TestKeyResponse)
async def test_api_key(req: TestKeyRequest) -> TestKeyResponse:
    """Test an API key for basic validity.

    Args:
        req: Test key request with provider and api_key.

    Returns:
        Validation result with valid flag and message.
    """
    if not req.api_key or not req.api_key.strip():
        return TestKeyResponse(valid=False, message="API key is empty")
    if len(req.api_key) < 10:
        return TestKeyResponse(valid=False, message="Key too short")
    return TestKeyResponse(valid=True, message="Key format looks valid")
