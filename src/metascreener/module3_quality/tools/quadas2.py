"""QUADAS-2 schema for diagnostic accuracy studies.

Implements the 4-domain, 11-signaling-question schema from the
QUADAS-2 (Quality Assessment of Diagnostic Accuracy Studies) tool.

Reference:
    Whiting PF et al. QUADAS-2: A revised tool for the quality
    assessment of diagnostic accuracy studies. Ann Intern Med
    2011; 155(8): 529-536.
"""
from __future__ import annotations

from metascreener.core.enums import RoBDomain, RoBJudgement
from metascreener.module3_quality.tools.base import (
    DomainSchema,
    RoBToolSchema,
    SignalingQuestion,
)

# Response options for QUADAS-2 signaling questions.
_RESPONSE_OPTIONS: list[str] = ["Yes", "No", "Unclear"]

# Judgement options for QUADAS-2 domains.
_JUDGEMENT_OPTIONS: list[RoBJudgement] = [
    RoBJudgement.LOW,
    RoBJudgement.HIGH,
    RoBJudgement.UNCLEAR,
]

# Severity ranking for QUADAS-2 judgements.
# QUADAS-2 uses LOW/HIGH/UNCLEAR; other RoBJudgement values are
# mapped to approximate equivalents for interoperability.
_QUADAS_SEVERITY: dict[RoBJudgement, int] = {
    RoBJudgement.LOW: 0,
    RoBJudgement.UNCLEAR: 1,
    RoBJudgement.SOME_CONCERNS: 1,
    RoBJudgement.MODERATE: 1,
    RoBJudgement.HIGH: 2,
    RoBJudgement.SERIOUS: 2,
    RoBJudgement.CRITICAL: 3,
}


def _build_domains() -> list[DomainSchema]:
    """Construct all four QUADAS-2 domains with their signaling questions.

    Returns:
        List of four ``DomainSchema`` instances ordered D1-D4.
    """
    d1_patient_selection = DomainSchema(
        domain=RoBDomain.QUADAS_PATIENT_SELECTION,
        name="Patient selection",
        signaling_questions=[
            SignalingQuestion(
                id="1.1",
                text=(
                    "Was a consecutive or random sample of patients "
                    "enrolled?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="1.2",
                text="Was a case-control design avoided?",
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="1.3",
                text="Did the study avoid inappropriate exclusions?",
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d2_index_test = DomainSchema(
        domain=RoBDomain.QUADAS_INDEX_TEST,
        name="Index test",
        signaling_questions=[
            SignalingQuestion(
                id="2.1",
                text=(
                    "Were the index test results interpreted without "
                    "knowledge of the results of the reference standard?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.2",
                text=(
                    "If a threshold was used, was it pre-specified?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.3",
                text=(
                    "Could the conduct or interpretation of the index "
                    "test have introduced bias?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d3_reference_standard = DomainSchema(
        domain=RoBDomain.QUADAS_REFERENCE_STANDARD,
        name="Reference standard",
        signaling_questions=[
            SignalingQuestion(
                id="3.1",
                text=(
                    "Is the reference standard likely to correctly "
                    "classify the target condition?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="3.2",
                text=(
                    "Were the reference standard results interpreted "
                    "without knowledge of the results of the index test?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="3.3",
                text=(
                    "Could the reference standard, its conduct, or its "
                    "interpretation have introduced bias?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d4_flow_timing = DomainSchema(
        domain=RoBDomain.QUADAS_FLOW_TIMING,
        name="Flow and timing",
        signaling_questions=[
            SignalingQuestion(
                id="4.1",
                text=(
                    "Was there an appropriate interval between index "
                    "test and reference standard?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="4.2",
                text=(
                    "Did all patients receive the same reference "
                    "standard?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    return [
        d1_patient_selection,
        d2_index_test,
        d3_reference_standard,
        d4_flow_timing,
    ]


class QUADAS2Schema(RoBToolSchema):
    """QUADAS-2 tool schema for diagnostic accuracy studies.

    Defines 4 domains with 11 signaling questions following the official
    QUADAS-2 instrument. Overall judgement follows the worst-case rule:
    HIGH > UNCLEAR > LOW.

    Example:
        >>> schema = QUADAS2Schema()
        >>> schema.tool_name
        'quadas2'
        >>> len(schema.domains)
        4
    """

    def __init__(self) -> None:
        self._domains = _build_domains()

    @property
    def tool_name(self) -> str:
        """Short identifier for this tool.

        Returns:
            The string ``'quadas2'``.
        """
        return "quadas2"

    @property
    def domains(self) -> list[DomainSchema]:
        """All four QUADAS-2 assessment domains.

        Returns:
            Ordered list of domain schemas (D1-D4).
        """
        return list(self._domains)

    def get_overall_judgement(
        self, domain_judgements: list[RoBJudgement]
    ) -> RoBJudgement:
        """Compute overall RoB judgement from per-domain judgements.

        Applies the QUADAS-2 worst-case rule:
        - Any HIGH in any domain yields HIGH overall.
        - Any UNCLEAR (without HIGH) yields UNCLEAR overall.
        - All LOW yields LOW overall.

        Args:
            domain_judgements: One judgement per domain (expects 4 values).

        Returns:
            The overall RoB judgement.
        """
        max_rank = max(
            self.get_severity_rank(j) for j in domain_judgements
        )
        # Map rank back to the canonical QUADAS-2 judgement.
        _rank_to_judgement: dict[int, RoBJudgement] = {
            0: RoBJudgement.LOW,
            1: RoBJudgement.UNCLEAR,
            2: RoBJudgement.HIGH,
            3: RoBJudgement.HIGH,  # CRITICAL mapped to HIGH
        }
        return _rank_to_judgement.get(max_rank, RoBJudgement.UNCLEAR)

    def get_severity_rank(self, judgement: RoBJudgement) -> int:
        """Return numeric severity rank for QUADAS-2 judgements.

        QUADAS-2 uses a 3-level scale: LOW (0), UNCLEAR (1), HIGH (2).
        Other RoBJudgement values are mapped for interoperability:
        SOME_CONCERNS and MODERATE map to UNCLEAR (1), SERIOUS maps to
        HIGH (2), and CRITICAL maps to rank 3.

        Args:
            judgement: A RoB judgement value.

        Returns:
            Integer severity rank (0-3).
        """
        return _QUADAS_SEVERITY.get(judgement, 1)
