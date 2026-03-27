"""PDF source implementations for the download pipeline.

Each source encapsulates the logic for fetching a PDF from one provider.
Sources are tried in ascending *priority* order (lower = tried first).
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import structlog

from metascreener.module0_retrieval.models import RawRecord

logger = structlog.get_logger(__name__)

_CHUNK_SIZE = 64 * 1024  # 64 KB streaming chunks
_PDF_MAGIC = b"%PDF"

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class PDFSource(ABC):
    """Abstract base class for a single PDF retrieval strategy.

    Subclasses implement :meth:`try_download` which should return the
    path to the saved file on success, or *None* on any failure.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source identifier."""
        ...

    @property
    @abstractmethod
    def priority(self) -> int:
        """Lower values are tried first."""
        ...

    @abstractmethod
    async def try_download(
        self,
        record: RawRecord,
        output_dir: Path,
        client: Any,
    ) -> str | None:
        """Attempt to download a PDF for *record*.

        Args:
            record: Bibliographic record with identifiers and URLs.
            output_dir: Directory where the PDF should be saved.
            client: An async HTTP client (e.g. ``httpx.AsyncClient``).

        Returns:
            Absolute path to the saved file as a string, or *None* on failure.
        """
        ...

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _stream_to_file(
        self,
        url: str,
        dest: Path,
        client: Any,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> str | None:
        """Stream *url* to *dest*, validating the magic bytes.

        Args:
            url: URL to fetch.
            dest: Destination file path.
            client: Async HTTP client.
            extra_headers: Optional additional request headers.

        Returns:
            String path on success, ``None`` on any error.
        """
        headers = {"Accept": "application/pdf"}
        if extra_headers:
            headers.update(extra_headers)
        try:
            async with client.stream("GET", url, headers=headers, follow_redirects=True) as resp:
                if resp.status_code != 200:
                    logger.debug(
                        "HTTP error fetching PDF",
                        source=self.name,
                        url=url,
                        status=resp.status_code,
                    )
                    return None

                # Validate magic bytes from first chunk before writing
                first_chunk: bytes = b""
                chunks: list[bytes] = []
                async for chunk in resp.aiter_bytes(chunk_size=_CHUNK_SIZE):
                    if not first_chunk:
                        first_chunk = chunk
                        if not first_chunk.startswith(_PDF_MAGIC):
                            logger.debug(
                                "Response is not a PDF",
                                source=self.name,
                                url=url,
                            )
                            return None
                    chunks.append(chunk)

                if not chunks:
                    return None

                dest.write_bytes(b"".join(chunks))
                logger.debug("PDF saved", source=self.name, path=str(dest))
                return str(dest)

        except Exception as exc:  # noqa: BLE001
            logger.debug("Download failed", source=self.name, url=url, error=str(exc))
            return None


# ---------------------------------------------------------------------------
# Concrete source implementations
# ---------------------------------------------------------------------------


class OpenAlexDirectSource(PDFSource):
    """Download from direct PDF URLs provided by OpenAlex.

    Priority 10 — tried first, since these are already-resolved links.
    """

    @property
    def name(self) -> str:
        return "openalex_direct"

    @property
    def priority(self) -> int:
        return 10

    async def try_download(
        self,
        record: RawRecord,
        output_dir: Path,
        client: Any,
    ) -> str | None:
        """Try each URL in ``record.pdf_urls`` in order.

        Args:
            record: Bibliographic record.
            output_dir: Destination directory.
            client: Async HTTP client.

        Returns:
            Path to saved file or *None*.
        """
        if not record.pdf_urls:
            return None

        stem = _safe_stem(record)
        for url in record.pdf_urls:
            dest = output_dir / f"{stem}_openalex.pdf"
            result = await self._stream_to_file(url, dest, client)
            if result:
                return result
        return None


class EuropePMCSource(PDFSource):
    """Download full-text PDF from Europe PMC.

    Priority 20.  Requires ``record.pmcid``.
    API endpoint: ``https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextPDF``
    """

    _BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextPDF"

    @property
    def name(self) -> str:
        return "europepmc"

    @property
    def priority(self) -> int:
        return 20

    async def try_download(
        self,
        record: RawRecord,
        output_dir: Path,
        client: Any,
    ) -> str | None:
        """Fetch PDF via Europe PMC REST API.

        Args:
            record: Bibliographic record with ``pmcid``.
            output_dir: Destination directory.
            client: Async HTTP client.

        Returns:
            Path to saved file or *None*.
        """
        if not record.pmcid:
            return None

        pmcid = record.pmcid.upper()
        if not pmcid.startswith("PMC"):
            pmcid = f"PMC{pmcid}"

        url = self._BASE.format(pmcid=pmcid)
        dest = output_dir / f"PMCID_{pmcid}.pdf"
        return await self._stream_to_file(url, dest, client)


class UnpaywallSource(PDFSource):
    """Download OA PDF via the Unpaywall API.

    Priority 30.  Requires ``record.doi`` and a contact e-mail.
    API: ``https://api.unpaywall.org/v2/{doi}?email={email}``
    """

    _API_BASE = "https://api.unpaywall.org/v2/{doi}?email={email}"
    _DEFAULT_EMAIL = "metascreener@example.com"

    def __init__(self, email: str | None = None) -> None:
        self._email = email or self._DEFAULT_EMAIL

    @property
    def name(self) -> str:
        return "unpaywall"

    @property
    def priority(self) -> int:
        return 30

    async def try_download(
        self,
        record: RawRecord,
        output_dir: Path,
        client: Any,
    ) -> str | None:
        """Query Unpaywall for the best OA PDF location.

        Args:
            record: Bibliographic record with ``doi``.
            output_dir: Destination directory.
            client: Async HTTP client.

        Returns:
            Path to saved file or *None*.
        """
        if not record.doi:
            return None

        api_url = self._API_BASE.format(doi=record.doi, email=self._email)
        try:
            resp = await client.get(api_url, follow_redirects=True)
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Unpaywall API error", error=str(exc), doi=record.doi)
            return None

        best = data.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf")
        if not pdf_url:
            return None

        doi_safe = re.sub(r"[^\w.\-]", "_", record.doi)
        dest = output_dir / f"DOI_{doi_safe}.pdf"
        return await self._stream_to_file(pdf_url, dest, client)


class SemanticScholarSource(PDFSource):
    """Download from Semantic Scholar PDF URLs stored in the record.

    Priority 40.  Uses ``record.pdf_urls`` populated by the S2 provider.
    """

    @property
    def name(self) -> str:
        return "semantic_scholar"

    @property
    def priority(self) -> int:
        return 40

    async def try_download(
        self,
        record: RawRecord,
        output_dir: Path,
        client: Any,
    ) -> str | None:
        """Try each URL in ``record.pdf_urls`` (S2-sourced records).

        Args:
            record: Bibliographic record from Semantic Scholar.
            output_dir: Destination directory.
            client: Async HTTP client.

        Returns:
            Path to saved file or *None*.
        """
        if not record.pdf_urls or record.source_db != "semantic_scholar":
            return None

        stem = _safe_stem(record)
        for url in record.pdf_urls:
            dest = output_dir / f"{stem}_s2.pdf"
            result = await self._stream_to_file(url, dest, client)
            if result:
                return result
        return None


class PMCOASource(PDFSource):
    """Download from the PubMed Central Open Access endpoint.

    Priority 50.  Requires ``record.pmcid``.
    URL: ``https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf``
    """

    _BASE = "https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf"

    @property
    def name(self) -> str:
        return "pmc_oa"

    @property
    def priority(self) -> int:
        return 50

    async def try_download(
        self,
        record: RawRecord,
        output_dir: Path,
        client: Any,
    ) -> str | None:
        """Fetch directly from PMC OA CDN.

        Args:
            record: Bibliographic record with ``pmcid``.
            output_dir: Destination directory.
            client: Async HTTP client.

        Returns:
            Path to saved file or *None*.
        """
        if not record.pmcid:
            return None

        pmcid = record.pmcid.upper()
        if not pmcid.startswith("PMC"):
            pmcid = f"PMC{pmcid}"

        url = self._BASE.format(pmcid=pmcid)
        dest = output_dir / f"PMCID_{pmcid}_pmc.pdf"
        return await self._stream_to_file(url, dest, client)


class DOIResolverSource(PDFSource):
    """Last-resort: follow the DOI redirect and look for a PDF link.

    Priority 60.  Requires ``record.doi``.
    Follows ``https://doi.org/{doi}`` and checks if the response is a PDF.
    """

    _DOI_BASE = "https://doi.org/{doi}"

    @property
    def name(self) -> str:
        return "doi_resolver"

    @property
    def priority(self) -> int:
        return 60

    async def try_download(
        self,
        record: RawRecord,
        output_dir: Path,
        client: Any,
    ) -> str | None:
        """Follow DOI redirect and attempt to save if a PDF is returned.

        Args:
            record: Bibliographic record with ``doi``.
            output_dir: Destination directory.
            client: Async HTTP client.

        Returns:
            Path to saved file or *None*.
        """
        if not record.doi:
            return None

        url = self._DOI_BASE.format(doi=record.doi)
        doi_safe = re.sub(r"[^\w.\-]", "_", record.doi)
        dest = output_dir / f"DOI_{doi_safe}_resolved.pdf"
        return await self._stream_to_file(url, dest, client)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_stem(record: RawRecord) -> str:
    """Return a filesystem-safe filename stem for *record*.

    Preference order: PMID → PMCID → DOI → record_id hash.

    Args:
        record: Bibliographic record.

    Returns:
        A short string safe for use in filenames.
    """
    if record.pmid:
        return f"PMID_{record.pmid}"
    if record.pmcid:
        pmcid = record.pmcid.upper()
        return f"PMCID_{pmcid}"
    if record.doi:
        doi_safe = re.sub(r"[^\w.\-]", "_", record.doi)
        return f"DOI_{doi_safe}"
    return f"REC_{record.record_id[:8]}"
