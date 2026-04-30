#!/usr/bin/env python3
"""Combine multiple FP adjudication CSVs into a majority-vote table.

Each input should be the output of ``fp_adjudicate_llm.py`` for the same sample
CSV. Inputs are passed as ``model_id=path`` pairs so the output keeps
per-adjudicator verdicts and reasons.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

VALID_VERDICTS = {"label_error", "genuine_fp", "ambiguous"}


def majority_vote(verdicts: list[str]) -> tuple[str, str, int]:
    """Return (majority_verdict, agreement, n_valid_judges)."""
    cleaned = [v.strip().lower() for v in verdicts if v.strip().lower() in VALID_VERDICTS]
    n_valid = len(cleaned)
    if not cleaned:
        return ("error", "0/0", 0)
    counts = Counter(cleaned)
    verdict, n_top = counts.most_common(1)[0]
    if n_top >= 2:
        return (verdict, f"{n_top}/{n_valid}", n_valid)
    return ("ambiguous", f"no_majority/{n_valid}", n_valid)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _parse_input(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "inputs must be model_id=path, e.g. nous-hermes4=filled.csv"
        )
    model, path = value.split("=", 1)
    model = model.strip()
    if not model:
        raise argparse.ArgumentTypeError("model_id cannot be empty")
    return model, Path(path)


def combine(inputs: list[tuple[str, Path]]) -> tuple[list[dict[str, str]], dict]:
    """Combine adjudication files keyed by (dataset, record_id)."""
    if len(inputs) < 2:
        raise ValueError("at least two adjudication files are required")

    loaded = [(model, _read_csv(path)) for model, path in inputs]
    base_model, base_rows = loaded[0]
    del base_model
    by_model: dict[str, dict[tuple[str, str], dict[str, str]]] = {}
    for model, rows in loaded:
        keyed: dict[tuple[str, str], dict[str, str]] = {}
        for row in rows:
            key = (row.get("dataset", ""), row.get("record_id", ""))
            keyed[key] = row
        by_model[model] = keyed

    out_rows: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    agreement_counts: Counter[str] = Counter()
    for base in base_rows:
        key = (base.get("dataset", ""), base.get("record_id", ""))
        out = {
            k: v
            for k, v in base.items()
            if k not in {"verdict", "reason"}
        }
        verdicts: list[str] = []
        reasons: list[str] = []
        for model, _path in inputs:
            row = by_model[model].get(key, {})
            verdict = (row.get("verdict") or "").strip().lower()
            reason = row.get("reason") or ""
            out[f"{model}_verdict"] = verdict
            out[f"{model}_reason"] = reason
            verdicts.append(verdict)
            if verdict in VALID_VERDICTS and reason:
                reasons.append(f"{model}: {reason}")
        majority, agreement, n_valid = majority_vote(verdicts)
        out["majority_verdict"] = majority
        out["agreement"] = agreement
        out["n_valid_judges"] = str(n_valid)
        out["majority_reason"] = " | ".join(reasons)[:1000]
        out_rows.append(out)
        counts[majority] += 1
        agreement_counts[agreement] += 1

    summary = {
        "n_rows": len(out_rows),
        "models": [model for model, _ in inputs],
        "majority_counts": dict(counts),
        "agreement_counts": dict(agreement_counts),
    }
    return out_rows, summary


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", type=_parse_input, required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--summary-output", required=True)
    args = ap.parse_args()

    rows, summary = combine(args.input)
    write_csv(rows, Path(args.output))
    Path(args.summary_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary_output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} rows -> {args.output}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
