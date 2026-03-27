"""Tests for individual PDFSource implementations.

All HTTP calls are mocked; no real network access occurs.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metascreener.module0_retrieval.downloader.sources import (
    DOIResolverSource,
    EuropePMCSource,
    OpenAlexDirectSource,
    PMCOASource,
    SemanticScholarSource,
    UnpaywallSource,
)
from metascreener.module0_retrieval.models import RawRecord

_PDF_BYTES = b"%PDF-1.4 " + b"x" * 4096


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(**kwargs: object) -> RawRecord:
    kwargs.setdefault("title", "Test Study")
    kwargs.setdefault("source_db", "pubmed")
    return RawRecord(**kwargs)  # type: ignore[arg-type]


def _make_streaming_client(content: bytes = _PDF_BYTES, status: int = 200) -> MagicMock:
    """Build an async HTTP client mock that streams *content* as one chunk."""

    async def _aiter(chunk_size: int = 65536):  # noqa: ANN001
        yield content

    resp = MagicMock()
    resp.status_code = status
    resp.aiter_bytes = _aiter

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=None)

    client = MagicMock()
    client.stream = MagicMock(return_value=cm)
    return client


def _make_json_client(payload: dict, status: int = 200) -> MagicMock:
    """Build an async HTTP client mock that returns *payload* as JSON."""
    resp = AsyncMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=payload)

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    return client


# ---------------------------------------------------------------------------
# OpenAlexDirectSource
# ---------------------------------------------------------------------------


class TestOpenAlexDirectSource:
    async def test_downloads_first_url(self, tmp_path: Path) -> None:
        record = _rec(pmid="12345", pdf_urls=["https://cdn.openalex.org/paper.pdf"])
        client = _make_streaming_client()
        source = OpenAlexDirectSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is not None
        assert Path(result).suffix == ".pdf"
        assert Path(result).read_bytes().startswith(b"%PDF")

    async def test_skips_when_no_urls(self, tmp_path: Path) -> None:
        record = _rec(pmid="12345", pdf_urls=[])
        client = _make_streaming_client()
        source = OpenAlexDirectSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is None

    async def test_returns_none_on_non_200(self, tmp_path: Path) -> None:
        record = _rec(pmid="12345", pdf_urls=["https://cdn.openalex.org/paper.pdf"])
        client = _make_streaming_client(status=403)
        source = OpenAlexDirectSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is None


# ---------------------------------------------------------------------------
# EuropePMCSource
# ---------------------------------------------------------------------------


class TestEuropePMCSource:
    async def test_downloads_with_pmcid(self, tmp_path: Path) -> None:
        record = _rec(pmcid="PMC1234567")
        client = _make_streaming_client()
        source = EuropePMCSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is not None
        assert "PMC1234567" in result

    async def test_auto_adds_pmc_prefix(self, tmp_path: Path) -> None:
        record = _rec(pmcid="1234567")  # no PMC prefix
        client = _make_streaming_client()
        source = EuropePMCSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is not None

    async def test_skips_when_no_pmcid(self, tmp_path: Path) -> None:
        record = _rec(doi="10.1000/test")
        client = _make_streaming_client()
        source = EuropePMCSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is None


# ---------------------------------------------------------------------------
# UnpaywallSource
# ---------------------------------------------------------------------------


class TestUnpaywallSource:
    async def test_downloads_via_unpaywall(self, tmp_path: Path) -> None:
        record = _rec(doi="10.1000/test")
        # JSON client for the API call
        api_client = _make_json_client(
            {"best_oa_location": {"url_for_pdf": "https://oa.example.com/paper.pdf"}}
        )
        # We also need to mock the streaming call for the actual PDF download
        stream_client = _make_streaming_client()

        source = UnpaywallSource(email="test@example.com")

        # Patch _stream_to_file to return a fake path after the API call
        async def fake_stream(url: str, dest: Path, client: object, **kw: object) -> str | None:
            dest.write_bytes(_PDF_BYTES)
            return str(dest)

        source._stream_to_file = fake_stream  # type: ignore[method-assign]

        # Attach streaming client's get method
        api_client.stream = stream_client.stream
        result = await source.try_download(record, tmp_path, api_client)
        assert result is not None

    async def test_skips_when_no_doi(self, tmp_path: Path) -> None:
        record = _rec(pmid="111")
        client = MagicMock()
        source = UnpaywallSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is None

    async def test_returns_none_when_no_pdf_url_in_response(self, tmp_path: Path) -> None:
        record = _rec(doi="10.1000/closed")
        api_client = _make_json_client({"best_oa_location": {"url_for_pdf": None}})
        source = UnpaywallSource()
        result = await source.try_download(record, tmp_path, api_client)
        assert result is None


# ---------------------------------------------------------------------------
# SemanticScholarSource
# ---------------------------------------------------------------------------


class TestSemanticScholarSource:
    async def test_downloads_s2_pdf_url(self, tmp_path: Path) -> None:
        record = _rec(
            source_db="semantic_scholar",
            s2_id="s2abc",
            pdf_urls=["https://pdfs.semanticscholar.org/paper.pdf"],
        )
        client = _make_streaming_client()
        source = SemanticScholarSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is not None

    async def test_skips_non_s2_records(self, tmp_path: Path) -> None:
        record = _rec(
            source_db="pubmed",
            pdf_urls=["https://pdfs.semanticscholar.org/paper.pdf"],
        )
        client = _make_streaming_client()
        source = SemanticScholarSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is None


# ---------------------------------------------------------------------------
# PMCOASource
# ---------------------------------------------------------------------------


class TestPMCOASource:
    async def test_downloads_from_pmc_oa(self, tmp_path: Path) -> None:
        record = _rec(pmcid="PMC7654321")
        client = _make_streaming_client()
        source = PMCOASource()
        result = await source.try_download(record, tmp_path, client)
        assert result is not None
        assert "PMC7654321" in result

    async def test_skips_when_no_pmcid(self, tmp_path: Path) -> None:
        record = _rec(pmid="9999")
        client = _make_streaming_client()
        source = PMCOASource()
        result = await source.try_download(record, tmp_path, client)
        assert result is None


# ---------------------------------------------------------------------------
# DOIResolverSource
# ---------------------------------------------------------------------------


class TestDOIResolverSource:
    async def test_follows_doi_redirect(self, tmp_path: Path) -> None:
        record = _rec(doi="10.1000/resolver.test")
        client = _make_streaming_client()
        source = DOIResolverSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is not None
        assert result.endswith(".pdf")

    async def test_skips_when_no_doi(self, tmp_path: Path) -> None:
        record = _rec(pmid="555")
        client = _make_streaming_client()
        source = DOIResolverSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is None

    async def test_returns_none_on_404(self, tmp_path: Path) -> None:
        record = _rec(doi="10.1000/notfound")
        client = _make_streaming_client(status=404)
        source = DOIResolverSource()
        result = await source.try_download(record, tmp_path, client)
        assert result is None
