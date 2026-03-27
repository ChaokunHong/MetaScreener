"""Tests for PDFDownloader (cascade manager)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metascreener.module0_retrieval.downloader.cache import DownloadCache
from metascreener.module0_retrieval.downloader.manager import PDFDownloader, build_filename
from metascreener.module0_retrieval.downloader.sources import PDFSource
from metascreener.module0_retrieval.downloader.validator import PDFValidator, ValidationResult
from metascreener.module0_retrieval.models import DownloadResult, RawRecord

_PDF_BYTES = b"%PDF-1.4 " + b"x" * 4096


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(**kwargs: object) -> RawRecord:
    kwargs.setdefault("title", "A Study")
    kwargs.setdefault("source_db", "pubmed")
    return RawRecord(**kwargs)  # type: ignore[arg-type]


def _make_source(name: str, priority: int, *, succeed: bool = True) -> PDFSource:
    """Build a mock PDFSource that either succeeds or returns None."""

    class _MockSource(PDFSource):
        @property
        def name(self) -> str:
            return name

        @property
        def priority(self) -> int:
            return priority

        async def try_download(
            self, record: RawRecord, output_dir: Path, client: object
        ) -> str | None:
            if not succeed:
                return None
            dest = output_dir / f"{name}_{record.record_id[:6]}.pdf"
            dest.write_bytes(_PDF_BYTES)
            return str(dest)

    return _MockSource()


def _passing_validator() -> PDFValidator:
    v = MagicMock(spec=PDFValidator)
    v.validate = MagicMock(return_value=ValidationResult(valid=True, page_count=5, has_text=True))
    return v


def _failing_validator() -> PDFValidator:
    v = MagicMock(spec=PDFValidator)
    v.validate = MagicMock(return_value=ValidationResult(valid=False, error="bad PDF"))
    return v


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPDFDownloaderCacheHit:
    async def test_cache_hit_skips_download(self, tmp_path: Path) -> None:
        record = _rec(pmid="111")

        cache = MagicMock(spec=DownloadCache)
        cache.get = AsyncMock(
            return_value={
                "success": True,
                "pdf_path": "/cached/path.pdf",
                "source": "europepmc",
            }
        )
        cache.set = AsyncMock()

        source = _make_source("src_a", 10, succeed=True)
        called_flag = {"called": False}

        original_try = source.try_download

        async def spy_try(*args: object, **kwargs: object) -> object:
            called_flag["called"] = True
            return await original_try(*args, **kwargs)

        source.try_download = spy_try  # type: ignore[method-assign]

        downloader = PDFDownloader(
            sources=[source],
            cache=cache,
            validator=_passing_validator(),
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            results = await downloader.download_batch([record], tmp_path)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].pdf_path == "/cached/path.pdf"
        assert results[0].source_used == "europepmc"
        # The actual source should NOT have been called
        assert called_flag["called"] is False


class TestPDFDownloaderCascadeFallback:
    async def test_first_source_fails_second_succeeds(self, tmp_path: Path) -> None:
        record = _rec(pmid="222")
        source_fail = _make_source("src_fail", 10, succeed=False)
        source_ok = _make_source("src_ok", 20, succeed=True)

        downloader = PDFDownloader(
            sources=[source_fail, source_ok],
            cache=None,
            validator=_passing_validator(),
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            results = await downloader.download_batch([record], tmp_path)

        assert len(results) == 1
        r = results[0]
        assert r.success is True
        assert r.source_used == "src_ok"
        # Both sources should have been attempted
        attempt_names = [a["source"] for a in r.attempts]
        assert "src_fail" in attempt_names
        assert "src_ok" in attempt_names


class TestPDFDownloaderAllFail:
    async def test_all_sources_fail_returns_failure(self, tmp_path: Path) -> None:
        record = _rec(pmid="333")
        sources = [
            _make_source("s1", 10, succeed=False),
            _make_source("s2", 20, succeed=False),
        ]

        downloader = PDFDownloader(
            sources=sources,
            cache=None,
            validator=_passing_validator(),
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            results = await downloader.download_batch([record], tmp_path)

        assert results[0].success is False
        assert results[0].pdf_path is None
        assert results[0].source_used is None


class TestPDFDownloaderEmptyBatch:
    async def test_empty_batch_returns_empty_list(self, tmp_path: Path) -> None:
        downloader = PDFDownloader(sources=[], cache=None, validator=_passing_validator())
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            results = await downloader.download_batch([], tmp_path)
        assert results == []


class TestPDFDownloaderValidationFailure:
    async def test_invalid_pdf_not_counted_as_success(self, tmp_path: Path) -> None:
        record = _rec(pmid="444")
        source_ok = _make_source("src_ok", 10, succeed=True)

        downloader = PDFDownloader(
            sources=[source_ok],
            cache=None,
            validator=_failing_validator(),
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            results = await downloader.download_batch([record], tmp_path)

        assert results[0].success is False


# ---------------------------------------------------------------------------
# build_filename tests
# ---------------------------------------------------------------------------


class TestBuildFilename:
    def test_pmid_preferred(self) -> None:
        r = _rec(pmid="9999", pmcid="PMC888", doi="10.1/x")
        assert build_filename(r) == "PMID_9999.pdf"

    def test_pmcid_second(self) -> None:
        r = _rec(pmcid="888", doi="10.1/x")
        assert build_filename(r) == "PMCID_PMC888.pdf"

    def test_doi_third(self) -> None:
        r = _rec(doi="10.1000/ab.cd")
        name = build_filename(r)
        assert name.startswith("DOI_")
        assert name.endswith(".pdf")

    def test_title_hash_fallback(self) -> None:
        r = _rec(title="Unique study with no IDs")
        name = build_filename(r)
        assert name.startswith("TITLE_")
        assert name.endswith(".pdf")
