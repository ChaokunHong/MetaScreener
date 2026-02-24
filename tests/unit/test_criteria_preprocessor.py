"""Tests for InputPreprocessor text cleanup and language detection."""

from __future__ import annotations

from metascreener.criteria.preprocessor import InputPreprocessor


def test_clean_pdf_noise() -> None:
    """Remove form feeds, collapse extra whitespace and newlines."""
    dirty = "Title of Paper\n\n\n  \nSome text with  weird   spacing\n\f\nPage 2"
    result = InputPreprocessor.clean_text(dirty)
    assert "\f" not in result
    assert "  " not in result
    assert result.strip() == result


def test_clean_control_chars_removed() -> None:
    """Control characters (except newlines/tabs) are stripped."""
    text = "Hello\x00World\x01Test\tKeep\nAlso"
    result = InputPreprocessor.clean_text(text)
    assert "\x00" not in result
    assert "\x01" not in result
    assert "\t" in result
    assert "\n" in result


def test_clean_collapses_excessive_newlines() -> None:
    """Three or more consecutive newlines collapse to exactly two."""
    text = "First\n\n\n\n\nSecond"
    result = InputPreprocessor.clean_text(text)
    assert result == "First\n\nSecond"


def test_clean_preserves_double_newline() -> None:
    """Exactly two newlines (paragraph break) are kept."""
    text = "First\n\nSecond"
    result = InputPreprocessor.clean_text(text)
    assert result == "First\n\nSecond"


def test_clean_empty_string() -> None:
    """Empty string returns empty string."""
    assert InputPreprocessor.clean_text("") == ""


def test_truncate_long_text() -> None:
    """Long text is truncated at a word boundary with suffix."""
    long_text = "word " * 10000
    result = InputPreprocessor.truncate(long_text, max_chars=5000)
    assert len(result) <= 5100  # allow for "... [truncated]" suffix
    assert result.endswith("... [truncated]")


def test_truncate_short_text_unchanged() -> None:
    """Text within the limit is returned unchanged."""
    short = "This is a short text."
    result = InputPreprocessor.truncate(short, max_chars=5000)
    assert result == short


def test_truncate_exact_length_unchanged() -> None:
    """Text exactly at the limit is returned unchanged."""
    text = "a" * 5000
    result = InputPreprocessor.truncate(text, max_chars=5000)
    assert result == text


def test_truncate_no_space_fallback() -> None:
    """When no space found before limit, truncate at max_chars directly."""
    text = "a" * 20000  # no spaces at all
    result = InputPreprocessor.truncate(text, max_chars=5000)
    assert result.endswith("... [truncated]")
    # The content part should be at most max_chars
    assert len(result) <= 5000 + len("... [truncated]")


def test_detect_language_english() -> None:
    """English text is detected as 'en'."""
    text = "Effect of antimicrobial stewardship programs on mortality in ICU patients"
    lang = InputPreprocessor.detect_language(text)
    assert lang == "en"


def test_detect_language_chinese() -> None:
    """Chinese text is detected as 'zh'."""
    text = "抗菌药物管理对ICU患者死亡率的影响"
    lang = InputPreprocessor.detect_language(text)
    assert lang == "zh"


def test_detect_language_japanese() -> None:
    """Japanese text with hiragana/katakana is detected as 'ja'."""
    text = "抗菌薬の管理がICU患者の死亡率に与える影響について"
    lang = InputPreprocessor.detect_language(text)
    assert lang == "ja"


def test_detect_language_korean() -> None:
    """Korean text with hangul is detected as 'ko'."""
    text = "항균제 관리가 중환자실 환자 사망률에 미치는 영향"
    lang = InputPreprocessor.detect_language(text)
    assert lang == "ko"


def test_detect_language_mixed_mostly_english() -> None:
    """Mixed text with low CJK ratio is detected as 'en'."""
    text = "This is an English paper about 药物 effects"
    lang = InputPreprocessor.detect_language(text)
    assert lang == "en"


def test_detect_language_empty_string() -> None:
    """Empty string defaults to 'en'."""
    lang = InputPreprocessor.detect_language("")
    assert lang == "en"
