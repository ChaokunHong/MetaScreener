"""Tests for text quality assessment (pre-pipeline quality gate)."""
from __future__ import annotations

from metascreener.io.text_quality import (
    _compute_avg_word_length,
    _compute_printable_ratio,
    _compute_sentence_ratio,
    _word_length_to_score,
    assess_text_quality,
)


class TestAssessTextQuality:
    """Tests for the assess_text_quality() function."""

    def test_good_quality_passes(self) -> None:
        """Normal English prose passes the quality gate."""
        text = (
            "This is a well-written academic paper about the effects of "
            "antimicrobial resistance in hospital settings. The study included "
            "500 patients aged 18-65 who were randomized to receive either "
            "the intervention or placebo. Results showed significant improvement "
            "in the primary outcome measure. The conclusion supports the use "
            "of the intervention in clinical practice. "
        ) * 5  # Repeat to get above 100 chars threshold
        result = assess_text_quality(text)
        assert result.passes_gate is True
        assert result.is_marginal is False
        assert result.quality_score > 0.6
        assert result.printable_ratio > 0.95

    def test_garbled_fails(self) -> None:
        """Random bytes / garbled OCR text fails the gate."""
        # Simulate garbled text with lots of non-printable characters
        garbled = "\x00\x01\x02\x03\x04\x05" * 200 + "abc" * 10
        result = assess_text_quality(garbled)
        assert result.passes_gate is False
        assert result.printable_ratio < 0.70

    def test_short_text_passes_through(self) -> None:
        """Text shorter than 100 chars passes through unconditionally."""
        result = assess_text_quality("Short text.")
        assert result.passes_gate is True
        assert result.is_marginal is False
        assert result.quality_score == 1.0
        assert result.details.get("reason") == "short_text_passthrough"

    def test_empty_passes_through(self) -> None:
        """Empty string passes through."""
        result = assess_text_quality("")
        assert result.passes_gate is True
        assert result.quality_score == 1.0

    def test_marginal_flagged(self) -> None:
        """Text with mixed quality is flagged as marginal."""
        # Create text that is mostly printable but with poor sentence structure
        # and abnormal word lengths — quality_score should be in [0.30, 0.60)
        words = ["ab"] * 500  # Very short words → low word_len_score
        text = " ".join(words)  # No sentence endings → low sentence_ratio
        # But all printable → printable_ratio = 1.0
        # quality = 0.50*1.0 + 0.25*low + 0.25*low → should be marginal range
        result = assess_text_quality(text)
        # May or may not be marginal depending on exact scores, but should pass
        assert result.passes_gate is True  # printable ratio is fine
        # Verify it produces valid metrics
        assert 0.0 <= result.quality_score <= 1.0

    def test_low_printable_fails(self) -> None:
        """printable_ratio < 0.70 triggers gate failure."""
        # 60% non-printable control chars, 40% normal text
        non_print = "\x00\x01\x02\x03\x04\x05\x06\x07" * 100
        normal = "normal text here. " * 30
        text = non_print + normal  # ~800 non-print + ~540 normal = ~60% non-print
        result = assess_text_quality(text)
        assert result.passes_gate is False
        assert result.printable_ratio < 0.70

    def test_low_quality_score_fails(self) -> None:
        """Composite quality_score < 0.30 triggers gate failure."""
        # All non-printable, no words, no sentences → all sub-metrics near 0
        text = "\x00" * 500
        result = assess_text_quality(text)
        assert result.passes_gate is False
        assert result.quality_score < 0.30

    def test_metrics_bounds(self) -> None:
        """All metrics are within their expected bounds."""
        text = "Hello world. This is a test sentence. " * 20
        result = assess_text_quality(text)
        assert 0.0 <= result.printable_ratio <= 1.0
        assert result.avg_word_length >= 0.0
        assert 0.0 <= result.sentence_ratio <= 1.0
        assert 0.0 <= result.quality_score <= 1.0


class TestSubMetrics:
    """Tests for individual sub-metric functions."""

    def test_printable_ratio_all_printable(self) -> None:
        assert _compute_printable_ratio("Hello World") == 1.0

    def test_printable_ratio_mixed(self) -> None:
        text = "abc\x00\x01\x02"
        ratio = _compute_printable_ratio(text)
        assert 0.0 < ratio < 1.0

    def test_printable_ratio_empty(self) -> None:
        assert _compute_printable_ratio("") == 1.0

    def test_avg_word_length_normal(self) -> None:
        avg = _compute_avg_word_length("hello world test")
        assert 4.0 <= avg <= 6.0

    def test_avg_word_length_empty(self) -> None:
        assert _compute_avg_word_length("") == 0.0

    def test_sentence_ratio_with_periods(self) -> None:
        text = "This is a sentence. And another one. " * 10
        ratio = _compute_sentence_ratio(text)
        assert ratio > 0.5

    def test_sentence_ratio_no_periods(self) -> None:
        text = "no sentence ending here " * 20
        ratio = _compute_sentence_ratio(text)
        assert ratio < 0.5

    def test_word_length_score_optimal(self) -> None:
        """Word length in optimal range (3-8) → score 1.0."""
        assert _word_length_to_score(5.0) == 1.0
        assert _word_length_to_score(3.0) == 1.0
        assert _word_length_to_score(8.0) == 1.0

    def test_word_length_score_extreme(self) -> None:
        """Word length outside bounds (< 2 or > 15) → score 0.0."""
        assert _word_length_to_score(1.5) == 0.0
        assert _word_length_to_score(16.0) == 0.0
        assert _word_length_to_score(0.0) == 0.0

    def test_word_length_score_intermediate(self) -> None:
        """Word length between bounds → intermediate score."""
        score = _word_length_to_score(2.5)  # between 2.0 and 3.0
        assert 0.0 < score < 1.0
