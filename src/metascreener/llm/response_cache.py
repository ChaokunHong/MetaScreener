"""In-memory response cache for LLM calls.

Caches raw responses keyed by (model_id, prompt_hash) to avoid
redundant API calls when the same paper is screened with the same
criteria. Cache is per-process and cleared on restart.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# (model_id, prompt_hash) → raw_response_text
_cache: dict[tuple[str, str], str] = {}
_hits = 0
_misses = 0


def get_cached(model_id: str, prompt_hash: str) -> str | None:
    """Look up a cached response.

    Args:
        model_id: Model identifier.
        prompt_hash: SHA256 hash of the prompt.

    Returns:
        Cached raw response string, or None on miss.
    """
    global _hits, _misses
    key = (model_id, prompt_hash)
    result = _cache.get(key)
    if result is not None:
        _hits += 1
        logger.debug("cache_hit", model_id=model_id, prompt_hash=prompt_hash[:8])
        return result
    _misses += 1
    return None


def put_cached(model_id: str, prompt_hash: str, response: str) -> None:
    """Store a response in the cache.

    Args:
        model_id: Model identifier.
        prompt_hash: SHA256 hash of the prompt.
        response: Raw response text from the LLM.
    """
    _cache[(model_id, prompt_hash)] = response


def cache_stats() -> dict[str, int]:
    """Return cache hit/miss statistics.

    Returns:
        Dict with hits, misses, and size counts.
    """
    return {"hits": _hits, "misses": _misses, "size": len(_cache)}


def clear_cache() -> int:
    """Clear all cached responses.

    Returns:
        Number of entries cleared.
    """
    global _hits, _misses
    count = len(_cache)
    _cache.clear()
    _hits = 0
    _misses = 0
    return count
