"""Tests for DownloadCache."""
from __future__ import annotations

from pathlib import Path

import pytest

from metascreener.module0_retrieval.downloader.cache import DownloadCache


class TestDownloadCacheSetGet:
    """Basic set/get/miss behaviour."""

    async def test_set_and_get_success(self, tmp_path: Path) -> None:
        cache = DownloadCache(tmp_path / "dl.db")
        await cache.initialize()
        try:
            await cache.set("rec1", True, "/tmp/rec1.pdf", "europepmc")
            result = await cache.get("rec1")
            assert result is not None
            assert result["success"] is True
            assert result["pdf_path"] == "/tmp/rec1.pdf"
            assert result["source"] == "europepmc"
        finally:
            await cache.close()

    async def test_get_missing_record_returns_none(self, tmp_path: Path) -> None:
        cache = DownloadCache(tmp_path / "dl.db")
        await cache.initialize()
        try:
            result = await cache.get("does_not_exist")
            assert result is None
        finally:
            await cache.close()

    async def test_overwrite_updates_entry(self, tmp_path: Path) -> None:
        cache = DownloadCache(tmp_path / "dl.db")
        await cache.initialize()
        try:
            await cache.set("rec2", False, None, None)
            first = await cache.get("rec2")
            assert first is not None
            assert first["success"] is False

            # Overwrite with success
            await cache.set("rec2", True, "/tmp/rec2.pdf", "unpaywall")
            second = await cache.get("rec2")
            assert second is not None
            assert second["success"] is True
            assert second["pdf_path"] == "/tmp/rec2.pdf"
            assert second["source"] == "unpaywall"
        finally:
            await cache.close()

    async def test_failed_entry_stored_correctly(self, tmp_path: Path) -> None:
        cache = DownloadCache(tmp_path / "dl.db")
        await cache.initialize()
        try:
            await cache.set("rec3", False, None, None)
            result = await cache.get("rec3")
            assert result is not None
            assert result["success"] is False
            assert result["pdf_path"] is None
            assert result["source"] is None
        finally:
            await cache.close()

    async def test_initialize_is_idempotent(self, tmp_path: Path) -> None:
        """Calling initialize() twice should not raise."""
        cache = DownloadCache(tmp_path / "dl.db")
        await cache.initialize()
        await cache.initialize()  # second call must be safe
        await cache.close()
