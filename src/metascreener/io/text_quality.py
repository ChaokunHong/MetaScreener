"""Text quality assessment for full-text PDF input.

Pre-pipeline gate that detects garbled/OCR-failed PDFs before
wasting LLM API calls on un-screenable text. Routes low-quality
text to HUMAN_REVIEW (never EXCLUDE — preserves recall bias).
"""
from __future__ import annotations

import structlog

from metascreener.core.models import TextQualityResult

logger = structlog.get_logger(__name__)

# Minimum text length for meaningful quality assessment.
# Short texts (e.g., title-only records) pass through unconditionally.
_MIN_ASSESSABLE_LENGTH = 100

# Gate thresholds
_PRINTABLE_FAIL_THRESHOLD = 0.70
_QUALITY_FAIL_THRESHOLD = 0.30
_QUALITY_MARGINAL_THRESHOLD = 0.60

# Word length bounds for the word-length score component.
# Normal English: avg_word_length ≈ 4-6 chars.
# Garbled text tends to have very short (<2) or very long (>15) "words".
_WORD_LEN_LOWER = 2.0
_WORD_LEN_UPPER = 15.0
_WORD_LEN_OPTIMAL_LOW = 3.0
_WORD_LEN_OPTIMAL_HIGH = 8.0

# Segment size for sentence-ratio detection
_SENTENCE_SEGMENT_SIZE = 50


def assess_text_quality(text: str) -> TextQualityResult:
    """Assess the quality of full-text input for LLM screening.

    Computes three sub-metrics and a weighted composite:

    - **printable_ratio**: fraction of printable characters
    - **avg_word_length**: mean word length (garbled text is abnormal)
    - **sentence_ratio**: fraction of segments with sentence-ending punctuation

    Gate logic:

    - ``printable_ratio < 0.70`` OR ``quality_score < 0.30`` → fail
    - ``quality_score`` in [0.30, 0.60) → marginal (proceed with reduced
      confidence)
    - Short text (<100 chars) → pass through (can't assess meaningfully)

    Args:
        text: Full-text content to assess.

    Returns:
        TextQualityResult with metrics, gate status, and marginal flag.
    """
    if not text or len(text) < _MIN_ASSESSABLE_LENGTH:
        return TextQualityResult(
            printable_ratio=1.0,
            avg_word_length=0.0,
            sentence_ratio=1.0,
            quality_score=1.0,
            passes_gate=True,
            is_marginal=False,
            details={"reason": "short_text_passthrough"},
        )

    printable_ratio = _compute_printable_ratio(text)
    avg_word_length = _compute_avg_word_length(text)
    sentence_ratio = _compute_sentence_ratio(text)

    # Convert avg_word_length to a [0, 1] score
    word_len_score = _word_length_to_score(avg_word_length)

    # Weighted composite: printable most important, then sentence, then word
    quality_score = (
        0.50 * printable_ratio
        + 0.25 * word_len_score
        + 0.25 * sentence_ratio
    )
    quality_score = max(0.0, min(1.0, quality_score))

    # Gate logic
    passes_gate = True
    is_marginal = False

    if printable_ratio < _PRINTABLE_FAIL_THRESHOLD:
        passes_gate = False
    elif quality_score < _QUALITY_FAIL_THRESHOLD:
        passes_gate = False
    elif quality_score < _QUALITY_MARGINAL_THRESHOLD:
        is_marginal = True

    result = TextQualityResult(
        printable_ratio=round(printable_ratio, 4),
        avg_word_length=round(avg_word_length, 4),
        sentence_ratio=round(sentence_ratio, 4),
        quality_score=round(quality_score, 4),
        passes_gate=passes_gate,
        is_marginal=is_marginal,
        details={
            "word_len_score": round(word_len_score, 4),
            "text_length": len(text),
        },
    )

    if not passes_gate:
        logger.info(
            "text_quality_gate_failed",
            quality_score=result.quality_score,
            printable_ratio=result.printable_ratio,
            text_length=len(text),
        )
    elif is_marginal:
        logger.info(
            "text_quality_marginal",
            quality_score=result.quality_score,
            text_length=len(text),
        )

    return result


def _compute_printable_ratio(text: str) -> float:
    """Fraction of characters that are printable or whitespace.

    Args:
        text: Input text.

    Returns:
        Ratio in [0.0, 1.0].
    """
    if not text:
        return 1.0
    n_printable = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
    return n_printable / len(text)


def _compute_avg_word_length(text: str) -> float:
    """Average word length across all whitespace-split tokens.

    Args:
        text: Input text.

    Returns:
        Average word length (0.0 if no words).
    """
    words = text.split()
    if not words:
        return 0.0
    return sum(len(w) for w in words) / len(words)


def _compute_sentence_ratio(text: str) -> float:
    """Fraction of text segments containing sentence-ending punctuation.

    Divides text into fixed-size segments and checks each for
    sentence-ending punctuation (``.``, ``!``, ``?``).

    Args:
        text: Input text.

    Returns:
        Ratio in [0.0, 1.0].
    """
    if len(text) < _SENTENCE_SEGMENT_SIZE:
        # Single segment: check if it has sentence-ending punctuation
        has_end = any(c in ".!?" for c in text)
        return 1.0 if has_end else 0.0

    n_segments = len(text) // _SENTENCE_SEGMENT_SIZE
    if n_segments == 0:
        return 0.0

    n_with_sentence = 0
    for i in range(n_segments):
        start = i * _SENTENCE_SEGMENT_SIZE
        end = start + _SENTENCE_SEGMENT_SIZE
        segment = text[start:end]
        if any(c in ".!?" for c in segment):
            n_with_sentence += 1

    return n_with_sentence / n_segments


def _word_length_to_score(avg_len: float) -> float:
    """Convert average word length to a [0, 1] quality score.

    Optimal range (3-8 chars) scores 1.0. Outside that, score
    degrades linearly toward 0.0 at the extreme bounds (2, 15).

    Args:
        avg_len: Average word length.

    Returns:
        Score in [0.0, 1.0].
    """
    if avg_len <= 0.0:
        return 0.0
    if _WORD_LEN_OPTIMAL_LOW <= avg_len <= _WORD_LEN_OPTIMAL_HIGH:
        return 1.0
    if avg_len < _WORD_LEN_LOWER or avg_len > _WORD_LEN_UPPER:
        return 0.0
    if avg_len < _WORD_LEN_OPTIMAL_LOW:
        return (avg_len - _WORD_LEN_LOWER) / (
            _WORD_LEN_OPTIMAL_LOW - _WORD_LEN_LOWER
        )
    # avg_len > _WORD_LEN_OPTIMAL_HIGH
    return (_WORD_LEN_UPPER - avg_len) / (
        _WORD_LEN_UPPER - _WORD_LEN_OPTIMAL_HIGH
    )
