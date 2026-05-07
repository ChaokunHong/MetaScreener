from __future__ import annotations

import json
from pathlib import Path

from metascreener.module1_screening.ms_active.batch import DatasetInput


def write_result_json(path: Path, *, dataset: str, extra_exclude: bool = False) -> None:
    rows = [
        {
            "record_id": "r1",
            "true_label": 1,
            "p_include": 0.9,
            "final_score": 0.9,
            "ecs_final": 0.8,
        },
        {
            "record_id": "r2",
            "true_label": 0,
            "p_include": 0.1,
            "final_score": 0.1,
            "ecs_final": 0.2,
        },
    ]
    if extra_exclude:
        rows.append(
            {
                "record_id": "r3",
                "true_label": 0,
                "p_include": 0.2,
                "final_score": 0.2,
                "ecs_final": 0.3,
            }
        )
    path.write_text(json.dumps({"dataset": dataset, "results": rows}), encoding="utf-8")


def write_records_csv(path: Path, *, extra_exclude: bool = False) -> None:
    rows = [
        "record_id,title,abstract,label_included",
        "r1,Eligible trial,Randomized outcome trial,1",
        "r2,Excluded editorial,Background commentary,0",
    ]
    if extra_exclude:
        rows.append("r3,Excluded case report,Background case,0")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def dataset_input(
    tmp_path: Path,
    dataset: str = "D1",
    *,
    extra_exclude: bool = False,
) -> DatasetInput:
    result_path = tmp_path / f"{dataset}_a13b.json"
    records_path = tmp_path / f"{dataset}_records.csv"
    write_result_json(result_path, dataset=dataset, extra_exclude=extra_exclude)
    write_records_csv(records_path, extra_exclude=extra_exclude)
    return DatasetInput(
        dataset=dataset,
        result_json_path=result_path,
        records_csv_path=records_path,
    )
