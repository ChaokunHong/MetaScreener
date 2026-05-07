"""Linear active-learning rankers for MS-Active-Risk."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from scipy.sparse import csr_matrix, hstack  # type: ignore[import-untyped]
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

from metascreener.module1_screening.ms_active.feature_policy import (
    validate_ms_screen_numeric_feature_keys,
)
from metascreener.module1_screening.ms_active.models import (
    CandidateExample,
    RecordLabel,
    ScoreRow,
    TrainingExample,
)


@dataclass(kw_only=True)
class TfidfLogisticRanker:
    """A1 ranker: review-specific TF-IDF logistic active learner."""

    random_state: int = 42
    C: float = 1.0
    max_iter: int = 1000
    name: str = "tfidf_logistic"
    feature_set_id: str = "text_tfidf"
    _vectorizer: TfidfVectorizer | None = field(default=None, init=False, repr=False)
    _model: LogisticRegression | None = field(default=None, init=False, repr=False)
    _prepared_text_matrix: csr_matrix | None = field(default=None, init=False, repr=False)
    _prepared_row_by_id: dict[str, int] | None = field(default=None, init=False, repr=False)

    def prepare(self, records: Sequence[CandidateExample]) -> None:
        """Pre-compute corpus TF-IDF features without using labels."""
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        try:
            matrix = vectorizer.fit_transform([record.text for record in records]).tocsr()
        except ValueError as exc:
            if "empty vocabulary" in str(exc):
                raise ValueError("TF-IDF vocabulary is empty for active corpus") from exc
            raise
        self._vectorizer = vectorizer
        self._prepared_text_matrix = matrix
        self._prepared_row_by_id = {
            record.record_id: index for index, record in enumerate(records)
        }

    def fit(self, labelled_records: Sequence[TrainingExample]) -> None:
        """Fit a review-specific text classifier from reviewed labels."""
        _validate_two_class_training(labelled_records)
        matrix = self._text_matrix_for_training(labelled_records)
        model = LogisticRegression(
            C=self.C,
            class_weight="balanced",
            max_iter=self.max_iter,
            random_state=self.random_state,
        )
        model.fit(matrix, _labels(labelled_records))
        self._model = model

    def score(self, candidate_records: Sequence[CandidateExample]) -> list[ScoreRow]:
        """Score candidates by predicted INCLUDE probability."""
        _, model = self._require_fitted()
        matrix = self._text_matrix_for_candidates(candidate_records)
        probabilities = model.predict_proba(matrix)
        include_index = _include_probability_index(model)
        return [
            ScoreRow(record_id=record.record_id, score=float(probabilities[index, include_index]))
            for index, record in enumerate(candidate_records)
        ]

    def _require_fitted(self) -> tuple[TfidfVectorizer, LogisticRegression]:
        if self._vectorizer is None or self._model is None:
            raise RuntimeError("Ranker must be fit before score is called")
        return self._vectorizer, self._model

    def _text_matrix_for_training(
        self,
        labelled_records: Sequence[TrainingExample],
    ) -> csr_matrix:
        if self._prepared_text_matrix is not None:
            return self._prepared_rows(labelled_records)
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        matrix = _fit_text_matrix(vectorizer, labelled_records)
        self._vectorizer = vectorizer
        return matrix

    def _text_matrix_for_candidates(
        self,
        candidate_records: Sequence[CandidateExample],
    ) -> csr_matrix:
        if self._prepared_text_matrix is not None:
            return self._prepared_rows(candidate_records)
        vectorizer, _ = self._require_fitted()
        return vectorizer.transform([record.text for record in candidate_records]).tocsr()

    def _prepared_rows(
        self,
        records: Sequence[TrainingExample] | Sequence[CandidateExample],
    ) -> csr_matrix:
        if self._prepared_text_matrix is None or self._prepared_row_by_id is None:
            raise RuntimeError("Prepared text matrix is missing")
        try:
            indices = [self._prepared_row_by_id[record.record_id] for record in records]
        except KeyError as exc:
            raise ValueError(f"Record {exc.args[0]!r} was not prepared") from exc
        return self._prepared_text_matrix[indices]


@dataclass(kw_only=True)
class TextFeatureLogisticRanker(TfidfLogisticRanker):
    """A2 ranker: TF-IDF text plus selected numeric MS-Screen features."""

    feature_keys: tuple[str, ...] = ("p_include", "final_score")
    name: str = "text_feature_logistic"
    feature_set_id: str = "text_tfidf_numeric"
    _numeric_transform: NumericFeatureTransform | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        self.feature_keys = validate_ms_screen_numeric_feature_keys(self.feature_keys)

    def fit(self, labelled_records: Sequence[TrainingExample]) -> None:
        """Fit a review-specific text + numeric feature classifier."""
        _validate_two_class_training(labelled_records)
        text_matrix = self._text_matrix_for_training(labelled_records)
        numeric_transform = NumericFeatureTransform.fit(labelled_records, self.feature_keys)
        numeric_matrix = numeric_transform.transform(labelled_records)
        matrix = hstack([text_matrix, numeric_matrix], format="csr")
        model = LogisticRegression(
            C=self.C,
            class_weight="balanced",
            max_iter=self.max_iter,
            random_state=self.random_state,
        )
        model.fit(matrix, _labels(labelled_records))
        self._model = model
        self._numeric_transform = numeric_transform

    def score(self, candidate_records: Sequence[CandidateExample]) -> list[ScoreRow]:
        """Score candidates by predicted INCLUDE probability."""
        _, model = self._require_fitted()
        if self._numeric_transform is None:
            raise RuntimeError("Ranker must be fit before score is called")
        text_matrix = self._text_matrix_for_candidates(candidate_records)
        numeric_matrix = self._numeric_transform.transform(candidate_records)
        matrix = hstack([text_matrix, numeric_matrix], format="csr")
        probabilities = model.predict_proba(matrix)
        include_index = _include_probability_index(model)
        return [
            ScoreRow(record_id=record.record_id, score=float(probabilities[index, include_index]))
            for index, record in enumerate(candidate_records)
        ]


def _validate_two_class_training(labelled_records: Sequence[TrainingExample]) -> None:
    labels = {record.true_label for record in labelled_records}
    if labels != {RecordLabel.INCLUDE, RecordLabel.EXCLUDE}:
        raise ValueError("Ranker training requires both INCLUDE and EXCLUDE labels")


def _labels(labelled_records: Sequence[TrainingExample]) -> list[int]:
    return [int(record.true_label) for record in labelled_records]


def _fit_text_matrix(
    vectorizer: TfidfVectorizer,
    labelled_records: Sequence[TrainingExample],
) -> object:
    try:
        return vectorizer.fit_transform([record.text for record in labelled_records])
    except ValueError as exc:
        if "empty vocabulary" in str(exc):
            raise ValueError("TF-IDF vocabulary is empty for labelled training records") from exc
        raise


def _include_probability_index(model: LogisticRegression) -> int:
    classes = list(model.classes_)
    return classes.index(int(RecordLabel.INCLUDE))


@dataclass(frozen=True)
class NumericFeatureTransform:
    """Training-fold median imputer and standardizer for dense features."""

    feature_keys: tuple[str, ...]
    medians: npt.NDArray[np.float64]
    means: npt.NDArray[np.float64]
    scales: npt.NDArray[np.float64]

    @classmethod
    def fit(
        cls,
        records: Sequence[TrainingExample],
        feature_keys: tuple[str, ...],
    ) -> NumericFeatureTransform:
        raw = _raw_numeric_matrix(records, feature_keys, allow_missing=True)
        all_missing = [
            bool(value) for value in np.atleast_1d(np.isnan(raw).all(axis=0)).tolist()
        ]
        if any(all_missing):
            missing = [
                key
                for key, is_missing in zip(feature_keys, all_missing, strict=True)
                if is_missing
            ]
            raise ValueError(
                "At least one finite training value is required for numeric feature(s): "
                + ", ".join(missing)
            )
        medians = np.nanmedian(raw, axis=0)
        imputed = np.where(np.isnan(raw), medians, raw)
        means = imputed.mean(axis=0)
        scales = imputed.std(axis=0)
        scales = np.where(scales == 0.0, 1.0, scales)
        return cls(feature_keys=feature_keys, medians=medians, means=means, scales=scales)

    def transform(
        self,
        records: Sequence[TrainingExample] | Sequence[CandidateExample],
    ) -> npt.NDArray[np.float64]:
        raw = _raw_numeric_matrix(records, self.feature_keys, allow_missing=True)
        imputed = np.where(np.isnan(raw), self.medians, raw)
        return (imputed - self.means) / self.scales


def _raw_numeric_matrix(
    records: Sequence[TrainingExample] | Sequence[CandidateExample],
    feature_keys: tuple[str, ...],
    *,
    allow_missing: bool,
) -> npt.NDArray[np.float64]:
    values: list[list[float]] = []
    for record in records:
        row: list[float] = []
        for key in feature_keys:
            value = _numeric_value(record, key, allow_missing=allow_missing)
            row.append(value)
        values.append(row)
    return np.asarray(values, dtype=float)


def _numeric_value(
    record: TrainingExample | CandidateExample,
    key: str,
    *,
    allow_missing: bool,
) -> float:
    if key not in record.features:
        if allow_missing:
            return math.nan
        raise ValueError(f"Missing numeric feature {key!r} for record_id {record.record_id}")
    value = float(record.features[key])
    if math.isnan(value) and allow_missing:
        return math.nan
    if not math.isfinite(value):
        raise ValueError(f"Numeric feature {key!r} must be finite for record_id {record.record_id}")
    return value
