"""OCR backends and intelligent router for PDF-to-markdown conversion."""
from __future__ import annotations

from metascreener.module0_retrieval.ocr.api_backend import APIBackend
from metascreener.module0_retrieval.ocr.base import OCRBackend
from metascreener.module0_retrieval.ocr.pymupdf_backend import PyMuPDFBackend
from metascreener.module0_retrieval.ocr.router import OCRRouter, PageInfo
from metascreener.module0_retrieval.ocr.tesseract_backend import TesseractBackend
from metascreener.module0_retrieval.ocr.vlm_backend import VLMBackend

__all__ = [
    "OCRBackend",
    "PyMuPDFBackend",
    "TesseractBackend",
    "VLMBackend",
    "APIBackend",
    "OCRRouter",
    "PageInfo",
]
