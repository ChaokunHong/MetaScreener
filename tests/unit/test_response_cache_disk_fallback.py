"""Tests for the LLM response cache disk fallback (Bug #4 reproducer + fix).

Without disk fallback, entries evicted from the in-memory LRU by
``put_cached`` would be re-fetched from the LLM API even though they
exist on disk. During the 2026-04-08 benchmark this caused every
config beyond a0/a1 to incur full API costs again, blowing up runtime
from ~5h to ~60h.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from metascreener.llm import response_cache


@pytest.fixture(autouse=True)
def _isolate_module_state(tmp_path: Path) -> Iterator[None]:
    """Reset the response_cache module-level state for each test.

    The cache is a module-level singleton, so tests must clean up
    after themselves to remain hermetic.
    """
    response_cache._cache.clear()
    response_cache._hits = 0
    response_cache._misses = 0
    if response_cache._db_conn is not None:
        try:
            response_cache._db_conn.close()
        except Exception:
            pass
        response_cache._db_conn = None
    yield
    response_cache._cache.clear()
    response_cache._hits = 0
    response_cache._misses = 0
    if response_cache._db_conn is not None:
        try:
            response_cache._db_conn.close()
        except Exception:
            pass
        response_cache._db_conn = None


def test_get_cached_falls_back_to_disk_after_eviction(tmp_path: Path) -> None:
    """Bug #4 reproducer: an entry evicted from memory but present on disk
    must be re-served from disk on the next get_cached call."""
    db_path = tmp_path / "cache.db"
    response_cache.enable_disk_cache(db_path)

    # Store a response — goes to both memory and disk
    response_cache.put_cached("model-a", "hash-1", '{"decision": "INCLUDE"}')

    # Simulate LRU eviction (e.g. cache pressure from many subsequent puts)
    response_cache._cache.clear()
    assert ("model-a", "hash-1") not in response_cache._cache

    # Disk fallback should re-serve it
    result = response_cache.get_cached("model-a", "hash-1")
    assert result == '{"decision": "INCLUDE"}'

    # And repopulate the in-memory LRU
    assert ("model-a", "hash-1") in response_cache._cache


def test_get_cached_real_miss_returns_none(tmp_path: Path) -> None:
    """A genuinely-missing key must still return None (not crash on disk)."""
    db_path = tmp_path / "cache.db"
    response_cache.enable_disk_cache(db_path)

    result = response_cache.get_cached("model-a", "never-stored")
    assert result is None
    assert response_cache._misses == 1


def test_get_cached_no_disk_cache_returns_none(tmp_path: Path) -> None:
    """Without disk cache enabled, behavior degrades gracefully."""
    # _db_conn left as None by fixture
    response_cache.put_cached("model-a", "hash-1", "value")
    response_cache._cache.clear()

    result = response_cache.get_cached("model-a", "hash-1")
    assert result is None  # No disk fallback available


def test_disk_fallback_persists_after_module_restart(tmp_path: Path) -> None:
    """End-to-end: simulate a process restart by closing and re-enabling
    the disk cache. All previously stored entries must remain available."""
    db_path = tmp_path / "cache.db"

    # Session 1: write 3 entries
    response_cache.enable_disk_cache(db_path)
    for i in range(3):
        response_cache.put_cached(f"model-{i}", f"hash-{i}", f"resp-{i}")
    response_cache._db_conn.close()
    response_cache._db_conn = None
    response_cache._cache.clear()

    # Session 2: re-enable, lookups must succeed
    n_loaded = response_cache.enable_disk_cache(db_path)
    assert n_loaded == 3
    for i in range(3):
        assert response_cache.get_cached(f"model-{i}", f"hash-{i}") == f"resp-{i}"


def test_eviction_preserves_disk_copy(tmp_path: Path) -> None:
    """When LRU eviction kicks in, the disk copy must remain intact so
    that subsequent get_cached calls can resurrect the entry.

    This is the exact scenario that broke Moran_2021/a2: a1 cached
    20k+ entries, the LRU evicted ~76% of them, and a2 had no way to
    get them back without paying for new API calls.
    """
    db_path = tmp_path / "cache.db"
    response_cache.enable_disk_cache(db_path)

    # Force aggressive eviction by setting a tiny cap
    original_max = response_cache._MAX_CACHE_SIZE
    response_cache._MAX_CACHE_SIZE = 10
    try:
        # Write 25 entries — far past the cap, triggering LRU evictions
        for i in range(25):
            response_cache.put_cached("model", f"hash-{i:03d}", f"resp-{i}")

        # In-memory cache holds at most _MAX_CACHE_SIZE entries
        assert len(response_cache._cache) <= response_cache._MAX_CACHE_SIZE

        # All 25 entries are still on disk
        conn = sqlite3.connect(str(db_path))
        n_disk = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        conn.close()
        assert n_disk == 25

        # Every single one must still be retrievable via get_cached
        for i in range(25):
            result = response_cache.get_cached("model", f"hash-{i:03d}")
            assert result == f"resp-{i}", f"entry {i} lost after eviction"
    finally:
        response_cache._MAX_CACHE_SIZE = original_max
