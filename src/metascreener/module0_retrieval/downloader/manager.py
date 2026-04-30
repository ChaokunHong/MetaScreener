"""PDF download manager — orchestrates sources, cache, and validation."""
from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Any

import httpx
import structlog

from metascreener.module0_retrieval.downloader.cache import DownloadCache
from metascreener.module0_retrieval.downloader.sources import (
    DOIResolverSource,
    EuropePMCSource,
    OpenAlexDirectSource,
    PDFSource,
    PMCOASource,
    SemanticScholarSource,
    UnpaywallSource,
)
from metascreener.module0_retrieval.downloader.validator import PDFValidator
from metascreener.module0_retrieval.models import DownloadResult, RawRecord

logger = structlog.get_logger(__name__)

_DEFAULT_SOURCES: list[PDFSource] = sorted(
    [
        OpenAlexDirectSource(),
        EuropePMCSource(),
        UnpaywallSource(),
        SemanticScholarSource(),
        PMCOASource(),
        DOIResolverSource(),
    ],
    key=lambda s: s.priority,
)


class PDFDownloader:
    """Cascading PDF downloader with caching and validation.

    Tries each :class:`PDFSource` in priority order and stores results
    in an optional :class:`DownloadCache`.  Downloaded files are
    validated by :class:`PDFValidator` before being considered successful.

    Args:
        sources: Ordered list of :class:`PDFSource` implementations.
            Defaults to all 6 built-in sources sorted by priority.
        cache: Persistent download cache.  Pass *None* to disable caching.
        validator: PDF validator instance.
        max_workers: Maximum number of concurrent download tasks.
    """

    def __init__(
        self,
        sources: list[PDFSource] | None = None,
        cache: DownloadCache | None = None,
        validator: PDFValidator | None = None,
        max_workers: int = 16,
    ) -> None:
        self._sources: list[PDFSource] = sorted(
            sources if sources is not None else _DEFAULT_SOURCES,
            key=lambda s: s.priority,
        )
        self._cache = cache
        self._validator = validator or PDFValidator()
        self._semaphore = asyncio.Semaphore(max_workers)

    async def download_batch(
        self,
        records: list[RawRecord],
        output_dir: Path,
    ) -> list[DownloadResult]:
        """Download PDFs for all *records* in parallel.

        Args:
            records: Bibliographic records to download.
            output_dir: Directory where PDFs will be written.

        Returns:
            One :class:`DownloadResult` per input record, in the same order.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=60.0) as client:
            tasks = [
                self._download_one(record, output_dir, client)
                for record in records
            ]
            return await asyncio.gather(*tasks)

    async def _download_one(
        self,
        record: RawRecord,
        output_dir: Path,
        client: Any,
    ) -> DownloadResult:
        """Download a single record, respecting the semaphore.

        Args:
            record: Target bibliographic record.
            output_dir: Destination directory.
            client: Shared async HTTP client.

        Returns:
            :class:`DownloadResult` for this record.
        """
        async with self._semaphore:
            return await self._try_record(record, output_dir, client)

    async def _try_record(
        self,
        record: RawRecord,
        output_dir: Path,
        client: Any,
    ) -> DownloadResult:
        """Core logic: cache check → source cascade → validation → cache write.

        Args:
            record: Target bibliographic record.
            output_dir: Destination directory.
            client: Shared async HTTP client.

        Returns:
            :class:`DownloadResult` for this record.
        """
        # 1. Check cache
        if self._cache is not None:
            cached = await self._cache.get(record.record_id)
            if cached is not None:
                logger.debug(
                    "Cache hit",
                    record_id=record.record_id,
                    success=cached["success"],
                )
                return DownloadResult(
                    record_id=record.record_id,
                    success=cached["success"],
                    pdf_path=cached["pdf_path"],
                    source_used=cached["source"],
                    attempts=[{"source": "cache", "status": "hit"}],
                )

        # 2. Try each source in priority order
        attempts: list[dict[str, Any]] = []
        for source in self._sources:
            path_str = await source.try_download(record, output_dir, client)

            if path_str is None:
                attempts.append({"source": source.name, "status": "failed"})
                continue

            # 3. Validate the downloaded file
            validation = self._validator.validate(Path(path_str))
            if not validation.valid:
                logger.debug(
                    "Validation failed after download",
                    source=source.name,
                    record_id=record.record_id,
                    error=validation.error,
                )
                # Remove invalid file to avoid stale artefacts
                try:
                    Path(path_str).unlink(missing_ok=True)
                except OSError:
                    pass
                attempts.append({
                    "source": source.name,
                    "status": "failed",
                    "error": validation.error,
                })
                continue

            # Success
            attempts.append({"source": source.name, "status": "success", "path": path_str})
            result = DownloadResult(
                record_id=record.record_id,
                success=True,
                pdf_path=path_str,
                source_used=source.name,
                attempts=attempts,
            )
            await self._update_cache(record.record_id, result)
            return result

        # All sources failed
        result = DownloadResult(
            record_id=record.record_id,
            success=False,
            pdf_path=None,
            source_used=None,
            attempts=attempts,
        )
        await self._update_cache(record.record_id, result)
        return result

    async def _update_cache(self, record_id: str, result: DownloadResult) -> None:
        """Persist a download result to the cache if available.

        Args:
            record_id: Unique record identifier.
            result: Completed download result.
        """
        if self._cache is not None:
            await self._cache.set(
                record_id,
                result.success,
                result.pdf_path,
                result.source_used,
            )


def build_filename(record: RawRecord) -> str:
    """Return a deterministic, filesystem-safe PDF filename for *record*.

    Priority: ``PMID_{id}.pdf`` > ``PMCID_{id}.pdf`` > ``DOI_{safe}.pdf``
    > ``TITLE_{hash8}.pdf``.

    Args:
        record: Bibliographic record.

    Returns:
        Filename string ending in ``.pdf``.
    """
    if record.pmid:
        return f"PMID_{record.pmid}.pdf"
    if record.pmcid:
        pmcid = record.pmcid.upper()
        if not pmcid.startswith("PMC"):
            pmcid = f"PMC{pmcid}"
        return f"PMCID_{pmcid}.pdf"
    if record.doi:
        doi_safe = re.sub(r"[^\w.\-]", "_", record.doi)
        return f"DOI_{doi_safe}.pdf"
    title_hash = hashlib.sha256(record.title.encode()).hexdigest()[:8]
    return f"TITLE_{title_hash}.pdf"
