"""In-memory response cache for LLM calls.

Caches raw responses keyed by (model_id, prompt_hash) to avoid
redundant API calls. Uses LRU eviction to bound memory usage.
"""
from __future__ import annotations

from collections import OrderedDict

import structlog

logger = structlog.get_logger(__name__)

_MAX_CACHE_SIZE = 5000
_EVICT_FRACTION = 0.2  # Remove 20% when full

_cache: OrderedDict[tuple[str, str], str] = OrderedDict()
_hits = 0
_misses = 0


def get_cached(model_id: str, prompt_hash: str) -> str | None:
    """Look up a cached response (moves to end for LRU)."""
    global _hits, _misses
    key = (model_id, prompt_hash)
    result = _cache.get(key)
    if result is not None:
        _hits += 1
        _cache.move_to_end(key)  # Mark as recently used
        return result
    _misses += 1
    return None


def put_cached(model_id: str, prompt_hash: str, response: str) -> None:
    """Store a response, evicting oldest entries if cache is full."""
    key = (model_id, prompt_hash)
    _cache[key] = response
    _cache.move_to_end(key)
    if len(_cache) > _MAX_CACHE_SIZE:
        n_evict = int(_MAX_CACHE_SIZE * _EVICT_FRACTION)
        for _ in range(n_evict):
            _cache.popitem(last=False)  # Remove oldest
        logger.debug("cache_eviction", evicted=n_evict, remaining=len(_cache))


def cache_stats() -> dict[str, int]:
    """Return cache hit/miss statistics."""
    return {"hits": _hits, "misses": _misses, "size": len(_cache)}


def clear_cache() -> int:
    """Clear all cached responses."""
    global _hits, _misses
    count = len(_cache)
    _cache.clear()
    _hits = 0
    _misses = 0
    return count
