"""RetrievalOrchestrator: runs the full search → dedup → download → OCR pipeline."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from metascreener.module0_retrieval.dedup.engine import DedupEngine
from metascreener.module0_retrieval.models import BooleanQuery, RawRecord, RetrievalResult
from metascreener.module0_retrieval.providers.base import SearchProvider

log = structlog.get_logger(__name__)


class RetrievalOrchestrator:
    """Orchestrates all stages of the literature retrieval pipeline.

    Stages:
        1. Parallel search across all configured providers.
        2. 6-layer deduplication via :class:`DedupEngine`.
        3. PDF download via :class:`~metascreener.module0_retrieval.downloader.manager.PDFDownloader`
           (optional).
        4. OCR/Markdown conversion via
           :class:`~metascreener.module0_retrieval.ocr.router.OCRRouter` (optional).

    Args:
        providers: List of :class:`SearchProvider` instances to query.
        enable_download: Whether to attempt PDF download after dedup.
        enable_ocr: Whether to run OCR after successful downloads.
        enable_semantic_dedup: Whether to enable semantic (Layer 6) dedup.
        output_dir: Root directory for downloaded PDFs and OCR output.
    """

    def __init__(
        self,
        providers: list[SearchProvider],
        enable_download: bool = True,
        enable_ocr: bool = True,
        enable_semantic_dedup: bool = True,
        output_dir: Path | str = "retrieval_output",
    ) -> None:
        self._providers = providers
        self._enable_download = enable_download
        self._enable_ocr = enable_ocr
        self._enable_semantic_dedup = enable_semantic_dedup
        self._output_dir = Path(output_dir)

    async def run(
        self,
        query: BooleanQuery,
        max_results_per_provider: int = 10000,
    ) -> RetrievalResult:
        """Execute the full retrieval pipeline for *query*.

        Args:
            query: Database-agnostic boolean query AST.
            max_results_per_provider: Maximum records to retrieve per provider.

        Returns:
            :class:`RetrievalResult` aggregating all pipeline statistics.
        """
        # Phase 1: parallel search
        search_counts, all_records = await self._search_all(query, max_results_per_provider)
        total_found = len(all_records)
        log.info("retrieval_search_done", total_found=total_found, providers=list(search_counts))

        # Phase 2: deduplication
        engine = DedupEngine(enable_semantic=self._enable_semantic_dedup)
        dedup_result = engine.deduplicate(all_records)
        deduped_records = dedup_result.records
        log.info(
            "retrieval_dedup_done",
            original=dedup_result.original_count,
            deduped=dedup_result.deduped_count,
        )

        result = RetrievalResult(
            search_counts=search_counts,
            total_found=total_found,
            dedup_count=dedup_result.deduped_count,
            records=deduped_records,
            dedup_result=dedup_result,
        )

        # Phase 3: PDF download (optional)
        if self._enable_download and deduped_records:
            result = await self._download_pdfs(result, deduped_records)

        # Phase 4: OCR (optional — only if download was also enabled)
        if self._enable_ocr and self._enable_download and result.downloaded > 0:
            result = await self._run_ocr(result, deduped_records)

        log.info(
            "retrieval_pipeline_done",
            total_found=result.total_found,
            dedup_count=result.dedup_count,
            downloaded=result.downloaded,
            ocr_completed=result.ocr_completed,
        )
        return result

    async def _search_all(
        self,
        query: BooleanQuery,
        max_results: int,
    ) -> tuple[dict[str, int], list[RawRecord]]:
        """Run all providers in parallel and aggregate results.

        Provider exceptions are caught individually so that a single
        failing provider does not abort the whole pipeline.

        Args:
            query: Boolean query to execute.
            max_results: Per-provider result cap.

        Returns:
            Tuple of (search_counts, all_records).
        """

        async def _safe_search(provider: SearchProvider) -> tuple[str, list[RawRecord]]:
            try:
                records = await provider.search(query, max_results)
                log.info("provider_search_done", provider=provider.name, count=len(records))
                return provider.name, records
            except Exception:  # noqa: BLE001
                log.warning("provider_search_failed", provider=provider.name, exc_info=True)
                return provider.name, []

        results: list[tuple[str, list[RawRecord]]] = await asyncio.gather(
            *[_safe_search(p) for p in self._providers]
        )

        search_counts: dict[str, int] = {}
        all_records: list[RawRecord] = []
        for name, records in results:
            search_counts[name] = len(records)
            all_records.extend(records)

        return search_counts, all_records

    async def _download_pdfs(
        self,
        result: RetrievalResult,
        records: list[RawRecord],
    ) -> RetrievalResult:
        """Download PDFs for all deduped records.

        Args:
            result: Current pipeline result to update.
            records: Deduped bibliographic records.

        Returns:
            Updated :class:`RetrievalResult`.
        """
        try:
            from metascreener.module0_retrieval.downloader.manager import (
                PDFDownloader,  # noqa: PLC0415
            )

            pdf_dir = self._output_dir / "pdfs"
            downloader = PDFDownloader()
            download_results = await downloader.download_batch(records, pdf_dir)
            downloaded = sum(1 for dr in download_results if dr.success)
            failed = sum(1 for dr in download_results if not dr.success)
            log.info("retrieval_download_done", downloaded=downloaded, failed=failed)
            return result.model_copy(update={"downloaded": downloaded, "download_failed": failed})
        except Exception:  # noqa: BLE001
            log.warning("retrieval_download_phase_failed", exc_info=True)
            return result

    async def _run_ocr(
        self,
        result: RetrievalResult,
        records: list[RawRecord],
    ) -> RetrievalResult:
        """Run OCR on successfully downloaded PDFs.

        Args:
            result: Current pipeline result to update.
            records: Deduped bibliographic records.

        Returns:
            Updated :class:`RetrievalResult`.
        """
        try:
            from metascreener.module0_retrieval.ocr.pymupdf import PyMuPDFBackend  # noqa: PLC0415
            from metascreener.module0_retrieval.ocr.router import OCRRouter  # noqa: PLC0415

            pdf_dir = self._output_dir / "pdfs"
            ocr_router = OCRRouter(pymupdf=PyMuPDFBackend())
            completed = 0
            for record in records:
                if not record.pmid and not record.doi:
                    continue
                # Reconstruct filename using the same logic as PDFDownloader
                from metascreener.module0_retrieval.downloader.manager import (
                    build_filename,  # noqa: PLC0415
                )
                pdf_path = pdf_dir / build_filename(record)
                if pdf_path.exists():
                    try:
                        await ocr_router.convert_pdf(pdf_path)
                        completed += 1
                    except Exception:  # noqa: BLE001
                        log.warning("ocr_page_failed", record_id=record.record_id, exc_info=True)
            log.info("retrieval_ocr_done", ocr_completed=completed)
            return result.model_copy(update={"ocr_completed": completed})
        except Exception:  # noqa: BLE001
            log.warning("retrieval_ocr_phase_failed", exc_info=True)
            return result
