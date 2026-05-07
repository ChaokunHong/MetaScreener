from __future__ import annotations

import json
from pathlib import Path

import pytest

from metascreener.module1_screening.ms_active.feature_store import (
    LoadedActiveDataset,
    load_active_dataset,
)
from metascreener.module1_screening.ms_active.models import RecordLabel
from metascreener.module1_screening.ms_active.rankers import (
    TextFeatureLogisticRanker,
    TfidfLogisticRanker,
)
from metascreener.module1_screening.ms_active.simulator import (
    ActiveLearningConfig,
    run_active_learning,
)


def _write_result_json(path: Path, *, dataset: str = "D1") -> None:
    payload = {
        "dataset": dataset,
        "results": [
            {
                "record_id": "r1",
                "true_label": 1,
                "p_include": 0.9,
                "final_score": 0.9,
                "ecs_final": 0.8,
                "exclude_certainty_passes": True,
                "sprt_early_stop": False,
                "asreview_score": 0.99,
            },
            {
                "record_id": "r2",
                "true_label": 0,
                "p_include": 0.1,
                "final_score": 0.1,
                "ecs_final": 0.2,
            },
            {
                "record_id": "r3",
                "true_label": None,
                "p_include": 0.5,
                "final_score": 0.5,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_records_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "record_id,title,abstract,label_included",
                "r1,Eligible trial,Randomized outcome trial,1",
                "r2,Excluded editorial,Background commentary,0",
                "r3,Unlabelled,No adjudicated label,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_load_active_dataset_joins_result_json_to_records_csv(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    _write_records_csv(records_path)

    loaded = load_active_dataset(result_path, records_path, dataset="D1")

    assert isinstance(loaded, LoadedActiveDataset)
    assert loaded.dataset == "D1"
    assert loaded.raw_result_count == 3
    assert loaded.skipped_unlabelled == 1
    assert [(skip.record_id, skip.reason) for skip in loaded.skipped_records] == [
        ("r3", "missing_true_label")
    ]
    assert loaded.n_includes == 1
    assert loaded.n_excludes == 1
    assert [record.record_id for record in loaded.records] == ["r1", "r2"]
    assert [record.true_label for record in loaded.records] == [
        RecordLabel.INCLUDE,
        RecordLabel.EXCLUDE,
    ]
    assert loaded.records[0].text == "Eligible trial\n\nRandomized outcome trial"
    assert loaded.records[0].features["exclude_certainty_passes"] == 1.0
    assert loaded.records[0].features["sprt_early_stop"] == 0.0
    assert "asreview_score" not in loaded.records[0].features


def test_load_active_dataset_rejects_dataset_mismatch(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path, dataset="Other")
    _write_records_csv(records_path)

    with pytest.raises(ValueError, match="dataset mismatch"):
        load_active_dataset(result_path, records_path, dataset="D1")


def test_load_active_dataset_rejects_non_binary_labels(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["results"][0]["true_label"] = 2
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    _write_records_csv(records_path)

    with pytest.raises(ValueError, match="binary include/exclude"):
        load_active_dataset(result_path, records_path, dataset="D1")


def test_load_active_dataset_rejects_one_class_loaded_dataset(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    for row in payload["results"]:
        if row["true_label"] is not None:
            row["true_label"] = 0
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    records_path.write_text(
        "\n".join(
            [
                "record_id,title,abstract,label_included",
                "r1,Eligible trial,Randomized outcome trial,0",
                "r2,Excluded editorial,Background commentary,0",
                "r3,Unlabelled,No adjudicated label,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="both INCLUDE and EXCLUDE"):
        load_active_dataset(result_path, records_path, dataset="D1")


def test_load_active_dataset_rejects_missing_records_csv_row(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    records_path.write_text(
        "record_id,title,abstract,label_included\nr1,Eligible trial,Abstract,1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing from records.csv"):
        load_active_dataset(result_path, records_path, dataset="D1")


@pytest.mark.parametrize("feature_key", ["ms_score", "asreview_score", "label_included"])
def test_load_active_dataset_rejects_invalid_requested_feature_keys(
    tmp_path: Path,
    feature_key: str,
) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    _write_records_csv(records_path)

    with pytest.raises(ValueError, match="Unsupported MS-Screen|leakage feature"):
        load_active_dataset(
            result_path,
            records_path,
            dataset="D1",
            feature_keys=(feature_key,),
        )


def test_load_active_dataset_rejects_malformed_result_schema(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    result_path.write_text(json.dumps({"dataset": "D1"}), encoding="utf-8")
    _write_records_csv(records_path)

    with pytest.raises(ValueError, match="results list"):
        load_active_dataset(result_path, records_path, dataset="D1")


def test_load_active_dataset_rejects_non_binary_records_csv_label(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    _write_records_csv(records_path)
    records_path.write_text(
        "\n".join(
            [
                "record_id,title,abstract,label_included",
                "r1,Eligible trial,Randomized outcome trial,maybe",
                "r2,Excluded editorial,Background commentary,0",
                "r3,Unlabelled,No adjudicated label,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="label_included"):
        load_active_dataset(result_path, records_path, dataset="D1")


def test_load_active_dataset_rejects_label_disagreement(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    records_path.write_text(
        "\n".join(
            [
                "record_id,title,abstract,label_included",
                "r1,Eligible trial,Abstract,0",
                "r2,Excluded editorial,Abstract,0",
                "r3,Unlabelled,Abstract,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="label disagreement"):
        load_active_dataset(result_path, records_path, dataset="D1")


def test_load_active_dataset_rejects_duplicate_result_record_ids(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["results"].append(dict(payload["results"][0]))
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    _write_records_csv(records_path)

    with pytest.raises(ValueError, match="duplicate record_id"):
        load_active_dataset(result_path, records_path, dataset="D1")


def test_load_active_dataset_rejects_duplicate_records_csv_ids(tmp_path: Path) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    _write_records_csv(records_path)
    with records_path.open("a", encoding="utf-8") as handle:
        handle.write("r1,Duplicate,Duplicate abstract,1\n")

    with pytest.raises(ValueError, match="duplicate record_id"):
        load_active_dataset(result_path, records_path, dataset="D1")


def test_load_active_dataset_omits_null_features_and_rejects_non_numeric(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "a13b_coverage_rule.json"
    records_path = tmp_path / "records.csv"
    _write_result_json(result_path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["results"][0]["p_include"] = None
    payload["results"][1]["final_score"] = "bad"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    _write_records_csv(records_path)

    with pytest.raises(ValueError, match="must be numeric"):
        load_active_dataset(result_path, records_path, dataset="D1")


def test_load_active_dataset_smoke_runs_a1_a2_on_real_fixture() -> None:
    result_path = Path("experiments/results/Muthu_2021/a13b_coverage_rule.json")
    records_path = Path("experiments/datasets/Muthu_2021/records.csv")
    if not result_path.exists() or not records_path.exists():
        pytest.skip("real Muthu_2021 fixture is not available")

    loaded = load_active_dataset(result_path, records_path, dataset="Muthu_2021")
    includes = [record for record in loaded.records if record.true_label is RecordLabel.INCLUDE]
    excludes = [record for record in loaded.records if record.true_label is RecordLabel.EXCLUDE]
    assert includes
    assert excludes
    subset = tuple(includes[:2] + excludes[:10])
    assert all(record.text for record in subset)

    a1 = run_active_learning(
        subset,
        dataset="Muthu_2021",
        ranker=TfidfLogisticRanker(random_state=42),
        config=ActiveLearningConfig(base_seed=42, target_recall=0.95),
    )
    a2 = run_active_learning(
        subset,
        dataset="Muthu_2021",
        ranker=TextFeatureLogisticRanker(
            feature_keys=("p_include", "final_score", "ecs_final"),
            random_state=42,
        ),
        config=ActiveLearningConfig(base_seed=42, target_recall=0.95),
    )

    assert a1.human_work == len(subset)
    assert a2.human_work == len(subset)
    assert len(a1.events) == len(subset)
    assert len(a2.events) == len(subset)
