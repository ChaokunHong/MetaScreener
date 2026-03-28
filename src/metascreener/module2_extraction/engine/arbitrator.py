"""Arbitrator: Resolve disagreements between dual-model extractions (Task 22).

When two LLM runs disagree on a field value, the Arbitrator presents both
values and their evidence to a third model and parses its verdict.
"""
from __future__ import annotations

import json
import textwrap
from typing import Any

from metascreener.module2_extraction.validation.models import ArbitrationResult


class Arbitrator:
    """Resolve disagreements between dual-model extractions.

    Sends a structured prompt to a third LLM backend that presents both
    candidate values and their evidence sentences.  The model responds with
    a JSON object selecting one of the values (or neither) and providing
    reasoning and a supporting evidence sentence.
    """

    async def arbitrate(
        self,
        field_name: str,
        value_a: Any,
        evidence_a: str | None,
        value_b: Any,
        evidence_b: str | None,
        context_text: str,
        backend: Any,
    ) -> ArbitrationResult:
        """Ask a third model to resolve a disagreement between two extracted values.

        Args:
            field_name: Name of the field where the two models disagreed.
            value_a: Value extracted by model A.
            evidence_a: Evidence sentence cited by model A (may be ``None``).
            value_b: Value extracted by model B.
            evidence_b: Evidence sentence cited by model B (may be ``None``).
            context_text: The original source text passage for grounding.
            backend: An LLM backend with an ``async complete(prompt, seed)`` method.

        Returns:
            :class:`ArbitrationResult` with the chosen value, reasoning, and
            optional evidence sentence.
        """
        prompt = self._build_prompt(
            field_name, value_a, evidence_a, value_b, evidence_b, context_text
        )
        response = await backend.complete(prompt, seed=42)
        return self._parse_response(response, value_a, value_b)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        field_name: str,
        value_a: Any,
        evidence_a: str | None,
        value_b: Any,
        evidence_b: str | None,
        context_text: str,
    ) -> str:
        """Build a structured arbitration prompt for the third LLM.

        The prompt presents:
        - The field name and original context text.
        - Value A with its evidence sentence.
        - Value B with its evidence sentence.
        - Clear instructions to return a JSON object.

        Args:
            field_name: Name of the field being arbitrated.
            value_a: Candidate value from model A.
            evidence_a: Supporting evidence from model A.
            value_b: Candidate value from model B.
            evidence_b: Supporting evidence from model B.
            context_text: Original source text.

        Returns:
            Prompt string to send to the arbitrating LLM.
        """
        evidence_a_text = evidence_a if evidence_a else "(no evidence provided)"
        evidence_b_text = evidence_b if evidence_b else "(no evidence provided)"

        return textwrap.dedent(f"""
            You are an expert data extractor for systematic reviews.
            Two models disagreed on the value of the field "{field_name}".

            === Original Source Text ===
            {context_text}

            === Model A ===
            Value: {value_a}
            Evidence: {evidence_a_text}

            === Model B ===
            Value: {value_b}
            Evidence: {evidence_b_text}

            === Task ===
            Determine which value is correct based on the source text.
            Respond ONLY with a valid JSON object in this exact format:
            {{
              "chosen": "A" | "B" | "neither",
              "correct_value": <the correct value, or null if neither>,
              "reasoning": "<brief explanation>",
              "evidence_sentence": "<the sentence from the source text that supports your choice, or null>"
            }}
        """).strip()

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self, response: str, value_a: Any, value_b: Any
    ) -> ArbitrationResult:
        """Parse the LLM arbitration response into an :class:`ArbitrationResult`.

        Attempts to extract a JSON object from the response.  If parsing fails
        or required fields are missing, defaults to choosing A.

        Args:
            response: Raw string response from the LLM.
            value_a: Original value from model A (used as fallback).
            value_b: Original value from model B (used as fallback when B is chosen).

        Returns:
            :class:`ArbitrationResult` with chosen, chosen_value, reasoning,
            and optional evidence_sentence.
        """
        try:
            data = _extract_json(response)
            chosen = data.get("chosen", "A")
            correct_value = data.get("correct_value")
            reasoning = data.get("reasoning", "")
            evidence_sentence = data.get("evidence_sentence")

            if chosen == "A":
                chosen_value = correct_value if correct_value is not None else value_a
            elif chosen == "B":
                chosen_value = correct_value if correct_value is not None else value_b
            else:
                chosen_value = correct_value  # may be None

            return ArbitrationResult(
                chosen=chosen,
                chosen_value=chosen_value,
                reasoning=reasoning,
                evidence_sentence=evidence_sentence,
            )

        except Exception:
            return ArbitrationResult(
                chosen="A",
                chosen_value=value_a,
                reasoning="Parse failed, defaulting to A",
                evidence_sentence=None,
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict:
    """Extract and parse the first JSON object found in a string.

    Tries full-text parsing first.  Falls back to scanning for the first
    ``{`` ... ``}`` block.

    Args:
        text: Raw LLM response string.

    Returns:
        Parsed dictionary.

    Raises:
        ValueError: If no valid JSON object can be found.
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty response")

    # Fast path: entire response is JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Scan for embedded JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in response: {text[:120]!r}")

    return json.loads(text[start : end + 1])
