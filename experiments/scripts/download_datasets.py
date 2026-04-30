"""Download 15 SYNERGY datasets to experiments/datasets/.

Saves for each dataset:
  - records.csv  (record_id, title, abstract, label_included)
  - metadata.json (N, n_include, inc_rate, pub_title, concepts)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from synergy_dataset import Dataset

SELECTED_DATASETS = [
    # Already downloaded (15):
    "Walker_2018",
    "Brouwer_2019",
    "van_Dis_2020",
    "Hall_2012",
    "Wassenaar_2017",
    "Leenaars_2020",
    "Radjenovic_2013",
    "Moran_2021",
    "van_de_Schoot_2018",
    "Muthu_2021",
    "Appenzeller-Herzog_2019",
    "Smid_2020",
    "van_der_Waal_2022",
    "Chou_2003",
    "Jeyaraman_2020",
    # Remaining 11 from SYNERGY (total 26 = full SYNERGY coverage):
    "Bos_2018",
    "Leenaars_2019",
    "Wolters_2018",
    "Chou_2004",
    "Oud_2018",
    "Meijboom_2021",
    "Donners_2021",
    "Menon_2022",
    "van_der_Valk_2021",
    "Sep_2021",
    "Nelson_2002",
]

OUT_DIR = Path(__file__).parent.parent / "datasets"


def download_one(name: str) -> dict:
    ds_dir = OUT_DIR / name
    csv_path = ds_dir / "records.csv"
    meta_path = ds_dir / "metadata.json"
    if csv_path.exists() and meta_path.exists():
        with open(meta_path) as f:
            existing = json.load(f)
        print(f"  {name} already present (N={existing.get('N','?')}) — SKIP")
        return existing
    print(f"  Downloading {name} ...", end=" ", flush=True)
    ds = Dataset(name)
    meta = ds.metadata
    data_meta = meta.get("data", {})
    pub = meta.get("publication", {})

    n_total = data_meta.get("n_records", 0)
    n_include = data_meta.get("n_records_included", 0)
    concepts = data_meta.get("concepts", {}).get("included", [])
    topic = concepts[0]["display_name"] if concepts else "N/A"
    pub_title = pub.get("title", "N/A")

    # Save directory
    ds_dir = OUT_DIR / name
    ds_dir.mkdir(parents=True, exist_ok=True)

    # Fetch records via to_dict (includes label_included)
    records_dict = ds.to_dict(variables=["doi", "title", "abstract"])

    # Write records.csv
    csv_path = ds_dir / "records.csv"
    fieldnames = ["record_id", "title", "abstract", "label_included"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for openalex_id, rec in records_dict.items():
            writer.writerow({
                "record_id": openalex_id,
                "title": rec.get("title") or "",
                "abstract": rec.get("abstract") or "",
                "label_included": int(rec.get("label_included", 0)),
            })

    actual_n = len(records_dict)
    actual_inc = sum(
        1 for r in records_dict.values() if r.get("label_included", 0) == 1
    )

    # Write metadata.json
    meta_out = {
        "dataset": name,
        "N": actual_n,
        "n_include": actual_inc,
        "inc_rate": round(actual_inc / actual_n, 6) if actual_n > 0 else 0.0,
        "pub_title": pub_title,
        "topic": topic,
        "pub_year": pub.get("publication_year"),
    }
    with open(ds_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta_out, f, indent=2, ensure_ascii=False)

    print(f"N={actual_n}, included={actual_inc} ({actual_inc/actual_n:.1%})")
    return meta_out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving to {OUT_DIR}\n")

    results = []
    failed = []
    for name in SELECTED_DATASETS:
        try:
            r = download_one(name)
            results.append(r)
        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            failed.append(name)

    print(f"\n=== Download complete: {len(results)}/{len(SELECTED_DATASETS)} ===")
    print("\nFull publication titles:")
    for r in results:
        print(f"  [{r['dataset']}]  {r['pub_title']}")

    if failed:
        print(f"\nFailed: {failed}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
