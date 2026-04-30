"""Extract 'Criteria for considering studies' section from Cochrane review PDFs.

For each PDF in --input-dir (default: external_sources/cochrane_pdfs/),
pulls the standard Cochrane subsection block starting at
  'Criteria for considering studies for this review'
and ending at
  'Search methods for identification of studies'.

Outputs plain text to --output-dir (default: external_sources/methods_texts/)
using the naming convention 'CLEF_<topic_id>_methods.txt' where topic_id
is the PDF stem (e.g. CD000996).

Usage:
  # Single file
  python experiments/scripts/extract_cochrane_methods.py --input external_sources/cochrane_pdfs/CD000996.pdf

  # Batch directory (default paths)
  python experiments/scripts/extract_cochrane_methods.py

  # Batch with custom paths
  python experiments/scripts/extract_cochrane_methods.py \
      --input-dir /some/dir --output-dir /some/other/dir
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_INPUT_DIR = Path("external_sources/cochrane_pdfs")
DEFAULT_OUTPUT_DIR = Path("external_sources/methods_texts")

# TOC lines look like 'METHODS..................5' — filter them out by
# refusing to anchor on matches surrounded by dots or positioned too early.
MIN_BODY_CHAR_POS = 2500  # TOC typically ends well before this

START_PATTERNS = [
    r"Criteria for considering studies for this review",
    r"Criteria for considering studies",  # fallback
]

END_PATTERNS = [
    r"Search methods for identification of studies",
    r"Search methods for identification",
    r"Electronic searches",
    # last resort — if the above are missing, stop at data collection
    r"Data collection and analysis",
]


class ExtractionError(Exception):
    """Raised when a PDF cannot be parsed into a criteria section."""


# Page header/footer artifacts that land mid-section when PyMuPDF
# concatenates multi-page text. All patterns match a full line.
PAGE_ARTIFACT_PATTERNS = [
    re.compile(r"^\s*Copyright © \d{4} The Cochrane Collaboration\..*$"),
    re.compile(r"^\s*Published by John Wiley & Sons,?\s*Ltd\.\s*$"),
    re.compile(r"^\s*Cochrane Library\s*$"),
    re.compile(r"^\s*Cochrane\s*$"),  # PyMuPDF sometimes splits "Cochrane Library" across lines
    re.compile(r"^\s*Library\s*$"),
    re.compile(r"^\s*Cochrane Database of Systematic Reviews\s*$"),
    re.compile(r"^\s*Trusted evidence\.\s*$"),
    re.compile(r"^\s*Informed decisions\.\s*$"),
    re.compile(r"^\s*Better health\.\s*$"),
    re.compile(r"^\s*\d+\s*$"),  # standalone page number
    re.compile(r"^.+\(Protocol\)\s*$"),  # review-title line ending in (Protocol)
    re.compile(r"^.+\(Review\)\s*$"),  # review-title line ending in (Review)
]


def _strip_page_artifacts(text: str) -> str:
    """Remove line-matching Cochrane page header/footer artifacts.

    Also collapses any run of 3+ blank lines into 2. Trailing/leading
    whitespace trimmed.
    """
    kept: list[str] = []
    for line in text.split("\n"):
        if any(p.match(line) for p in PAGE_ARTIFACT_PATTERNS):
            continue
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _find_first_match(patterns: list[str], text: str, min_pos: int) -> re.Match | None:
    """Return the earliest match of any pattern at or after ``min_pos``.

    Patterns are tried in order; within a single pattern the first match
    (after min_pos) wins.
    """
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            if m.start() >= min_pos:
                return m
    return None


def _looks_like_toc_line(text: str, pos: int) -> bool:
    """TOC entries have many dots and a trailing page number."""
    window = text[max(0, pos - 5) : pos + 120]
    return window.count(".") >= 6


def extract_methods(pdf_path: Path) -> tuple[str, dict]:
    """Return ``(criteria_section, diagnostics)`` for one PDF.

    The criteria_section is plain text stripped of leading/trailing
    whitespace. diagnostics is a dict with keys: n_pages, start_pos,
    end_pos, start_pattern, end_pattern, n_chars.
    """
    doc = fitz.open(str(pdf_path))
    if doc.is_encrypted:
        raise ExtractionError(f"PDF is encrypted: {pdf_path}")

    full_text = "\n".join(page.get_text() for page in doc)
    n_pages = len(doc)
    doc.close()

    # First, try anchor in body (past TOC)
    start_match = _find_first_match(START_PATTERNS, full_text, MIN_BODY_CHAR_POS)
    if start_match is None:
        # Retry from pos 0 but filter out TOC-looking matches
        for pat in START_PATTERNS:
            for m in re.finditer(pat, full_text, re.IGNORECASE):
                if not _looks_like_toc_line(full_text, m.start()):
                    start_match = m
                    break
            if start_match:
                break

    if start_match is None:
        raise ExtractionError(
            f"Could not locate criteria section in {pdf_path}. "
            f"None of {START_PATTERNS} matched."
        )

    start = start_match.start()
    start_pattern = start_match.group(0)

    # End anchor: first matching pattern after start
    body_after = full_text[start + len(start_match.group(0)) :]
    end_match = _find_first_match(END_PATTERNS, body_after, 0)
    if end_match is None:
        logger.warning(
            "extract_end_marker_missing",
            pdf=str(pdf_path),
            using="end of document",
        )
        end = len(full_text)
        end_pattern = None
    else:
        end = start + len(start_match.group(0)) + end_match.start()
        end_pattern = end_match.group(0)

    raw_section = full_text[start:end].strip()
    cleaned = _strip_page_artifacts(raw_section)

    diagnostics = {
        "n_pages": n_pages,
        "start_pos": start,
        "end_pos": end,
        "n_chars_raw": len(raw_section),
        "n_chars": len(cleaned),
        "n_chars_stripped": len(raw_section) - len(cleaned),
        "start_pattern": start_pattern,
        "end_pattern": end_pattern,
    }
    return cleaned, diagnostics


def _derive_output_name(pdf_path: Path) -> str:
    """CLEF_<topic_id>_methods.txt for Cochrane; generic fallback otherwise."""
    stem = pdf_path.stem
    if re.match(r"^CD\d+$", stem):
        return f"CLEF_{stem}_methods.txt"
    return f"{stem}_methods.txt"


def process_one(pdf_path: Path, output_dir: Path) -> bool:
    try:
        section, diag = extract_methods(pdf_path)
    except ExtractionError as e:
        logger.error("extract_failed", pdf=str(pdf_path), err=str(e))
        return False
    except Exception as e:  # pragma: no cover - defensive
        logger.error(
            "extract_unexpected_error",
            pdf=str(pdf_path),
            err=str(e),
            err_type=type(e).__name__,
        )
        return False

    out_name = _derive_output_name(pdf_path)
    out_path = output_dir / out_name
    out_path.write_text(section, encoding="utf-8")

    logger.info(
        "extract_done",
        pdf=pdf_path.name,
        output=str(out_path),
        **diag,
    )

    # Warn on suspicious sizes
    if diag["n_chars"] < 300:
        logger.warning(
            "section_suspiciously_short",
            pdf=pdf_path.name,
            n_chars=diag["n_chars"],
            hint="verify PDF has a full Methods section",
        )
    if diag["n_chars"] > 10000:
        logger.warning(
            "section_suspiciously_long",
            pdf=pdf_path.name,
            n_chars=diag["n_chars"],
            hint="end marker may have been missed; inspect manually",
        )

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Single PDF path (overrides --input-dir).",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Directory of PDFs (default: {DEFAULT_INPUT_DIR}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for methods.txt (default: {DEFAULT_OUTPUT_DIR}).",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.input is not None:
        targets = [args.input]
    else:
        targets = sorted(args.input_dir.glob("*.pdf"))

    if not targets:
        print(f"No PDFs found in {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    n_ok = 0
    n_fail = 0
    for pdf in targets:
        if process_one(pdf, args.output_dir):
            n_ok += 1
        else:
            n_fail += 1

    print(f"\n=== Extraction done: {n_ok} ok, {n_fail} failed ===")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
