"""V1 Source Coherence Validator.

Verifies that an extracted value is actually grounded in its cited evidence
sentence, and that the evidence sentence itself exists in the source document.
"""
from __future__ import annotations

import re
from typing import Any

from metascreener.doc_engine.models import Section, StructuredDocument
from metascreener.module2_extraction.models import ExtractionStrategy, RawExtractionResult
from metascreener.module2_extraction.validation.models import ValidationResult


class SourceCoherenceValidator:
    """V1: Verify extracted value appears in its cited evidence.

    Rules applied in order:
    1. DIRECT_TABLE strategy → always passes (value came directly from a table cell).
    2. No evidence sentence present → warning.
    3. Evidence sentence must exist in the document (fuzzy: token_overlap_ratio > 0.80).
    4. Extracted value must appear in the evidence text.
    """

    _OVERLAP_THRESHOLD: float = 0.80

    def validate(
        self,
        result: RawExtractionResult,
        doc: StructuredDocument,
    ) -> ValidationResult:
        """Validate that the extracted value is coherent with its evidence source.

        Args:
            result: The raw extraction result containing the value and its evidence.
            doc: The structured document from which the value was extracted.

        Returns:
            ValidationResult indicating pass/fail with severity and message.
        """
        # Rule 1: DIRECT_TABLE always passes — value read directly from a cell.
        if result.strategy_used == ExtractionStrategy.DIRECT_TABLE:
            return ValidationResult(passed=True)

        # Rule 2: No evidence sentence — cannot verify, issue a warning.
        evidence_sentence = result.evidence.sentence if result.evidence else None
        if not evidence_sentence or not evidence_sentence.strip():
            return ValidationResult(
                passed=False,
                severity="warning",
                message="No evidence sentence provided; cannot verify source coherence.",
            )

        # Rule 3: Evidence sentence must exist in the document (fuzzy match).
        if not _locate_sentence_in_doc(evidence_sentence, doc):
            return ValidationResult(
                passed=False,
                severity="error",
                message=(
                    f"Evidence sentence not found in document "
                    f"(overlap threshold {self._OVERLAP_THRESHOLD}). "
                    f"Possible hallucination: '{evidence_sentence[:80]}...'"
                ),
            )

        # Rule 4: Extracted value must appear in the evidence text.
        if not _value_present_in_text(result.value, evidence_sentence):
            return ValidationResult(
                passed=False,
                severity="error",
                message=(
                    f"Extracted value '{result.value}' not found in evidence sentence: "
                    f"'{evidence_sentence[:120]}'"
                ),
            )

        return ValidationResult(passed=True)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _token_overlap_ratio(a: str, b: str) -> float:
    """Compute the Jaccard-style token overlap ratio between two strings.

    Tokens are whitespace-split and lowercased before comparison.

    Args:
        a: First string.
        b: Second string.

    Returns:
        A float in [0, 1]: |tokens(a) ∩ tokens(b)| / |tokens(a) ∪ tokens(b)|.
        Returns 0.0 if both strings are empty.
    """
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a and not tokens_b:
        return 0.0
    union = tokens_a | tokens_b
    intersection = tokens_a & tokens_b
    return len(intersection) / len(union)


def _locate_sentence_in_doc(sentence: str, doc: StructuredDocument) -> bool:
    """Check whether a sentence exists within the document text.

    Performs a fuzzy search over all section content using token overlap.
    The sentence is considered found if any section contains it verbatim
    (substring) OR if the overlap with the entire section content exceeds
    the 0.80 threshold.

    Args:
        sentence: The evidence sentence to look for.
        doc: The structured document to search within.

    Returns:
        True if the sentence is found (or sufficiently similar), False otherwise.
    """
    sentence_lower = sentence.lower().strip()

    def _search_section(section: Section) -> bool:
        content_lower = section.content.lower()
        # Fast path: exact substring
        if sentence_lower in content_lower:
            return True
        # Fuzzy: token overlap on the sentence vs. content window
        if _token_overlap_ratio(sentence, section.content) >= 0.80:
            return True
        # Recurse into sub-sections
        return any(_search_section(child) for child in section.children)

    for section in doc.sections:
        if _search_section(section):
            return True

    # Also check raw_markdown as a fallback full-text search
    if sentence_lower in doc.raw_markdown.lower():
        return True

    return False


def _value_present_in_text(value: Any, text: str) -> bool:
    """Determine whether a value is present within a text string.

    For string values: checks direct substring (case-insensitive).
    For numeric values: extracts all numbers from the text and checks
    for an approximate match (within 1% relative tolerance).
    For other types: falls back to string representation substring search.

    Args:
        value: The extracted value to look for.
        text: The evidence text to search within.

    Returns:
        True if the value can be found in the text.
    """
    if value is None:
        return False

    if isinstance(value, str):
        return value.lower() in text.lower()

    if isinstance(value, (int, float)):
        numbers_in_text = _extract_all_numbers(text)
        target = float(value)
        for num in numbers_in_text:
            if target == 0.0:
                if abs(num) < 1e-9:
                    return True
            else:
                if abs(num - target) / abs(target) <= 0.01:
                    return True
        return False

    # Fallback: string representation
    return str(value).lower() in text.lower()


def _extract_all_numbers(text: str) -> list[float]:
    """Extract all numeric values from a text string.

    Handles integers, decimals, and signed numbers.

    Args:
        text: The text to parse.

    Returns:
        A list of floats found in the text (may be empty).
    """
    pattern = r"[-+]?\d*\.?\d+"
    matches = re.findall(pattern, text)
    result: list[float] = []
    for m in matches:
        try:
            result.append(float(m))
        except ValueError:
            pass
    return result
