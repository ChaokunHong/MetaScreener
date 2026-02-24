"""Input text preprocessing for criteria wizard.

Provides text cleanup, truncation, and language detection utilities
used by the PICO Criteria Wizard to normalize user-provided text
before LLM processing.
"""

from __future__ import annotations

import re
import unicodedata

import structlog

logger = structlog.get_logger(__name__)

# Maximum default character limit for text truncation.
DEFAULT_MAX_CHARS = 15_000

# Truncation suffix appended when text exceeds the limit.
TRUNCATION_SUFFIX = "... [truncated]"

# CJK ratio threshold: if CJK characters exceed this fraction of
# total alphabetic+CJK characters, the text is classified as CJK.
CJK_RATIO_THRESHOLD = 0.3


class InputPreprocessor:
    """Static utility class for preprocessing raw text input.

    Handles PDF noise removal, text truncation with word-boundary
    awareness, and simple Unicode-based language detection.
    """

    @staticmethod
    def clean_text(text: str) -> str:
        """Remove noise from raw text input.

        Processing steps:
            1. Remove form feed characters.
            2. Remove control characters (keep newlines and tabs).
            3. Collapse multiple spaces to a single space.
            4. Collapse 3+ consecutive newlines to exactly 2.
            5. Strip leading/trailing whitespace.

        Args:
            text: Raw input text, potentially from PDF extraction.

        Returns:
            Cleaned text with normalized whitespace.
        """
        if not text:
            return ""

        # Step 1: Remove form feed characters.
        result = text.replace("\f", "")

        # Step 2: Remove control characters except newline (\n) and tab (\t).
        # Unicode category "Cc" covers all C0/C1 control characters.
        result = "".join(
            ch
            for ch in result
            if ch in ("\n", "\t") or unicodedata.category(ch) != "Cc"
        )

        # Step 3: Collapse multiple spaces (not newlines/tabs) to one.
        result = re.sub(r"[ ]+", " ", result)

        # Step 4: Collapse 3+ consecutive newlines (with optional
        # spaces between them) to exactly 2 newlines.
        result = re.sub(r"(\n[ ]*){3,}", "\n\n", result)

        # Step 5: Strip leading/trailing whitespace.
        return result.strip()

    @staticmethod
    def truncate(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
        """Truncate text to a maximum character count at a word boundary.

        If the text is within the limit, it is returned unchanged.
        Otherwise, truncation occurs at the last space character before
        the limit, and the truncation suffix is appended.

        Args:
            text: Input text to potentially truncate.
            max_chars: Maximum number of characters before truncation.

        Returns:
            Original text if within limit, otherwise truncated text
            with ``"... [truncated]"`` suffix.
        """
        if len(text) <= max_chars:
            return text

        logger.warning(
            "text_truncated",
            original_length=len(text),
            max_chars=max_chars,
        )

        # Find last space before the limit for a clean word boundary.
        truncation_point = text.rfind(" ", 0, max_chars)

        if truncation_point == -1:
            # No space found; hard-truncate at max_chars.
            truncation_point = max_chars

        return text[:truncation_point] + TRUNCATION_SUFFIX

    @staticmethod
    def detect_language(text: str) -> str:
        """Detect the primary language of text using Unicode heuristics.

        Uses character-class ratios to distinguish CJK-family languages
        from Latin-script text. Within CJK, the presence of
        hiragana/katakana indicates Japanese, hangul indicates Korean,
        and pure CJK ideographs default to Chinese.

        This is a lightweight heuristic suitable for screening input;
        it is not a full language detector.

        Args:
            text: Input text to classify.

        Returns:
            ISO 639-1 language code: ``"en"``, ``"zh"``, ``"ja"``,
            or ``"ko"``.
        """
        if not text:
            return "en"

        cjk_count = 0
        latin_count = 0
        hiragana_katakana_count = 0
        hangul_count = 0

        for ch in text:
            cp = ord(ch)

            # CJK Unified Ideographs (U+4E00–U+9FFF)
            # CJK Unified Ideographs Extension A (U+3400–U+4DBF)
            # CJK Compatibility Ideographs (U+F900–U+FAFF)
            if (0x4E00 <= cp <= 0x9FFF) or \
               (0x3400 <= cp <= 0x4DBF) or \
               (0xF900 <= cp <= 0xFAFF):
                cjk_count += 1

            # Hiragana (U+3040–U+309F) and Katakana (U+30A0–U+30FF)
            elif (0x3040 <= cp <= 0x309F) or (0x30A0 <= cp <= 0x30FF):
                hiragana_katakana_count += 1
                cjk_count += 1  # Also count toward CJK total

            # Hangul Syllables (U+AC00–U+D7AF)
            # Hangul Jamo (U+1100–U+11FF)
            # Hangul Compatibility Jamo (U+3130–U+318F)
            elif (0xAC00 <= cp <= 0xD7AF) or \
                 (0x1100 <= cp <= 0x11FF) or \
                 (0x3130 <= cp <= 0x318F):
                hangul_count += 1
                cjk_count += 1  # Also count toward CJK total

            # Basic Latin letters (A-Z, a-z)
            elif (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A):
                latin_count += 1

        total_alpha = cjk_count + latin_count
        if total_alpha == 0:
            return "en"

        cjk_ratio = cjk_count / total_alpha

        if cjk_ratio > CJK_RATIO_THRESHOLD:
            # Distinguish among CJK languages.
            if hiragana_katakana_count > 0:
                return "ja"
            if hangul_count > 0:
                return "ko"
            return "zh"

        return "en"
