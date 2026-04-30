"""Run ASReview v3 simulation on all 26 SYNERGY datasets for head-to-head
comparison with MetaScreener A13b.

Protocol (van de Schoot et al. 2021, Nature Machine Intelligence):
  - Classifier: Naive Bayes
  - Feature extractor: TF-IDF
  - Query strategy: max
  - Balancer: balanced
  - Prior: 1 include + 1 exclude (randomly sampled by prior-seed)
  - 5 random seeds per dataset (different prior-seed per run)
  - Metrics: WSS@85, WSS@95, Recall@10/25/50% records reviewed, AUROC

Results saved as JSON per (dataset, seed) in experiments/results/asreview_benchmark/.

Usage:
  uv run python experiments/scripts/run_asreview_benchmark.py                       # all
  uv run python experiments/scripts/run_asreview_benchmark.py --datasets Donners_2021
  uv run python experiments/scripts/run_asreview_benchmark.py --seeds 42            # 1 seed only
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = PROJECT_ROOT / "experiments" / "datasets"
OUT_DIR = PROJECT_ROOT / "experiments" / "results" / "asreview_benchmark"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = [
    "Donners_2021", "Sep_2021", "Nelson_2002", "van_der_Valk_2021",
    "Meijboom_2021", "Oud_2018", "Menon_2022", "Jeyaraman_2020",
    "Chou_2004", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "Wolters_2018",
    "van_de_Schoot_2018", "Bos_2018", "Moran_2021", "Leenaars_2019",
    "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017", "Hall_2012",
    "van_Dis_2020", "Brouwer_2019", "Walker_2018",
]

SEEDS = [42, 123, 456, 789, 2024]


def _count_includes(csv_path: Path) -> tuple[int, int]:
    n_total = 0
    n_inc = 0
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            n_total += 1
            if int(row.get("label_included", 0)) == 1:
                n_inc += 1
    return n_total, n_inc


def _parse_asreview_output(
    asreview_file: Path, n_total: int, n_inc: int,
) -> dict:
    """Extract review order + compute WSS / Recall / AUROC from an .asreview zip."""
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(asreview_file) as z:
            z.extractall(tmp)
        conn = sqlite3.connect(str(Path(tmp) / "results.db"))
        cur = conn.cursor()
        rows = list(cur.execute(
            "SELECT r.time, r.record_id, r.label, rec.dataset_row "
            "FROM results r JOIN record rec ON r.record_id = rec.record_id "
            "ORDER BY r.time ASC"
        ))
        # last_ranking: remaining unreviewed records with final model score
        last_ranking = list(cur.execute(
            "SELECT record_id, ranking FROM last_ranking ORDER BY ranking DESC"
        ))

    reviewed_records = len(rows)
    reviewed_includes = sum(1 for _, _, l, _ in rows if l == 1)

    # WSS and Recall metrics
    result = {
        "n_total": n_total,
        "n_includes": n_inc,
        "reviewed_records": reviewed_records,
        "reviewed_includes": reviewed_includes,
        "final_recall": reviewed_includes / n_inc if n_inc else 0.0,
    }

    # Cumulative recall curve over reviewed records
    found = 0
    for target in [0.85, 0.90, 0.95]:
        target_count = math.ceil(target * n_inc)
        found_local = 0
        records_at_target = None
        for i, (_, _, label, _) in enumerate(rows, 1):
            if label == 1:
                found_local += 1
            if found_local >= target_count:
                records_at_target = i
                break
        if records_at_target is None:
            result[f"wss_{int(target*100)}"] = None
            result[f"records_at_recall_{int(target*100)}"] = None
        else:
            wss = (1.0 - records_at_target / n_total) - (1.0 - target)
            result[f"wss_{int(target*100)}"] = round(wss, 4)
            result[f"records_at_recall_{int(target*100)}"] = records_at_target

    # Recall @ X% of records reviewed
    for frac in [0.05, 0.10, 0.25, 0.50]:
        cutoff = math.ceil(frac * n_total)
        found_local = 0
        for i, (_, _, label, _) in enumerate(rows, 1):
            if i > cutoff:
                break
            if label == 1:
                found_local += 1
        # Records beyond reviewed_records but within cutoff contribute 0 to recall
        recall = found_local / n_inc if n_inc else 0.0
        result[f"recall_at_{int(frac*100)}pct"] = round(recall, 4)

    return result


def run_one(
    dataset: str, seed: int, ai_preset: str | None = None,
    timeout_s: int = 7200,
) -> dict | None:
    """Run a single ASReview simulation.

    Args:
        dataset: SYNERGY dataset name.
        seed: Random seed for model + prior.
        ai_preset: If given (e.g. 'elas_u4'), use ASReview's built-in AI preset
            (the hyperparameter-tuned default). If None, use the NB+TF-IDF
            configuration matching van de Schoot 2021 Nature Machine
            Intelligence paper.
    """
    csv_path = DATASETS_DIR / dataset / "records.csv"
    suffix = f"_{ai_preset}" if ai_preset else ""
    out_path = OUT_DIR / f"{dataset}_seed{seed}{suffix}.asreview"
    metric_path = OUT_DIR / f"{dataset}_seed{seed}{suffix}.json"

    if metric_path.exists():
        with open(metric_path) as f:
            return json.load(f)

    n_total, n_inc = _count_includes(csv_path)
    if n_inc < 2:
        print(f"  SKIP {dataset} (fewer than 2 includes, cannot prior-sample)")
        return None

    # ASReview v3 leaves a `<out>.asreview.tmp` directory when a simulation is
    # killed / times out. A subsequent run with the same output path fails
    # instantly with a truncated traceback. Since we only reach this point when
    # the final .json does NOT exist (see early-return above), this exact run
    # is not yet complete, so removing any stale .tmp dir with the same path
    # is safe — no concurrent writer can own it at this instant.
    tmp_dir = Path(f"{out_path}.tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    t0 = time.time()
    cmd = [
        "uv", "run", "--project", str(PROJECT_ROOT), "asreview", "simulate",
        str(csv_path),
        "--n-prior-included", "1",
        "--n-prior-excluded", "1",
        "--prior-seed", str(seed),
        "--seed", str(seed),
        "--output", str(out_path),
    ]
    if ai_preset:
        cmd += ["--ai", ai_preset]
    else:
        cmd += [
            "--classifier", "nb",
            "--feature-extractor", "tfidf",
            "--querier", "max",
            "--balancer", "balanced",
        ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT {dataset} seed={seed}")
        return {"dataset": dataset, "seed": seed, "status": "timeout"}

    wall_s = time.time() - t0
    if result.returncode != 0:
        print(f"  FAIL {dataset} seed={seed}: {result.stderr[:300]}")
        return {"dataset": dataset, "seed": seed, "status": "failed",
                "stderr": result.stderr[:1000]}

    metrics = _parse_asreview_output(out_path, n_total, n_inc)
    metrics.update({
        "dataset": dataset,
        "seed": seed,
        "wall_time_s": round(wall_s, 1),
        "status": "ok",
    })
    # save .json, keep .asreview zip for reproducibility
    with open(metric_path, "w") as f:
        json.dump(metrics, f, indent=2)
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", type=str, default=",".join(DATASETS))
    parser.add_argument("--seeds", type=str, default=",".join(str(s) for s in SEEDS))
    parser.add_argument("--ai", type=str, default=None,
                        help="ASReview AI preset (e.g. 'elas_u4' for v3 default). "
                        "If omitted, uses NB+TF-IDF (van de Schoot 2021 replication).")
    parser.add_argument("--timeout", type=int, default=7200,
                        help="Per-run subprocess timeout in seconds (default 7200 = 2h)")
    args = parser.parse_args()

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]

    total = len(datasets) * len(seeds)
    label = args.ai if args.ai else "NB+TF-IDF (van de Schoot 2021 baseline)"
    print(f"ASReview benchmark: {len(datasets)} datasets × {len(seeds)} seeds = {total} runs")
    print(f"Config: {label}, 1 inc / 1 exc prior")
    print()

    summary = []
    t_start = time.time()
    for i, ds in enumerate(datasets, 1):
        for j, seed in enumerate(seeds, 1):
            idx = (i-1) * len(seeds) + j
            print(f"[{idx}/{total}] {ds} seed={seed} ...", flush=True)
            res = run_one(ds, seed, ai_preset=args.ai, timeout_s=args.timeout)
            if res:
                summary.append(res)
                if res.get("status") == "ok":
                    wss95 = res.get("wss_95")
                    recall = res.get("final_recall", 0)
                    print(f"  WSS@95={wss95:.3f}  recall={recall:.3f}  time={res['wall_time_s']}s")

    print(f"\nTotal time: {(time.time()-t_start)/60:.1f} min")
    # Write aggregate summary
    suffix = f"_{args.ai}" if args.ai else ""
    agg_path = OUT_DIR / f"summary{suffix}.json"
    with open(agg_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Aggregate saved: {agg_path}")


if __name__ == "__main__":
    main()
