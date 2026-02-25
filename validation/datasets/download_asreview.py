"""Download ASReview Synergy dataset.

Source: ASReview Synergy Dataset
https://github.com/asreview/synergy-dataset

26 labeled systematic review datasets for benchmarking active
learning and screening automation.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

# All 26 datasets from ASReview Synergy
SYNERGY_DATASETS: list[str] = [
    "Appenzeller-Herzog_2019",
    "Bos_2018",
    "Brouwer_2019",
    "Cormack_2016",
    "De_Vet_2006",
    "Donners_2021",
    "Hall_2012",
    "Jeyaraman_2020",
    "Kitchenham_2010",
    "Kwok_2020",
    "Leenaars_2019",
    "Meijboom_2021",
    "Moran_2014",
    "Muthu_2021",
    "Nagtegaal_2019",
    "Nelson_2002",
    "Oud_2018",
    "Radjenovic_2013",
    "Sep_2021",
    "Smits_2022",
    "Van_de_Schoot_2017",
    "Van_der_Valk_2021",
    "Van_Dis_2020",
    "Valk_2021",
    "Wassenaar_2017",
    "Wolters_2018",
]

BASE_URL = "https://raw.githubusercontent.com/asreview/synergy-dataset/master/datasets"

DEFAULT_OUTPUT_DIR: Path = Path(__file__).parent / "asreview"


def download_asreview(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    """Download all 26 ASReview Synergy dataset CSV files.

    Each dataset is downloaded from the ASReview GitHub repository.
    Files that already exist locally are skipped.

    Args:
        output_dir: Directory to save downloaded CSV files.
            Defaults to ``validation/datasets/asreview/``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "asreview_download_started",
        output_dir=str(output_dir),
        n_datasets=len(SYNERGY_DATASETS),
    )

    downloaded = 0
    skipped = 0

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for dataset_name in SYNERGY_DATASETS:
            output_path = output_dir / f"{dataset_name}.csv"

            if output_path.exists():
                logger.info(
                    "asreview_dataset_skipped",
                    dataset=dataset_name,
                    reason="already_exists",
                )
                skipped += 1
                continue

            url = f"{BASE_URL}/{dataset_name}/{dataset_name}.csv"
            logger.info(
                "asreview_dataset_downloading",
                dataset=dataset_name,
                url=url,
            )

            response = client.get(url)
            response.raise_for_status()

            output_path.write_bytes(response.content)
            logger.info(
                "asreview_dataset_downloaded",
                dataset=dataset_name,
                size_bytes=len(response.content),
                path=str(output_path),
            )
            downloaded += 1

    logger.info(
        "asreview_download_complete",
        downloaded=downloaded,
        skipped=skipped,
        total=len(SYNERGY_DATASETS),
    )


if __name__ == "__main__":
    download_asreview()
