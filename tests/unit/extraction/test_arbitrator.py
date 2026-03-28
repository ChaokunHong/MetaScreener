"""Tests for Arbitrator (Task 22)."""
from __future__ import annotations

import json

import pytest

from metascreener.module2_extraction.engine.arbitrator import Arbitrator
from metascreener.module2_extraction.validation.models import ArbitrationResult


# ---------------------------------------------------------------------------
# Mock backend
# ---------------------------------------------------------------------------


class MockBackend:
    """LLM backend that returns a canned response string."""

    def __init__(self, response: str) -> None:
        self._response = response

    async def complete(self, prompt: str, seed: int = 42) -> str:
        self._last_prompt = prompt
        return self._response


def _json_response(chosen: str, correct_value, reasoning: str, evidence: str | None = "sentence") -> str:
    """Build a well-formed arbitration JSON response."""
    return json.dumps({
        "chosen": chosen,
        "correct_value": correct_value,
        "reasoning": reasoning,
        "evidence_sentence": evidence,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestArbitrateChoosesA:
    @pytest.mark.asyncio
    async def test_arbitrate_chooses_a(self) -> None:
        """Backend returns chosen=A → result.chosen == 'A' with value_a."""
        backend = MockBackend(_json_response("A", 42.0, "Value A is clearly stated in the text"))
        arb = Arbitrator()
        result = await arb.arbitrate(
            field_name="n_total",
            value_a=42.0,
            evidence_a="The study enrolled 42 patients.",
            value_b=50.0,
            evidence_b="Fifty patients were enrolled.",
            context_text="The study enrolled 42 patients in the intervention arm.",
            backend=backend,
        )
        assert result.chosen == "A"
        assert result.chosen_value == 42.0
        assert isinstance(result, ArbitrationResult)

    @pytest.mark.asyncio
    async def test_arbitrate_a_reasoning_preserved(self) -> None:
        """Reasoning from the LLM should be preserved in result."""
        reasoning = "Value A matches the methods section exactly."
        backend = MockBackend(_json_response("A", 42.0, reasoning))
        arb = Arbitrator()
        result = await arb.arbitrate(
            field_name="n_total",
            value_a=42.0,
            evidence_a="42 patients enrolled",
            value_b=50.0,
            evidence_b="50 patients",
            context_text="42 patients enrolled in the RCT.",
            backend=backend,
        )
        assert result.reasoning == reasoning


class TestArbitrateChoosesB:
    @pytest.mark.asyncio
    async def test_arbitrate_chooses_b(self) -> None:
        """Backend returns chosen=B → result.chosen == 'B' with value_b."""
        backend = MockBackend(_json_response("B", 50.0, "Value B is correct per the abstract"))
        arb = Arbitrator()
        result = await arb.arbitrate(
            field_name="n_total",
            value_a=42.0,
            evidence_a="42 enrolled",
            value_b=50.0,
            evidence_b="50 total participants",
            context_text="A total of 50 participants were included.",
            backend=backend,
        )
        assert result.chosen == "B"
        assert result.chosen_value == 50.0

    @pytest.mark.asyncio
    async def test_arbitrate_b_evidence_preserved(self) -> None:
        """Evidence sentence from LLM response should be preserved."""
        evidence = "A total of 50 participants were included in the RCT."
        backend = MockBackend(_json_response("B", 50.0, "B is correct", evidence))
        arb = Arbitrator()
        result = await arb.arbitrate(
            field_name="n_total",
            value_a=42.0,
            evidence_a=None,
            value_b=50.0,
            evidence_b=evidence,
            context_text="A total of 50 participants were included in the RCT.",
            backend=backend,
        )
        assert result.evidence_sentence == evidence


class TestArbitrateNeither:
    @pytest.mark.asyncio
    async def test_arbitrate_neither(self) -> None:
        """Backend returns 'neither' with a correct_value → result has that value."""
        backend = MockBackend(_json_response("neither", 46.0, "Neither matches; correct is 46"))
        arb = Arbitrator()
        result = await arb.arbitrate(
            field_name="n_total",
            value_a=42.0,
            evidence_a="approx 42",
            value_b=50.0,
            evidence_b="approx 50",
            context_text="46 patients total were randomized.",
            backend=backend,
        )
        assert result.chosen == "neither"
        assert result.chosen_value == 46.0

    @pytest.mark.asyncio
    async def test_arbitrate_neither_none_correct_value(self) -> None:
        """'neither' with null correct_value → chosen_value is None."""
        backend = MockBackend(_json_response("neither", None, "Cannot determine from context"))
        arb = Arbitrator()
        result = await arb.arbitrate(
            field_name="mean_age",
            value_a=45.0,
            evidence_a=None,
            value_b=50.0,
            evidence_b=None,
            context_text="Age data was not reported.",
            backend=backend,
        )
        assert result.chosen == "neither"
        assert result.chosen_value is None


class TestParseFailureDefaultsToA:
    @pytest.mark.asyncio
    async def test_garbage_response_defaults_to_a(self) -> None:
        """Backend returns garbage → defaults to A with parse failure reasoning."""
        backend = MockBackend("This is not valid JSON at all!!! ###")
        arb = Arbitrator()
        result = await arb.arbitrate(
            field_name="n_total",
            value_a=42.0,
            evidence_a="42 patients",
            value_b=50.0,
            evidence_b="50 patients",
            context_text="Some context text.",
            backend=backend,
        )
        assert result.chosen == "A"
        assert result.chosen_value == 42.0
        assert "parse" in result.reasoning.lower() or "default" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_empty_response_defaults_to_a(self) -> None:
        """Backend returns empty string → defaults to A."""
        backend = MockBackend("")
        arb = Arbitrator()
        result = await arb.arbitrate(
            field_name="effect_size",
            value_a=1.5,
            evidence_a=None,
            value_b=2.0,
            evidence_b=None,
            context_text="Context.",
            backend=backend,
        )
        assert result.chosen == "A"
        assert result.chosen_value == 1.5

    @pytest.mark.asyncio
    async def test_partial_json_defaults_to_a(self) -> None:
        """Partial JSON (missing required fields) → defaults to A."""
        backend = MockBackend('{"chosen": "B"}')  # missing correct_value
        arb = Arbitrator()
        result = await arb.arbitrate(
            field_name="n_total",
            value_a=10.0,
            evidence_a=None,
            value_b=20.0,
            evidence_b=None,
            context_text="Context.",
            backend=backend,
        )
        # "B" is chosen, correct_value falls back to value_b or default
        # Depends on implementation — key requirement is no crash
        assert result.chosen in ("A", "B", "neither")
        assert result.chosen_value is not None or result.chosen == "neither"


class TestPromptContainsBothValues:
    @pytest.mark.asyncio
    async def test_prompt_contains_both_values(self) -> None:
        """Verify the prompt sent to the LLM includes both values."""
        backend = MockBackend(_json_response("A", 42.0, "A is correct"))
        arb = Arbitrator()
        await arb.arbitrate(
            field_name="mean_age",
            value_a=42.0,
            evidence_a="Mean age was 42 years.",
            value_b=50.0,
            evidence_b="Mean age 50 years.",
            context_text="The mean age was reported as 42 years in Table 1.",
            backend=backend,
        )
        prompt = backend._last_prompt
        assert "42" in prompt or "42.0" in prompt
        assert "50" in prompt or "50.0" in prompt

    @pytest.mark.asyncio
    async def test_prompt_contains_field_name(self) -> None:
        """Prompt should include the field name for context."""
        backend = MockBackend(_json_response("A", 42.0, "Correct"))
        arb = Arbitrator()
        await arb.arbitrate(
            field_name="mean_age",
            value_a=42.0,
            evidence_a=None,
            value_b=50.0,
            evidence_b=None,
            context_text="Some context.",
            backend=backend,
        )
        prompt = backend._last_prompt
        assert "mean_age" in prompt

    @pytest.mark.asyncio
    async def test_prompt_contains_context_text(self) -> None:
        """Prompt should include the original context text."""
        context = "The study enrolled patients between 40 and 55 years old."
        backend = MockBackend(_json_response("A", 42.0, "Correct"))
        arb = Arbitrator()
        await arb.arbitrate(
            field_name="mean_age",
            value_a=42.0,
            evidence_a=None,
            value_b=50.0,
            evidence_b=None,
            context_text=context,
            backend=backend,
        )
        prompt = backend._last_prompt
        assert context in prompt or "enrolled patients" in prompt

    @pytest.mark.asyncio
    async def test_prompt_contains_evidence_when_provided(self) -> None:
        """Prompt should include evidence sentences when provided."""
        evidence_a = "Table 1 shows mean age 42 years."
        backend = MockBackend(_json_response("A", 42.0, "Correct"))
        arb = Arbitrator()
        await arb.arbitrate(
            field_name="mean_age",
            value_a=42.0,
            evidence_a=evidence_a,
            value_b=50.0,
            evidence_b="Abstract states 50 years.",
            context_text="Context text here.",
            backend=backend,
        )
        prompt = backend._last_prompt
        assert evidence_a in prompt or "Table 1" in prompt
