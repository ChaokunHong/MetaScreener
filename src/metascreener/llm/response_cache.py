"""In-memory + optional disk response cache for LLM calls.

Caches raw responses keyed by (model_id, prompt_hash) to avoid
redundant API calls. Uses LRU eviction to bound memory usage.

Disk persistence (SQLite) can be enabled via ``enable_disk_cache(path)``
so that cached responses survive process restarts.
"""
from __future__ import annotations

import sqlite3
from collections import OrderedDict
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Sized to comfortably hold an entire benchmark run's prompt set
# (4 models × ~25k records ≈ 100k entries) without evicting hot data.
# Each entry is a small JSON string (~1-2 KB), so 200k entries ≈ 400 MB
# resident memory at most — acceptable for the benchmark host.
_MAX_CACHE_SIZE = 200_000
_EVICT_FRACTION = 0.2  # Remove 20% when full

_cache: OrderedDict[tuple[str, str], str] = OrderedDict()
_hits = 0
_misses = 0

# --- Disk cache (SQLite) ---
_db_conn: sqlite3.Connection | None = None


def enable_disk_cache(path: str | Path) -> int:
    """Enable SQLite disk cache at *path*. Pre-loads into memory cache.

    Args:
        path: Path to the SQLite database file (created if absent).

    Returns:
        Number of entries loaded from disk into memory.
    """
    global _db_conn
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _db_conn = sqlite3.connect(str(path))
    _db_conn.execute(
        "CREATE TABLE IF NOT EXISTS cache "
        "(model_id TEXT, prompt_hash TEXT, response TEXT, "
        "PRIMARY KEY (model_id, prompt_hash))"
    )
    _db_conn.commit()

    # Pre-load disk entries into memory
    rows = _db_conn.execute("SELECT model_id, prompt_hash, response FROM cache").fetchall()
    loaded = 0
    for model_id, prompt_hash, response in rows:
        key = (model_id, prompt_hash)
        if key not in _cache:
            _cache[key] = response
            loaded += 1
    logger.info("disk_cache_loaded", path=str(path), entries=loaded)
    return loaded


def get_cached(model_id: str, prompt_hash: str) -> str | None:
    """Look up a cached response (memory first, then disk fallback).

    On memory miss, falls back to the SQLite disk cache (if enabled) and
    repopulates the in-memory LRU. Without this fallback, entries
    evicted from memory by ``put_cached``'s LRU policy would be
    re-fetched from the LLM API even though they exist on disk —
    causing every benchmark config beyond the first to incur full
    API costs again.
    """
    global _hits, _misses
    key = (model_id, prompt_hash)
    result = _cache.get(key)
    if result is not None:
        _hits += 1
        _cache.move_to_end(key)  # Mark as recently used
        return result

    # Memory miss — fall back to disk before declaring it a real miss
    if _db_conn is not None:
        row = _db_conn.execute(
            "SELECT response FROM cache WHERE model_id = ? AND prompt_hash = ?",
            (model_id, prompt_hash),
        ).fetchone()
        if row is not None:
            _hits += 1
            response = row[0]
            # Repopulate the in-memory LRU (without re-persisting to disk)
            _cache[key] = response
            _cache.move_to_end(key)
            if len(_cache) > _MAX_CACHE_SIZE:
                n_evict = int(_MAX_CACHE_SIZE * _EVICT_FRACTION)
                for _ in range(n_evict):
                    _cache.popitem(last=False)
            return response

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

    # Persist to disk if enabled
    if _db_conn is not None:
        _db_conn.execute(
            "INSERT OR REPLACE INTO cache (model_id, prompt_hash, response) "
            "VALUES (?, ?, ?)",
            (model_id, prompt_hash, response),
        )
        _db_conn.commit()


def evict_cached(model_id: str, prompt_hash: str) -> bool:
    """Remove a specific cached response (e.g. after parse failure)."""
    key = (model_id, prompt_hash)
    if key in _cache:
        del _cache[key]
        if _db_conn is not None:
            _db_conn.execute(
                "DELETE FROM cache WHERE model_id = ? AND prompt_hash = ?",
                (model_id, prompt_hash),
            )
            _db_conn.commit()
        return True
    return False


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
    if _db_conn is not None:
        _db_conn.execute("DELETE FROM cache")
        _db_conn.commit()
    return count
