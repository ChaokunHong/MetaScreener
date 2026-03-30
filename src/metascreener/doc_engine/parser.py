"""Document Parser Orchestrator: parse a PDF via OCR and build a StructuredDocument.

Coordinates all doc_engine sub-modules — section parser, table extractor,
figure extractor, metadata extractor, and reference parser — into a single
async ``parse()`` call.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from metascreener.doc_engine.figure_extractor import extract_figure_refs_from_markdown
from metascreener.doc_engine.metadata_extractor import extract_metadata
from metascreener.doc_engine.models import OCRReport, StructuredDocument
from metascreener.doc_engine.reference_parser import parse_references
from metascreener.doc_engine.section_parser import parse_sections
from metascreener.doc_engine.table_extractor import extract_tables_from_markdown

if TYPE_CHECKING:
    from metascreener.doc_engine.cache import DocumentCache

logger = structlog.get_logger(__name__)

# Stable identifier for "default" OCR configuration used as the cache key.
_DEFAULT_OCR_CONFIG_HASH = "default"


class DocumentParser:
    """Orchestrate the full PDF-to-StructuredDocument pipeline.

    Args:
        ocr_router: Any object that exposes
            ``async convert_pdf(pdf_path: Path) -> OCRResult``
            where ``OCRResult`` has attributes:
            ``.markdown``, ``.total_pages``, ``.backend_usage``,
            ``.conversion_time_s``.
        cache: Optional :class:`~metascreener.doc_engine.cache.DocumentCache`
            instance.  When provided, ``parse()`` returns the cached document
            on a cache hit and stores the parsed result on a miss.
    """

    def __init__(
        self,
        ocr_router: Any,  # noqa: ANN401
        cache: DocumentCache | None = None,
    ) -> None:
        self._ocr_router = ocr_router
        self._cache = cache

    async def parse(self, pdf_path: Path) -> StructuredDocument:
        """Parse a PDF and return a fully-populated StructuredDocument.

        Pipeline:
            1. Convert PDF to Markdown via the injected OCR router.
            2. Parse section tree from Markdown.
            3. Extract tables from Markdown.
            4. Extract figure references from Markdown.
            5. Extract bibliographic metadata from Markdown.
            6. Parse reference list from the "References" section.
            7. Link tables to their source sections.
            8. Assemble and return the StructuredDocument.

        Args:
            pdf_path: Absolute path to the PDF file to parse.

        Returns:
            A fully populated StructuredDocument.
        """
        logger.info("document_parse_start", pdf=str(pdf_path))

        pdf_hash: str | None = None
        if self._cache is not None:
            pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            cached = await self._cache.get(pdf_hash, _DEFAULT_OCR_CONFIG_HASH)
            if cached is not None:
                logger.info("document_cache_hit", pdf=str(pdf_path), pdf_hash=pdf_hash[:12])
                return cached

        ocr_result = await self._ocr_router.convert_pdf(pdf_path)
        markdown: str = ocr_result.markdown

        stripped = markdown.strip()
        if stripped.startswith("---"):
            end = stripped.find("---", 3)
            if end != -1:
                after_frontmatter = stripped[end + 3:].strip()
                if after_frontmatter:
                    markdown = after_frontmatter
                # else: frontmatter was the only content — keep original

        _MIN_CONTENT_CHARS = 100
        content_chars = len(markdown.strip())
        if content_chars < _MIN_CONTENT_CHARS:
            logger.warning(
                "ocr_output_too_short",
                chars=content_chars,
                backend=str(ocr_result.backend_usage),
                pdf=str(pdf_path),
            )
            try:
                from metascreener.io.pdf_parser import extract_text_from_pdf
                fallback_text = extract_text_from_pdf(pdf_path)
                if len(fallback_text.strip()) > content_chars:
                    logger.info("ocr_pymupdf_fallback_used", chars=len(fallback_text))
                    markdown = fallback_text
                    ocr_result.backend_usage["pymupdf_fallback"] = 1
            except Exception:
                logger.warning("ocr_pymupdf_fallback_failed")

        sections = parse_sections(markdown)
        tables = extract_tables_from_markdown(markdown)
        figures = extract_figure_refs_from_markdown(markdown)
        metadata = extract_metadata(markdown)

        ref_text = ""
        for section in sections:
            if section.heading.strip().lower() == "references":
                ref_text = section.content
                break
        references = parse_references(ref_text)

        table_map = {t.table_id: t for t in tables}
        for section in sections:
            for tid in section.tables_in_section:
                if tid in table_map and table_map[tid].source_section is None:
                    table_map[tid].source_section = section.heading

        doc_id = hashlib.sha256(pdf_path.name.encode()).hexdigest()[:12]
        ocr_report = OCRReport(
            total_pages=ocr_result.total_pages,
            backend_usage=ocr_result.backend_usage,
            conversion_time_s=ocr_result.conversion_time_s,
            quality_scores={},
            warnings=[],
        )

        doc = StructuredDocument(
            doc_id=doc_id,
            source_path=pdf_path,
            metadata=metadata,
            sections=sections,
            tables=tables,
            figures=figures,
            references=references,
            supplementary=None,
            raw_markdown=markdown,
            ocr_report=ocr_report,
        )

        logger.info(
            "document_parse_complete",
            doc_id=doc_id,
            sections=len(sections),
            tables=len(tables),
            figures=len(figures),
            references=len(references),
        )

        if self._cache is not None and pdf_hash is not None:
            try:
                await self._cache.put(pdf_hash, _DEFAULT_OCR_CONFIG_HASH, doc)
                logger.debug("document_cache_stored", pdf=str(pdf_path), pdf_hash=pdf_hash[:12])
            except Exception:
                logger.warning("document_cache_put_failed", pdf=str(pdf_path))

        return doc
