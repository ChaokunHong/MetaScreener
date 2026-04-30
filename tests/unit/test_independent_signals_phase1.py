from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from experiments.scripts.independent_signals.b1_lexical import _decision_sweep
from experiments.scripts.independent_signals.b3_full_lodo import (
    _feature_file_complete,
    _lodo_logistic_grid,
    _run_suffix,
    _score_rows_with_workers,
)
from experiments.scripts.independent_signals.b3_seed_protocol import (
    _seed_scores,
    _SeedWork,
    _select_nonself_seeds,
)
from experiments.scripts.independent_signals.common import lexical_score, parse_identifier
from experiments.scripts.independent_signals.encoder_bert import _cosine
from experiments.scripts.independent_signals.encoder_ranker import (
    _lodo_dataset_splits,
    _lodo_ranker_grid,
)
from experiments.scripts.independent_signals.openalex_client import (
    citation_sets,
    metadata_text,
    openalex_api_url,
)


def test_parse_identifier_detects_supported_ids() -> None:
    assert parse_identifier("https://openalex.org/W123").kind == "openalex"
    assert parse_identifier("https://openalex.org/W123").value == "W123"
    assert parse_identifier("pubmed:98765").kind == "pmid"
    assert parse_identifier("doi:10.1000/test").kind == "doi"
    assert parse_identifier("10.1000/test").kind == "doi"
    assert parse_identifier("local-id").kind == "unknown"


def test_lexical_score_combines_fixed_b1_terms() -> None:
    row = {
        "tfidf_include": 0.5,
        "tfidf_title_include": 0.2,
        "tfidf_exclude": 0.1,
        "bm25_delta": 0.3,
    }

    assert lexical_score(row) == pytest.approx(0.9)


def test_decision_sweep_separates_rescue_and_release_risk() -> None:
    rows = [
        {"record_id": "a", "decision": "EXCLUDE", "true_label": 1, "tfidf_include": 1.0},
        {"record_id": "b", "decision": "EXCLUDE", "true_label": 0, "tfidf_include": 0.1},
        {"record_id": "c", "decision": "HUMAN_REVIEW", "true_label": 1, "tfidf_include": 0.0},
        {"record_id": "d", "decision": "HUMAN_REVIEW", "true_label": 0, "tfidf_include": -1.0},
    ]

    sweep = _decision_sweep(rows, [0.5])

    rescue = [row for row in sweep if row["action"] == "rescue_auto_exclude_to_hr"][0]
    release = [row for row in sweep if row["action"] == "release_hr_to_exclude"][0]
    assert rescue["fn_rescued"] == 1
    assert rescue["new_fn"] == 0
    assert release["new_fn"] == 0
    assert release["precision_true_exclude"] == 1.0


def test_openalex_url_uses_supported_urn_formats() -> None:
    assert openalex_api_url(parse_identifier("pubmed:12345")).endswith("/works/pmid:12345")
    assert openalex_api_url(parse_identifier("doi:10.1000/x")).endswith("/works/doi:10.1000%2Fx")


def test_metadata_and_citation_extractors_ignore_title_text() -> None:
    payload = {
        "display_name": "A title that should not be used",
        "type": "article",
        "primary_topic": {"display_name": "Cardiology"},
        "concepts": [{"display_name": "Myocardial infarction"}],
        "mesh": [{"descriptor_name": "Humans"}],
        "referenced_works": ["https://openalex.org/W1"],
        "related_works": ["https://openalex.org/W2"],
    }

    text = metadata_text(payload)
    referenced, related = citation_sets(payload)
    assert "title" not in text.lower()
    assert "Cardiology" in text
    assert referenced == {"https://openalex.org/W1"}
    assert related == {"https://openalex.org/W2"}


def test_encoder_cosine_handles_zero_vectors() -> None:
    assert _cosine(np.asarray([1.0, 0.0]), np.asarray([1.0, 0.0])) == pytest.approx(1.0)
    assert _cosine(np.asarray([0.0, 0.0]), np.asarray([1.0, 0.0])) == 0.0


def test_b3_seed_protocol_excludes_record_itself_from_seed_set() -> None:
    seeds = [
        _SeedWork("https://openalex.org/W1", None),
        _SeedWork("https://openalex.org/W2", None),
        _SeedWork("https://openalex.org/W3", None),
    ]

    selected = _select_nonself_seeds(seeds, "https://openalex.org/W1", 2)

    assert [item.work_id for item in selected] == [
        "https://openalex.org/W2",
        "https://openalex.org/W3",
    ]


def test_b3_seed_scores_separate_direct_and_neighbor_overlap() -> None:
    seed = _SeedWork(
        "https://openalex.org/Wseed",
        {
            "referenced_works": ["https://openalex.org/Wshared"],
            "related_works": ["https://openalex.org/Wcandidate"],
        },
    )

    direct, neighbor_count, neighbor_jaccard = _seed_scores(
        referenced={"https://openalex.org/Wseed", "https://openalex.org/Wshared"},
        related={"https://openalex.org/Wother"},
        record_id="https://openalex.org/Wcandidate",
        seeds=[seed],
    )

    assert direct == 2.0
    assert neighbor_count == 2.0
    assert 0.0 < neighbor_jaccard < 1.0


def test_encoder_ranker_lodo_splits_exclude_heldout_dataset() -> None:
    rows = [
        {"dataset": "A", "true_label": 0},
        {"dataset": "A", "true_label": 1},
        {"dataset": "B", "true_label": 0},
        {"dataset": "B", "true_label": 1},
        {"dataset": "C", "true_label": 0},
    ]

    splits = _lodo_dataset_splits(rows)

    assert {split["heldout"] for split in splits} == {"A", "B", "C"}
    for split in splits:
        heldout = split["heldout"]
        assert all(rows[idx]["dataset"] != heldout for idx in split["train_idx"])
        assert all(rows[idx]["dataset"] == heldout for idx in split["test_idx"])


def test_encoder_ranker_grid_reports_all_c_values() -> None:
    rows = [
        {"dataset": "A", "true_label": 0},
        {"dataset": "A", "true_label": 1},
        {"dataset": "B", "true_label": 0},
        {"dataset": "B", "true_label": 1},
        {"dataset": "C", "true_label": 0},
        {"dataset": "C", "true_label": 1},
    ]
    embeddings = np.asarray([
        [0.0, 0.0],
        [2.0, 0.0],
        [0.0, 0.1],
        [2.0, 0.1],
        [0.0, 0.2],
        [2.0, 0.2],
    ])

    result = _lodo_ranker_grid(rows, embeddings, c_values=[0.1, 1.0])

    assert set(result["c_grid_metrics"]) == {"c_0.1", "c_1.0"}
    assert result["best_c_by_auc"] in {0.1, 1.0}
    assert result["best_metric"]["auc"] == pytest.approx(1.0)


def test_full_lodo_feature_file_complete_requires_all_expected_ids(tmp_path: Path) -> None:
    path = tmp_path / "features.csv"
    path.write_text("record_id\nA\nB\n", encoding="utf-8")

    assert _feature_file_complete(path, {"A", "B"})
    assert not _feature_file_complete(path, {"A", "B", "C"})


def test_full_lodo_logistic_grid_reports_c_grid() -> None:
    rows = [
        {"dataset": "A", "true_label": 0, "x": 0.0},
        {"dataset": "A", "true_label": 1, "x": 2.0},
        {"dataset": "B", "true_label": 0, "x": 0.1},
        {"dataset": "B", "true_label": 1, "x": 2.1},
        {"dataset": "C", "true_label": 0, "x": 0.2},
        {"dataset": "C", "true_label": 1, "x": 2.2},
    ]

    result = _lodo_logistic_grid(rows, ["x"], c_values=[0.1, 1.0])

    assert set(result["c_grid_metrics"]) == {"c_0.1", "c_1.0"}
    assert result["best_c_by_auc"] in {0.1, 1.0}
    assert result["best_metric"]["auc"] == pytest.approx(1.0)


def test_full_lodo_parallel_scoring_preserves_input_order() -> None:
    rows = [{"record_id": str(idx)} for idx in range(8)]

    scored = _score_rows_with_workers(
        rows,
        scorer=lambda row: {"record_id": row["record_id"], "score": int(row["record_id"])},
        workers=4,
    )

    assert [row["record_id"] for row in scored] == [str(idx) for idx in range(8)]


def test_full_lodo_run_suffix_separates_dry_run_from_full_run() -> None:
    assert _run_suffix(None) == "full"
    assert _run_suffix(20) == "max_20"
