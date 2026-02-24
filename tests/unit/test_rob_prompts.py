"""Tests for the unified RoB prompt builder."""
from __future__ import annotations

from metascreener.module3_quality.prompts.rob_v1 import build_rob_prompt
from metascreener.module3_quality.tools.quadas2 import QUADAS2Schema
from metascreener.module3_quality.tools.rob2 import RoB2Schema
from metascreener.module3_quality.tools.robins_i import ROBINSISchema


class TestBuildRobPrompt:
    """Tests for the unified prompt builder."""

    def test_prompt_contains_tool_name(self) -> None:
        prompt = build_rob_prompt(RoB2Schema(), "Some paper text here.")
        assert "RoB 2" in prompt or "rob2" in prompt.lower()

    def test_prompt_contains_paper_text(self) -> None:
        prompt = build_rob_prompt(RoB2Schema(), "The study enrolled 500 patients.")
        assert "The study enrolled 500 patients." in prompt

    def test_prompt_contains_all_domains(self) -> None:
        schema = RoB2Schema()
        prompt = build_rob_prompt(schema, "text")
        for domain in schema.domains:
            assert domain.name in prompt

    def test_prompt_contains_signaling_questions(self) -> None:
        schema = RoB2Schema()
        prompt = build_rob_prompt(schema, "text")
        # Check at least one signaling question is present
        assert "1.1" in prompt

    def test_prompt_contains_json_output_format(self) -> None:
        prompt = build_rob_prompt(RoB2Schema(), "text")
        assert "judgement" in prompt
        assert "rationale" in prompt
        assert "supporting_quotes" in prompt

    def test_prompt_contains_judgement_options(self) -> None:
        prompt = build_rob_prompt(RoB2Schema(), "text")
        assert "low" in prompt.lower()
        assert "some_concerns" in prompt.lower() or "some concerns" in prompt.lower()
        assert "high" in prompt.lower()

    def test_robins_i_prompt_has_seven_domains(self) -> None:
        schema = ROBINSISchema()
        prompt = build_rob_prompt(schema, "text")
        for domain in schema.domains:
            assert domain.name in prompt

    def test_quadas2_prompt_has_four_domains(self) -> None:
        schema = QUADAS2Schema()
        prompt = build_rob_prompt(schema, "text")
        for domain in schema.domains:
            assert domain.name in prompt

    def test_prompt_domain_keys_use_enum_values(self) -> None:
        """Output JSON keys should use RoBDomain enum values."""
        prompt = build_rob_prompt(RoB2Schema(), "text")
        assert "rob2_d1_randomization" in prompt
