from __future__ import annotations

import math

import pytest

from metascreener.module1_screening.ms_active.feature_policy import MS_SCREEN_NUMERIC_FEATURES
from metascreener.module1_screening.ms_active.models import (
    CandidateExample,
    RecordLabel,
    TrainingExample,
)
from metascreener.module1_screening.ms_active.rankers import (
    TextFeatureLogisticRanker,
    TfidfLogisticRanker,
)


def _training(
    record_id: str,
    text: str,
    label: RecordLabel,
    *,
    score: float = 0.0,
) -> TrainingExample:
    return TrainingExample(
        record_id=record_id,
        text=text,
        true_label=label,
        features={"p_include": score},
    )


def _candidate(record_id: str, text: str, *, score: float = 0.0) -> CandidateExample:
    return CandidateExample(record_id=record_id, text=text, features={"p_include": score})


def _rankers() -> list[TfidfLogisticRanker]:
    return [
        TfidfLogisticRanker(random_state=42),
        TextFeatureLogisticRanker(feature_keys=("p_include",), random_state=42),
    ]


def test_tfidf_logistic_ranker_scores_include_like_text_higher() -> None:
    ranker = TfidfLogisticRanker(random_state=42)
    ranker.fit(
        [
            _training("inc", "randomized clinical trial eligible outcome", RecordLabel.INCLUDE),
            _training("exc", "editorial background excluded commentary", RecordLabel.EXCLUDE),
        ]
    )

    rows = ranker.score(
        [
            _candidate("candidate_include", "eligible randomized trial outcome"),
            _candidate("candidate_exclude", "editorial commentary background"),
        ]
    )

    score_by_id = {row.record_id: row.score for row in rows}
    assert set(score_by_id) == {"candidate_include", "candidate_exclude"}
    assert all(math.isfinite(score) for score in score_by_id.values())
    assert score_by_id["candidate_include"] > score_by_id["candidate_exclude"]


def test_tfidf_logistic_ranker_uses_prepared_corpus_matrix() -> None:
    ranker = TfidfLogisticRanker(random_state=42)
    ranker.prepare(
        [
            _candidate("inc", "eligible randomized clinical trial"),
            _candidate("exc", "excluded editorial commentary"),
            _candidate("candidate", "randomized trial"),
        ]
    )

    ranker.fit(
        [
            _training("inc", "ignored text", RecordLabel.INCLUDE),
            _training("exc", "ignored text", RecordLabel.EXCLUDE),
        ]
    )
    rows = ranker.score([_candidate("candidate", "ignored text")])

    assert [row.record_id for row in rows] == ["candidate"]
    assert 0.0 <= rows[0].score <= 1.0


@pytest.mark.parametrize("ranker", _rankers())
def test_rankers_reject_score_before_fit(ranker: TfidfLogisticRanker) -> None:
    with pytest.raises(RuntimeError, match="fit"):
        ranker.score([_candidate("candidate", "eligible trial")])


@pytest.mark.parametrize("ranker", _rankers())
def test_rankers_reject_one_class_training_data(ranker: TfidfLogisticRanker) -> None:
    with pytest.raises(ValueError, match="both INCLUDE and EXCLUDE"):
        ranker.fit(
            [
                _training("inc1", "eligible trial", RecordLabel.INCLUDE),
                _training("inc2", "eligible study", RecordLabel.INCLUDE),
            ]
        )


def test_text_feature_logistic_ranker_uses_numeric_features_when_text_is_identical() -> None:
    ranker = TextFeatureLogisticRanker(feature_keys=("p_include",), random_state=42)
    ranker.fit(
        [
            _training("inc", "same abstract", RecordLabel.INCLUDE, score=1.0),
            _training("exc", "same abstract", RecordLabel.EXCLUDE, score=0.0),
        ]
    )

    rows = ranker.score(
        [
            _candidate("candidate_high", "same abstract", score=0.9),
            _candidate("candidate_low", "same abstract", score=0.1),
        ]
    )

    score_by_id = {row.record_id: row.score for row in rows}
    assert set(score_by_id) == {"candidate_high", "candidate_low"}
    assert all(math.isfinite(score) for score in score_by_id.values())
    assert all(0.0 <= score <= 1.0 for score in score_by_id.values())
    assert score_by_id["candidate_high"] > score_by_id["candidate_low"]


def test_text_feature_logistic_ranker_preserves_text_signal_when_numeric_features_equal() -> None:
    ranker = TextFeatureLogisticRanker(feature_keys=("p_include",), random_state=42)
    ranker.fit(
        [
            _training("inc", "randomized eligible trial outcome", RecordLabel.INCLUDE, score=0.5),
            _training("exc", "excluded editorial commentary", RecordLabel.EXCLUDE, score=0.5),
        ]
    )

    rows = ranker.score(
        [
            _candidate("candidate_include", "eligible randomized trial", score=0.5),
            _candidate("candidate_exclude", "editorial commentary", score=0.5),
        ]
    )

    score_by_id = {row.record_id: row.score for row in rows}
    assert score_by_id["candidate_include"] > score_by_id["candidate_exclude"]


def test_text_feature_logistic_ranker_imputes_missing_candidate_feature_from_training() -> None:
    ranker = TextFeatureLogisticRanker(feature_keys=("p_include",), random_state=42)
    ranker.fit(
        [
            _training("inc", "eligible trial", RecordLabel.INCLUDE, score=1.0),
            _training("exc", "excluded commentary", RecordLabel.EXCLUDE, score=0.0),
        ]
    )

    rows = ranker.score([CandidateExample(record_id="missing", text="eligible", features={})])

    assert rows[0].record_id == "missing"
    assert math.isfinite(rows[0].score)
    assert 0.0 <= rows[0].score <= 1.0


def test_text_feature_logistic_ranker_imputes_missing_candidate_as_training_median() -> None:
    ranker = TextFeatureLogisticRanker(feature_keys=("p_include",), random_state=42)
    ranker.fit(
        [
            _training("inc", "same abstract", RecordLabel.INCLUDE, score=1.0),
            _training("exc", "same abstract", RecordLabel.EXCLUDE, score=0.0),
            _training("exc_mid", "same abstract", RecordLabel.EXCLUDE, score=0.5),
        ]
    )

    rows = ranker.score(
        [
            CandidateExample(record_id="missing", text="same abstract", features={}),
            _candidate("explicit_median", "same abstract", score=0.5),
        ]
    )
    score_by_id = {row.record_id: row.score for row in rows}

    assert score_by_id["missing"] == pytest.approx(score_by_id["explicit_median"])


def test_text_feature_logistic_ranker_rejects_unsupported_numeric_feature_key() -> None:
    with pytest.raises(ValueError, match="Unsupported MS-Screen"):
        TextFeatureLogisticRanker(feature_keys=("ms_score",), random_state=42)


def test_text_feature_logistic_ranker_accepts_preregistered_ms_screen_feature_keys() -> None:
    ranker = TextFeatureLogisticRanker(
        feature_keys=tuple(sorted(MS_SCREEN_NUMERIC_FEATURES)),
        random_state=42,
    )

    assert ranker.feature_keys == tuple(sorted(MS_SCREEN_NUMERIC_FEATURES))


@pytest.mark.parametrize("feature_key", ["asreview_score", "label_included", "oracle_score"])
def test_text_feature_logistic_ranker_rejects_leakage_feature_keys(feature_key: str) -> None:
    with pytest.raises(ValueError, match="leakage feature"):
        TextFeatureLogisticRanker(feature_keys=(feature_key,), random_state=42)


def test_text_feature_logistic_ranker_rejects_all_missing_training_feature() -> None:
    ranker = TextFeatureLogisticRanker(feature_keys=("p_include",), random_state=42)

    with pytest.raises(ValueError, match="finite training value"):
        ranker.fit(
            [
                TrainingExample(
                    record_id="inc",
                    text="eligible trial",
                    true_label=RecordLabel.INCLUDE,
                    features={},
                ),
                TrainingExample(
                    record_id="exc",
                    text="excluded commentary",
                    true_label=RecordLabel.EXCLUDE,
                    features={},
                ),
            ]
        )


@pytest.mark.parametrize("bad_value", [float("inf"), float("-inf")])
def test_text_feature_logistic_ranker_rejects_non_finite_numeric_features(
    bad_value: float,
) -> None:
    ranker = TextFeatureLogisticRanker(feature_keys=("p_include",), random_state=42)

    with pytest.raises(ValueError, match="must be finite"):
        ranker.fit(
            [
                _training("inc", "eligible trial", RecordLabel.INCLUDE, score=1.0),
                _training("exc", "excluded commentary", RecordLabel.EXCLUDE, score=bad_value),
            ]
        )

    ranker.fit(
        [
            _training("inc", "eligible trial", RecordLabel.INCLUDE, score=1.0),
            _training("exc", "excluded commentary", RecordLabel.EXCLUDE, score=0.0),
        ]
    )
    with pytest.raises(ValueError, match="must be finite"):
        ranker.score([_candidate("bad", "eligible", score=bad_value)])


@pytest.mark.parametrize("ranker", _rankers())
def test_ranker_scores_are_probabilities_between_zero_and_one(
    ranker: TfidfLogisticRanker,
) -> None:
    ranker.fit(
        [
            _training("inc", "eligible trial", RecordLabel.INCLUDE, score=1.0),
            _training("exc", "excluded commentary", RecordLabel.EXCLUDE, score=0.0),
        ]
    )

    rows = ranker.score(
        [
            _candidate("candidate_a", "eligible trial", score=0.9),
            _candidate("candidate_b", "", score=0.1),
        ]
    )

    assert all(0.0 <= row.score <= 1.0 for row in rows)


def test_text_feature_ranker_uses_training_statistics_for_numeric_scaling() -> None:
    ranker = TextFeatureLogisticRanker(feature_keys=("p_include",), random_state=42)
    ranker.fit(
        [
            _training("inc", "same abstract", RecordLabel.INCLUDE, score=1.0),
            _training("exc", "same abstract", RecordLabel.EXCLUDE, score=0.0),
        ]
    )
    candidate = _candidate("stable", "same abstract", score=0.5)
    score_alone = ranker.score([candidate])[0].score
    score_with_extreme = {
        row.record_id: row.score
        for row in ranker.score(
            [
                candidate,
                _candidate("extreme", "same abstract", score=9999.0),
            ]
        )
    }["stable"]

    assert score_with_extreme == pytest.approx(score_alone)


def test_tfidf_ranker_scores_empty_candidate_text_finitely() -> None:
    ranker = TfidfLogisticRanker(random_state=42)
    ranker.fit(
        [
            _training("inc", "eligible trial", RecordLabel.INCLUDE),
            _training("exc", "excluded commentary", RecordLabel.EXCLUDE),
        ]
    )

    row = ranker.score([_candidate("empty", "")])[0]

    assert math.isfinite(row.score)


@pytest.mark.parametrize("ranker", _rankers())
def test_rankers_report_empty_training_vocabulary_cleanly(
    ranker: TfidfLogisticRanker,
) -> None:
    with pytest.raises(ValueError, match="TF-IDF vocabulary"):
        ranker.fit(
            [
                _training("inc", "", RecordLabel.INCLUDE, score=1.0),
                _training("exc", "", RecordLabel.EXCLUDE, score=0.0),
            ]
        )
