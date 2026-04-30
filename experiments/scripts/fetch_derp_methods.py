"""Download DERP (Drug Effectiveness Review Project) final reports from the
Wayback Machine and extract their Methods chapter for external-validation
criteria generation.

DERP rationale: Cohen 2006 benchmark's 15 SR topics are DERP final reports.
The original OHSU DERP domain (derp.ohsu.edu) is 404, so we pull the latest
archived copies from archive.org. 13 of 15 Cohen topics have a final report
PDF archived; ADHD has only the Key Questions PDF; ACEInhibitors is
unrecoverable from Wayback and must be handled with a fallback criteria
template (see `--fallback` flag).

DERP report structure (varies across drug classes):
  Cover / front matter
  Table of Contents (contains many "........." lines)
  Executive Summary
  Scope and Key Questions
  **METHODS** chapter   ← what we want
    Populations
    Interventions
    Effectiveness / safety outcomes
    Study designs
    Inclusion criteria  (critical)
    Data sources and searches
    Study selection / data extraction
  **RESULTS** chapter
  ...

We extract the METHODS chapter body: from the first non-TOC "METHODS"
heading to the next non-TOC "RESULTS" heading. Page header/footer
artifacts ("Final Report Update N", "Drug Effectiveness Review Project",
page numbers) are stripped.

Usage:
  # Download + extract all 13 available DERP reports
  python experiments/scripts/fetch_derp_methods.py

  # Only specific drugs
  python experiments/scripts/fetch_derp_methods.py --drugs BetaBlockers,Statins

  # Redownload (overwrite PDFs)
  python experiments/scripts/fetch_derp_methods.py --overwrite
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
import httpx
import structlog

logger = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = PROJECT_ROOT / "external_sources" / "derp_pdfs"
METHODS_DIR = PROJECT_ROOT / "external_sources" / "methods_texts"

# Wayback Machine raw-content URLs per Cohen drug topic.
# Generated from a CDX search 2026-04-24 on derp.ohsu.edu/final/*.pdf;
# latest non-"evidence"/"key-questions" snapshot per DERP code; see
# SESSION_HANDOFF Step B discoveries for the mapping audit log.
DERP_URLS: dict[str, str | None] = {
    "ADHD": None,              # Wayback has KQs only; no final report
    "Antihistamines": (
        "https://web.archive.org/web/20140111020034id_/"
        "http://derp.ohsu.edu/final/AH2_Final_Report_Update%2011.pdf"
    ),
    "AtypicalAntipsychotics": (
        "https://web.archive.org/web/20140111020039id_/"
        "http://derp.ohsu.edu/final/AAP_final_report_update_27.pdf"
    ),
    "BetaBlockers": (
        "https://web.archive.org/web/20140111015926id_/"
        "http://derp.ohsu.edu/final/BB_Final_Report_Update%204_Shaded_09_JUL.pdf"
    ),
    "CalciumChannelBlockers": (
        "https://web.archive.org/web/20140111020057id_/"
        "http://derp.ohsu.edu/final/CCB_%20Final_Report_update%2022.pdf"
    ),
    "Estrogens": (
        "https://web.archive.org/web/20140111015854id_/"
        "http://derp.ohsu.edu/final/HT_Final_Report_Update%203.pdf"
    ),
    "NSAIDS": (
        "https://web.archive.org/web/20140111020048id_/"
        "http://derp.ohsu.edu/final/NSAIDS_Final_Report_Update%2034.pdf"
    ),
    "Opiods": (
        "https://web.archive.org/web/20120531111118id_/"
        "http://derp.ohsu.edu/final/OP_Final_Report_Update%205.pdf"
    ),
    "OralHypoglycemics": (
        "https://web.archive.org/web/20140111015728id_/"
        "http://derp.ohsu.edu/final/OH_Final_Report_Update%202.pdf"
    ),
    "ProtonPumpInhibitors": (
        "https://web.archive.org/web/20140111020105id_/"
        "http://derp.ohsu.edu/final/"
        "PPI_%20final%20report_update%205_version%204_unshaded_09_May1.pdf"
    ),
    "SkeletalMuscleRelaxants": (
        "https://web.archive.org/web/20140111020053id_/"
        "http://derp.ohsu.edu/final/SMR_Final_Report_Update%2028.pdf"
    ),
    "Statins": (
        "https://web.archive.org/web/20140111020054id_/"
        "http://derp.ohsu.edu/final/"
        "Statins_final%20report_update%205_unshaded_NOV_093.pdf"
    ),
    "Triptans": (
        "https://web.archive.org/web/20140111015902id_/"
        "http://derp.ohsu.edu/final/"
        "Triptans_final_report_update%204_version%202_unshaded_09_JUN.pdf"
    ),
    "UrinaryIncontinence": (
        "https://web.archive.org/web/20140111015955id_/"
        "http://derp.ohsu.edu/final/"
        "OAB_final_%20report_update%204_unshaded_MAR_09.pdf"
    ),
    # ACEInhibitors not in Wayback — handled with --fallback only
    "ACEInhibitors": None,
}

# Regex to identify a TOC-style line: many dots usually with a trailing page #
_TOC_LINE = re.compile(r"\.{5,}")

# Page header / footer artifacts common across DERP reports. The regex
# forms match whole-line occurrences after PyMuPDF page-concatenation.
DERP_ARTIFACTS = [
    re.compile(r"^\s*Final Report Update\s+\d+\s*$"),
    re.compile(r"^\s*Final Report\s*$"),
    re.compile(r"^\s*Drug Effectiveness Review Project\s*$"),
    re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$"),
    re.compile(r"^\s*\d+\s*$"),  # lone page number
]


def _strip_derp_artifacts(text: str) -> str:
    """Remove DERP page header/footer artifacts from extracted methods text."""
    kept = []
    for line in text.split("\n"):
        if any(p.match(line) for p in DERP_ARTIFACTS):
            continue
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _find_section_start(
    full_text: str,
    keyword: str,
    *,
    require_standalone: bool = True,
    skip_toc: bool = True,
) -> int | None:
    """Find the position of ``keyword`` acting as a section heading.

    A standalone heading is a line whose content (after trimming) equals the
    keyword (case-insensitive). Lines that look like TOC entries (many dots)
    are skipped when ``skip_toc`` is True.
    """
    for m in re.finditer(re.escape(keyword), full_text, re.IGNORECASE):
        start_of_line = full_text.rfind("\n", 0, m.start()) + 1
        end_of_line = full_text.find("\n", m.end())
        if end_of_line == -1:
            end_of_line = len(full_text)
        line = full_text[start_of_line:end_of_line].strip()
        if skip_toc and _TOC_LINE.search(line):
            continue
        if require_standalone and not line.lower().startswith(keyword.lower()):
            continue
        # Standalone heading: entire line is the keyword (allow short trailing)
        if require_standalone and len(line) > len(keyword) + 5:
            continue
        return m.start()
    return None


def extract_derp_methods(pdf_path: Path) -> tuple[str, dict]:
    """Extract the Methods chapter of a DERP final report.

    Primary strategy: locate a standalone "METHODS" line past the TOC, end
    at the first standalone "RESULTS" line after it. Fallback if either is
    missing: narrow on the "Inclusion Criteria" subsection.
    """
    doc = fitz.open(str(pdf_path))
    full_text = "\n".join(page.get_text() for page in doc)
    n_pages = len(doc)
    doc.close()

    # Safety cap: DERP Methods chapters are typically 5-15k chars; anything
    # beyond 20k from start means we failed to find the real end marker.
    MAX_METHODS_CHARS = 20000

    start = _find_section_start(full_text, "METHODS")
    end: int | None = None
    strategy = "methods_to_results"
    if start is not None:
        # Primary end: standalone RESULTS (case-sensitive — DERP uses ALL CAPS chapter heads)
        search_from = start + len("METHODS")
        for m in re.finditer(r"RESULTS", full_text[search_from:]):
            abs_pos = search_from + m.start()
            sol = full_text.rfind("\n", 0, abs_pos) + 1
            eol = full_text.find("\n", abs_pos + len("RESULTS"))
            if eol == -1:
                eol = len(full_text)
            line = full_text[sol:eol].strip()
            if _TOC_LINE.search(line):
                continue
            # Must be standalone (line length ≈ marker length)
            if line == "RESULTS" or line.startswith("RESULTS "):
                end = abs_pos
                break
        # Fallback 1: first of several subsection headers past METHODS
        if end is None:
            fallback_markers = [
                "Search Strategies",
                "Search Strategy",
                "Data Sources and Searches",
                "Data Sources",
                "Data Extraction",
                "Data Synthesis",
            ]
            for marker in fallback_markers:
                pos = _find_section_start(
                    full_text[search_from:], marker, require_standalone=False
                )
                if pos is not None:
                    end = search_from + pos
                    strategy = f"methods_to_{marker.lower().replace(' ', '_')}"
                    break
        # Fallback 2: hard cap — prevents runaway extraction
        if end is None or end - start > MAX_METHODS_CHARS:
            end = start + MAX_METHODS_CHARS
            strategy = "methods_hard_capped"

    if start is None or end is None:
        # Fallback: use Inclusion Criteria subsection as anchor
        ic_start = _find_section_start(
            full_text, "Inclusion Criteria", require_standalone=False
        )
        if ic_start is not None:
            start = ic_start
            # End ~10k chars later or at first "Search Strategy" / "Data Sources"
            candidates = [
                _find_section_start(
                    full_text[start + 1 :],
                    k,
                    require_standalone=False,
                )
                for k in (
                    "Search Strategy",
                    "Search Strategies",
                    "Data Sources",
                    "Data Extraction",
                )
            ]
            candidates = [c + start + 1 for c in candidates if c is not None]
            end = min(candidates) if candidates else start + 10000
            strategy = "inclusion_to_search"
        else:
            raise ValueError(
                f"Could not locate Methods or Inclusion Criteria section in {pdf_path}"
            )

    raw = full_text[start:end].strip()
    cleaned = _strip_derp_artifacts(raw)

    diagnostics = {
        "n_pages": n_pages,
        "strategy": strategy,
        "start_pos": start,
        "end_pos": end,
        "n_chars_raw": len(raw),
        "n_chars": len(cleaned),
    }
    return cleaned, diagnostics


def fetch_pdf(url: str, dest: Path, overwrite: bool) -> bool:
    """Download a PDF from Wayback. Returns True on success."""
    if dest.exists() and not overwrite:
        logger.info("derp_pdf_skipped", drug=dest.stem, reason="exists")
        return True
    logger.info("derp_pdf_fetching", drug=dest.stem, url=url[:80] + "...")
    try:
        with httpx.Client(timeout=180.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            if not resp.content.startswith(b"%PDF"):
                logger.error(
                    "derp_pdf_not_pdf",
                    drug=dest.stem,
                    first_bytes=resp.content[:16].hex(),
                )
                return False
            dest.write_bytes(resp.content)
        logger.info(
            "derp_pdf_downloaded",
            drug=dest.stem,
            size_bytes=dest.stat().st_size,
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("derp_pdf_error", drug=dest.stem, err=str(e))
        return False


def process_one(drug: str, url: str, *, overwrite: bool) -> dict:
    """Download + extract methods for one DERP topic."""
    pdf_path = PDF_DIR / f"{drug}.pdf"
    out_path = METHODS_DIR / f"Cohen_{drug}_methods.txt"

    if not fetch_pdf(url, pdf_path, overwrite):
        return {"drug": drug, "status": "download_failed"}

    try:
        text, diag = extract_derp_methods(pdf_path)
    except Exception as e:  # noqa: BLE001
        logger.error("derp_extract_failed", drug=drug, err=str(e))
        return {"drug": drug, "status": "extract_failed", "err": str(e)}

    out_path.write_text(text, encoding="utf-8")
    return {
        "drug": drug,
        "status": "ok",
        "pdf_size": pdf_path.stat().st_size,
        "methods_chars": diag["n_chars"],
        "strategy": diag["strategy"],
        "n_pages": diag["n_pages"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drugs",
        type=str,
        default=None,
        help="Comma-separated drug names (default: all 13 with Wayback URLs).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download PDFs even if they already exist on disk.",
    )
    args = parser.parse_args()

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    METHODS_DIR.mkdir(parents=True, exist_ok=True)

    if args.drugs:
        targets = [d.strip() for d in args.drugs.split(",")]
    else:
        targets = [d for d, u in DERP_URLS.items() if u is not None]

    print(f"DERP fetch+extract — {len(targets)} drugs")
    print()

    summaries: list[dict] = []
    for i, drug in enumerate(targets, 1):
        url = DERP_URLS.get(drug)
        if url is None:
            print(f"[{i}/{len(targets)}] {drug} — ❌ NO URL (handle with fallback)")
            summaries.append({"drug": drug, "status": "no_url"})
            continue
        print(f"[{i}/{len(targets)}] {drug} ...", end=" ", flush=True)
        s = process_one(drug, url, overwrite=args.overwrite)
        summaries.append(s)
        if s["status"] == "ok":
            print(
                f"OK | {s['n_pages']}pg | methods={s['methods_chars']} chars "
                f"| strategy={s['strategy']}"
            )
        else:
            print(f"FAILED: {s['status']} {s.get('err','')[:60]}")
        time.sleep(2)  # polite to archive.org

    # Summary
    n_ok = sum(1 for s in summaries if s["status"] == "ok")
    print(f"\n{'='*70}\n  {n_ok}/{len(summaries)} successful\n{'='*70}")

    (PDF_DIR.parent / "derp_fetch_summary.json").write_text(
        json.dumps(summaries, indent=2)
    )


if __name__ == "__main__":
    main()
