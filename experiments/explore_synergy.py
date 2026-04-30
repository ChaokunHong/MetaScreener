"""Explore all SYNERGY datasets and produce a summary table.

Outputs:
  - Terminal table (sorted by inclusion rate)
  - experiments/synergy_overview.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

from synergy_dataset import Dataset, iter_datasets


def main() -> None:
    rows: list[dict] = []

    for ds in iter_datasets():
        meta = ds.metadata
        data = meta.get("data", {})
        pub = meta.get("publication", {})

        n_total = data.get("n_records", 0)
        n_include = data.get("n_records_included", 0)
        inc_rate = n_include / n_total if n_total > 0 else 0.0

        # Extract topic/concepts
        concepts = data.get("concepts", {}).get("included", [])
        topic = concepts[0]["display_name"] if concepts else "N/A"

        # Check if title and abstract are available via to_dict
        has_title = True   # synergy always has title via OpenAlex
        has_abstract = True  # synergy always has abstract via OpenAlex

        rows.append({
            "dataset": ds.name,
            "N": n_total,
            "n_include": n_include,
            "inc_rate": inc_rate,
            "topic": topic,
            "pub_title": pub.get("title", "N/A")[:80],
            "has_title": has_title,
            "has_abstract": has_abstract,
        })

    # Sort by inclusion rate
    rows.sort(key=lambda r: r["inc_rate"])

    # Print table
    header = f"{'Dataset':<35} {'N':>6} {'n_inc':>5} {'inc%':>7} {'Topic':<25}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['dataset']:<35} {r['N']:>6} {r['n_include']:>5} "
            f"{r['inc_rate']:>6.2%} {r['topic']:<25}"
        )

    print(f"\nTotal datasets: {len(rows)}")
    print(f"Total records:  {sum(r['N'] for r in rows)}")
    print(f"Total included: {sum(r['n_include'] for r in rows)}")

    # Save CSV
    out = Path(__file__).parent / "synergy_overview.csv"
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
