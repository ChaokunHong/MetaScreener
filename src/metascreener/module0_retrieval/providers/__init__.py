"""Search provider registry and factory."""
from __future__ import annotations

from metascreener.module0_retrieval.providers.base import SearchProvider

_PROVIDER_MAP: dict[str, type[SearchProvider]] = {}


def _lazy_map() -> dict[str, type[SearchProvider]]:
    """Build provider map lazily to avoid heavy imports at package load."""
    if _PROVIDER_MAP:
        return _PROVIDER_MAP
    from metascreener.module0_retrieval.providers.europepmc import (
        EuropePMCProvider,  # noqa: PLC0415
    )
    from metascreener.module0_retrieval.providers.openalex import OpenAlexProvider  # noqa: PLC0415
    from metascreener.module0_retrieval.providers.pubmed import PubMedProvider  # noqa: PLC0415
    from metascreener.module0_retrieval.providers.scopus import ScopusProvider  # noqa: PLC0415
    from metascreener.module0_retrieval.providers.semantic_scholar import (
        SemanticScholarProvider,  # noqa: PLC0415
    )

    _PROVIDER_MAP.update(
        {
            "pubmed": PubMedProvider,
            "openalex": OpenAlexProvider,
            "europepmc": EuropePMCProvider,
            "scopus": ScopusProvider,
            "semantic_scholar": SemanticScholarProvider,
        }
    )
    return _PROVIDER_MAP


def create_provider(name: str, config: dict) -> SearchProvider:
    """Factory function to create a provider by name.

    Args:
        name: Provider identifier, e.g. ``"pubmed"``, ``"openalex"``.
        config: Provider-specific keyword arguments passed to the constructor.

    Returns:
        Configured :class:`SearchProvider` instance.

    Raises:
        ValueError: If *name* is not a recognised provider.
    """
    registry = _lazy_map()
    lower = name.lower()
    if lower not in registry:
        valid = ", ".join(sorted(registry))
        raise ValueError(f"Unknown provider '{name}'. Valid options: {valid}")
    return registry[lower](**config)


__all__ = ["SearchProvider", "create_provider"]
