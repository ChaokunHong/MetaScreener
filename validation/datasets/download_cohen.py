"""Download Cohen 2006 benchmark dataset.

Source: Cohen et al. (2006) "Reducing Workload in Systematic Review
Preparation Using Automated Citation Classification" -- JAMIA.

15 systematic review topics with ~14,000 labeled papers.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

# All 15 systematic review topics from the Cohen 2006 benchmark
COHEN_TOPICS: list[str] = [
    "ACEInhibitors",
    "ADHD",
    "Antihistamines",
    "AtypicalAntipsychotics",
    "BetaBlockers",
    "CalciumChannelBlockers",
    "Estrogens",
    "NSAIDS",
    "Opioids",
    "OralHypoglycemics",
    "ProtonPumpInhibitors",
    "SkeletalMuscleRelaxants",
    "Statins",
    "Triptans",
    "UrinaryIncontinence",
]

BASE_URL = "https://dmice.ohsu.edu/cohenaa/systematic-reviews"

DEFAULT_OUTPUT_DIR: Path = Path(__file__).parent / "cohen"


def download_cohen(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    """Download all 15 Cohen 2006 benchmark topic CSV files.

    Each topic is downloaded from the OHSU DMICE server as a CSV file.
    Files that already exist locally are skipped.

    Args:
        output_dir: Directory to save downloaded CSV files.
            Defaults to ``validation/datasets/cohen/``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "cohen_download_started",
        output_dir=str(output_dir),
        n_topics=len(COHEN_TOPICS),
    )

    downloaded = 0
    skipped = 0

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for topic in COHEN_TOPICS:
            output_path = output_dir / f"{topic}.csv"

            if output_path.exists():
                logger.info("cohen_topic_skipped", topic=topic, reason="already_exists")
                skipped += 1
                continue

            url = f"{BASE_URL}/{topic}.csv"
            logger.info("cohen_topic_downloading", topic=topic, url=url)

            response = client.get(url)
            response.raise_for_status()

            output_path.write_bytes(response.content)
            logger.info(
                "cohen_topic_downloaded",
                topic=topic,
                size_bytes=len(response.content),
                path=str(output_path),
            )
            downloaded += 1

    logger.info(
        "cohen_download_complete",
        downloaded=downloaded,
        skipped=skipped,
        total=len(COHEN_TOPICS),
    )


if __name__ == "__main__":
    download_cohen()
