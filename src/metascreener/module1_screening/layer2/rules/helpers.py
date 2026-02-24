"""Shared helpers for Layer 2 soft rules."""
from __future__ import annotations

from metascreener.core.models import ModelOutput


def count_element_matches(
    element_key: str,
    model_outputs: list[ModelOutput],
) -> tuple[int, int]:
    """Count match/mismatch votes for a specific element across models.

    Inspects ``model_output.pico_assessment[element_key].match`` for
    each output. Outputs without the element key are skipped.

    Args:
        element_key: The assessment element to inspect (e.g., "population").
        model_outputs: LLM outputs with pico_assessment dicts.

    Returns:
        Tuple of (n_match, n_mismatch).
    """
    n_match = 0
    n_mismatch = 0

    for output in model_outputs:
        assessment = output.pico_assessment.get(element_key)
        if assessment is None:
            continue
        if assessment.match:
            n_match += 1
        else:
            n_mismatch += 1

    return n_match, n_mismatch
