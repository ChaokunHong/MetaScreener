"""Pydantic schemas for API request/response models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class APIKeysConfig(BaseModel):
    """API key configuration for LLM providers.

    Attributes:
        openrouter: OpenRouter API key.
        together: Together AI API key.
    """

    openrouter: str = ""
    together: str = ""


class InferenceSettings(BaseModel):
    """Inference parameter configuration.

    Attributes:
        temperature: Sampling temperature (0.0 for deterministic).
        seed: Random seed for reproducibility.
        timeout_s: Timeout per LLM call in seconds.
        max_retries: Maximum retry attempts per call.
    """

    temperature: float = 0.0
    seed: int = 42
    timeout_s: float = 120.0
    max_retries: int = 3


class SettingsResponse(BaseModel):
    """Full settings response.

    Attributes:
        api_keys: API key configuration.
        inference: Inference parameter settings.
        enabled_models: List of enabled model identifiers.
    """

    api_keys: APIKeysConfig = Field(default_factory=APIKeysConfig)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    enabled_models: list[str] = Field(default_factory=list)


class SettingsUpdate(BaseModel):
    """Partial settings update request.

    Attributes:
        api_keys: Optional API key update.
        inference: Optional inference settings update.
        enabled_models: Optional list of enabled model identifiers.
    """

    api_keys: APIKeysConfig | None = None
    inference: InferenceSettings | None = None
    enabled_models: list[str] | None = None


class ModelInfo(BaseModel):
    """Model information for the model list endpoint.

    Attributes:
        model_id: Internal model identifier key.
        name: Full model name.
        provider: API provider name.
        version: Version date string.
        license: Model license identifier.
        enabled: Whether the model is currently enabled.
    """

    model_id: str
    name: str
    provider: str
    version: str
    license: str
    enabled: bool = True


class TestKeyRequest(BaseModel):
    """API key test request.

    Attributes:
        provider: LLM provider name.
        api_key: API key to validate.
    """

    provider: str
    api_key: str


class TestKeyResponse(BaseModel):
    """API key test response.

    Attributes:
        valid: Whether the key appears valid.
        message: Human-readable validation message.
    """

    valid: bool
    message: str
