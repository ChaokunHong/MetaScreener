"""Download records + labels for external validation datasets.

Sources:
  - Cohen 2006 (15 drug SR topics) — OHSU TSV + PubMed efetch
  - CLEF 2019 Task 2 Testing (20 Cochrane intervention reviews) — CLEF-TAR qrels + PubMed efetch

Output: experiments/datasets/{Cohen_<topic>,CLEF_<topic_id>}/
  - records.csv     (record_id, title, abstract, label_included)
  - metadata.json   (dataset, N, n_include, inc_rate, source, pub_title, topic_id)

Label choice:
  - Cohen: `article_triage` column (final post-full-text decision). The TSV
    also has `abstract_triage` — preserved in metadata.json under
    `n_include_abstract` for reference, but not used as the primary label.
  - CLEF: `relevance` from the `.abs.` qrels file (abstract-level binary).

PubMed rate limiting: 3 req/s without NCBI_API_KEY, 10 req/s with.
Batch size: 200 PMIDs per efetch call.

Usage:
  python experiments/scripts/download_external_records.py --source both
  python experiments/scripts/download_external_records.py --source cohen --dry-run
  NCBI_API_KEY=xxx python experiments/scripts/download_external_records.py --source clef
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

COHEN_TSV_URL = "https://dmice.ohsu.edu/cohenaa/epc-ir-data/epc-ir.clean.tsv"
# Primary qrels: content-level (post-full-text inclusion) — matches SYNERGY's
# label_included semantics. The abs.qrels file (abstract-stage) is fetched
# as secondary and stored in metadata for downstream analysis.
CLEF_CONTENT_QRELS_URL = (
    "https://raw.githubusercontent.com/CLEF-TAR/tar/master/"
    "2019-TAR/Task2/Testing/Intervention/qrels/full.test.intervention.content.2019.qrels"
)
CLEF_ABS_QRELS_URL = (
    "https://raw.githubusercontent.com/CLEF-TAR/tar/master/"
    "2019-TAR/Task2/Testing/Intervention/qrels/full.test.intervention.abs.2019.qrels"
)
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

BATCH_SIZE = 200
DEFAULT_OUTPUT_BASE = Path("experiments/datasets")


def _element_text(el: ET.Element | None) -> str:
    """Return concatenated text from an element, including nested children.

    PubMed titles/abstracts often contain inline markup (<i>, <b>, <sub>).
    Plain `.text` misses nested text; `itertext()` captures all of it.
    """
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def _parse_pubmed_xml(xml_bytes: bytes) -> dict[str, dict[str, str]]:
    """Parse PubMed efetch XML into {pmid: {title, abstract}}.

    Records without a PMID or title are skipped.
    """
    root = ET.fromstring(xml_bytes)  # noqa: S314 - NCBI-controlled source
    out: dict[str, dict[str, str]] = {}
    for article in root.iter("PubmedArticle"):
        pmid_el = article.find(".//PMID")
        title_el = article.find(".//ArticleTitle")
        if pmid_el is None or pmid_el.text is None or title_el is None:
            continue

        parts: list[str] = []
        for abs_el in article.findall(".//AbstractText"):
            label = abs_el.get("Label", "")
            text = _element_text(abs_el)
            if label:
                parts.append(f"{label}: {text}")
            else:
                parts.append(text)
        abstract = " ".join(p for p in parts if p).strip()

        out[pmid_el.text] = {
            "title": _element_text(title_el),
            "abstract": abstract,
        }
    return out


def fetch_pubmed(
    pmids: list[str],
    api_key: str | None,
    client: httpx.Client,
) -> dict[str, dict[str, str]]:
    """Batch-fetch title+abstract for a list of PMIDs.

    Returns {pmid: {title, abstract}}. PMIDs not returned by efetch are omitted
    (most likely retracted, withdrawn, or wrong ID).
    """
    sleep_between = 0.11 if api_key else 0.35  # 10/s with key, ~3/s without
    results: dict[str, dict[str, str]] = {}

    for i in range(0, len(pmids), BATCH_SIZE):
        chunk = pmids[i : i + BATCH_SIZE]
        params: dict[str, str] = {
            "db": "pubmed",
            "id": ",".join(chunk),
            "rettype": "abstract",
            "retmode": "xml",
        }
        if api_key:
            params["api_key"] = api_key

        for attempt in range(3):
            try:
                resp = client.get(EFETCH_URL, params=params, timeout=60.0)
                resp.raise_for_status()
                break
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if attempt == 2:
                    logger.error(
                        "efetch_failed",
                        batch_start=i,
                        batch_size=len(chunk),
                        err=str(e),
                    )
                    raise
                backoff = 2 ** attempt
                logger.warning(
                    "efetch_retry", attempt=attempt + 1, backoff_s=backoff, err=str(e)
                )
                time.sleep(backoff)

        parsed = _parse_pubmed_xml(resp.content)
        results.update(parsed)

        if (i // BATCH_SIZE) % 10 == 0 and i > 0:
            logger.info(
                "efetch_progress",
                fetched=len(results),
                processed=i + len(chunk),
                total=len(pmids),
            )
        time.sleep(sleep_between)

    return results


def _write_dataset(
    dataset_name: str,
    pmid_labels: list[tuple[str, int]],
    pubmed_data: dict[str, dict[str, str]],
    output_base: Path,
    source: str,
    topic_id: str,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Write records.csv + metadata.json for one dataset directory.

    Dedupes PMIDs within the dataset (keeping first occurrence). Returns
    {n_written, n_missing, n_include}.
    """
    dataset_dir = output_base / dataset_name
    dataset_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    n_written = 0
    n_missing = 0
    n_include = 0

    records_path = dataset_dir / "records.csv"
    with records_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["record_id", "title", "abstract", "label_included"]
        )
        writer.writeheader()
        for pmid, label in pmid_labels:
            if pmid in seen:
                continue
            seen.add(pmid)
            rec = pubmed_data.get(pmid)
            if rec is None:
                n_missing += 1
                continue
            writer.writerow(
                {
                    "record_id": f"pubmed:{pmid}",
                    "title": rec["title"],
                    "abstract": rec["abstract"],
                    "label_included": label,
                }
            )
            n_written += 1
            if label == 1:
                n_include += 1

    metadata = {
        "dataset": dataset_name,
        "N": n_written,
        "n_include": n_include,
        "inc_rate": round(n_include / n_written, 5) if n_written else 0.0,
        "source": source,
        "topic_id": topic_id,
        "n_missing_pubmed": n_missing,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    (dataset_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    logger.info(
        "dataset_written",
        dataset=dataset_name,
        n_written=n_written,
        n_missing=n_missing,
        n_include=n_include,
        path=str(records_path),
    )
    return {"n_written": n_written, "n_missing": n_missing, "n_include": n_include}


def download_cohen(
    output_base: Path,
    api_key: str | None,
    dry_run: bool,
    overwrite: bool,
) -> None:
    logger.info("cohen_fetch_tsv", url=COHEN_TSV_URL)
    resp = httpx.get(COHEN_TSV_URL, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()

    by_topic: dict[str, list[tuple[str, int, int]]] = {}
    for line in resp.text.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        topic, _endnote, pmid, abstract_triage, article_triage = parts[:5]
        label = 1 if article_triage.strip() == "I" else 0
        abs_label = 1 if abstract_triage.strip() == "I" else 0
        by_topic.setdefault(topic, []).append((pmid, label, abs_label))

    logger.info(
        "cohen_parsed_tsv",
        n_topics=len(by_topic),
        total=sum(len(v) for v in by_topic.values()),
    )

    print("\n=== Cohen 2006 summary ===")
    print(f"{'Topic':<28} {'N':>6} {'Inc(article)':>13} {'Inc(abstract)':>14} {'%':>6}")
    for topic in sorted(by_topic):
        rows = by_topic[topic]
        n = len(rows)
        inc_article = sum(1 for _, a, _ in rows if a == 1)
        inc_abstract = sum(1 for _, _, b in rows if b == 1)
        print(
            f"{topic:<28} {n:>6} {inc_article:>13} {inc_abstract:>14} "
            f"{inc_article / n * 100:>5.1f}%"
        )
    if dry_run:
        print("\n[dry-run] skipping PubMed fetch.")
        return

    with httpx.Client(timeout=120.0) as client:
        for topic in sorted(by_topic):
            dataset_name = f"Cohen_{topic}"
            records_path = output_base / dataset_name / "records.csv"
            if records_path.exists() and not overwrite:
                logger.info(
                    "cohen_topic_skipped",
                    topic=topic,
                    reason="records.csv already exists (use --overwrite to rebuild)",
                )
                continue

            rows = by_topic[topic]
            pmids = [p for p, _, _ in rows]
            pmid_labels = [(p, label) for p, label, _ in rows]
            abstract_label_map = {p: ab for p, _, ab in rows}

            logger.info("cohen_topic_start", topic=topic, n_pmids=len(pmids))
            pubmed_data = fetch_pubmed(pmids, api_key=api_key, client=client)

            n_include_abstract = sum(
                1
                for p in pubmed_data
                if abstract_label_map.get(p) == 1
            )
            extra = {
                "label_description": "article_triage (post-full-text final decision)",
                "n_include_abstract": n_include_abstract,
            }
            _write_dataset(
                dataset_name=dataset_name,
                pmid_labels=pmid_labels,
                pubmed_data=pubmed_data,
                output_base=output_base,
                source="Cohen_2006",
                topic_id=topic,
                extra_metadata=extra,
            )


def _fetch_clef_qrels(url: str) -> dict[str, dict[str, int]]:
    """Fetch a CLEF qrels file and return {topic_id: {pmid: label}}.

    qrels format: ``topic_id 0 pmid relevance`` (whitespace-separated).
    Dedupes within topic (keeps last occurrence in case of dupes).
    """
    logger.info("clef_fetch_qrels", url=url)
    resp = httpx.get(url, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    by_topic: dict[str, dict[str, int]] = {}
    for line in resp.text.strip().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        topic_id, _zero, pmid, rel = parts[0], parts[1], parts[2], parts[3]
        try:
            label = int(rel)
        except ValueError:
            continue
        by_topic.setdefault(topic_id, {})[pmid] = label
    return by_topic


def download_clef(
    output_base: Path,
    api_key: str | None,
    dry_run: bool,
    overwrite: bool,
) -> None:
    content_by_topic = _fetch_clef_qrels(CLEF_CONTENT_QRELS_URL)
    abs_by_topic = _fetch_clef_qrels(CLEF_ABS_QRELS_URL)

    logger.info(
        "clef_parsed_qrels",
        n_topics=len(content_by_topic),
        total_content=sum(len(v) for v in content_by_topic.values()),
        total_abs=sum(len(v) for v in abs_by_topic.values()),
    )

    print("\n=== CLEF 2019 Task 2 Testing summary ===")
    print(f"{'Topic':<14} {'N':>6} {'Inc(content)':>13} {'Inc(abs)':>10} {'%content':>9}")
    for topic_id in sorted(content_by_topic):
        content_labels = content_by_topic[topic_id]
        abs_labels = abs_by_topic.get(topic_id, {})
        n = len(content_labels)
        inc_c = sum(1 for v in content_labels.values() if v == 1)
        inc_a = sum(1 for v in abs_labels.values() if v == 1)
        print(
            f"{topic_id:<14} {n:>6} {inc_c:>13} {inc_a:>10} "
            f"{inc_c / n * 100:>8.1f}%"
        )
    if dry_run:
        print("\n[dry-run] skipping PubMed fetch.")
        return

    with httpx.Client(timeout=120.0) as client:
        for topic_id in sorted(content_by_topic):
            dataset_name = f"CLEF_{topic_id}"
            records_path = output_base / dataset_name / "records.csv"
            if records_path.exists() and not overwrite:
                logger.info(
                    "clef_topic_skipped",
                    topic=topic_id,
                    reason="records.csv already exists (use --overwrite to rebuild)",
                )
                continue

            content_labels = content_by_topic[topic_id]
            abs_labels = abs_by_topic.get(topic_id, {})
            pmids = list(content_labels.keys())
            pmid_labels = [(p, content_labels[p]) for p in pmids]

            logger.info("clef_topic_start", topic=topic_id, n_pmids=len(pmids))
            pubmed_data = fetch_pubmed(pmids, api_key=api_key, client=client)

            n_include_abstract = sum(
                1 for p in pubmed_data if abs_labels.get(p) == 1
            )
            extra = {
                "label_description": "CLEF content.qrels (post full-text inclusion)",
                "n_include_abstract": n_include_abstract,
            }
            _write_dataset(
                dataset_name=dataset_name,
                pmid_labels=pmid_labels,
                pubmed_data=pubmed_data,
                output_base=output_base,
                source="CLEF_2019_Task2_Testing",
                topic_id=topic_id,
                extra_metadata=extra,
            )


def relabel_clef(output_base: Path) -> None:
    """Re-label existing CLEF records.csv files using content.qrels.

    Fast path for when records.csv was originally built from abs.qrels.
    Skips PubMed fetches; updates only label_included + metadata.
    PMIDs not in content.qrels are labeled 0 (treated as excluded).
    """
    content_by_topic = _fetch_clef_qrels(CLEF_CONTENT_QRELS_URL)
    abs_by_topic = _fetch_clef_qrels(CLEF_ABS_QRELS_URL)
    logger.info("clef_relabel_start", n_topics=len(content_by_topic))

    for topic_id in sorted(content_by_topic):
        dataset_name = f"CLEF_{topic_id}"
        dataset_dir = output_base / dataset_name
        records_path = dataset_dir / "records.csv"
        metadata_path = dataset_dir / "metadata.json"
        if not records_path.exists():
            logger.warning("clef_relabel_skipped", topic=topic_id, reason="missing")
            continue

        content_labels = content_by_topic[topic_id]
        abs_labels = abs_by_topic.get(topic_id, {})

        with records_path.open("r", newline="") as f:
            rows = list(csv.DictReader(f))

        n_include_content = 0
        n_include_abs = 0
        with records_path.open("w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["record_id", "title", "abstract", "label_included"]
            )
            writer.writeheader()
            for row in rows:
                pmid = row["record_id"].removeprefix("pubmed:")
                new_label = content_labels.get(pmid, 0)
                row["label_included"] = new_label
                writer.writerow(row)
                if new_label == 1:
                    n_include_content += 1
                if abs_labels.get(pmid) == 1:
                    n_include_abs += 1

        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
        else:
            metadata = {"dataset": dataset_name}
        metadata["N"] = len(rows)
        metadata["n_include"] = n_include_content
        metadata["inc_rate"] = (
            round(n_include_content / len(rows), 5) if rows else 0.0
        )
        metadata["n_include_abstract"] = n_include_abs
        metadata["label_description"] = "CLEF content.qrels (post full-text inclusion)"
        metadata["source"] = "CLEF_2019_Task2_Testing"
        metadata["topic_id"] = topic_id
        metadata_path.write_text(json.dumps(metadata, indent=2))

        logger.info(
            "clef_relabel_done",
            topic=topic_id,
            n=len(rows),
            n_include_content=n_include_content,
            n_include_abs=n_include_abs,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=["cohen", "clef", "both", "relabel-clef"],
        default="both",
        help=(
            "'relabel-clef': re-label existing CLEF records.csv with content.qrels "
            "without re-fetching PubMed (fast fix when downloaded with wrong qrels)."
        ),
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        default=DEFAULT_OUTPUT_BASE,
        help="Base directory for datasets (default: experiments/datasets/)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("NCBI_API_KEY"),
        help="NCBI API key (env NCBI_API_KEY used if unset). "
        "Without one, rate limit is 3 req/s; with one, 10 req/s.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse TSV/qrels and print summary only; skip PubMed fetch.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download and overwrite existing records.csv files.",
    )
    args = parser.parse_args()

    if args.api_key:
        logger.info("ncbi_api_key_detected", rate_limit="10 req/s")
    else:
        logger.info("ncbi_api_key_missing", rate_limit="3 req/s (slower)")

    args.output_base.mkdir(parents=True, exist_ok=True)

    if args.source == "relabel-clef":
        relabel_clef(args.output_base)
        return

    if args.source in ("cohen", "both"):
        download_cohen(args.output_base, args.api_key, args.dry_run, args.overwrite)
    if args.source in ("clef", "both"):
        download_clef(args.output_base, args.api_key, args.dry_run, args.overwrite)


if __name__ == "__main__":
    main()
