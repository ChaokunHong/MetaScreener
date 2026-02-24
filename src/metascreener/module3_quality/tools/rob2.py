"""Cochrane RoB 2 schema for randomized controlled trials (RCTs).

Implements the 5-domain, 22-signaling-question schema from the
Cochrane Risk of Bias tool for RCTs (version 2, 2019).

Reference:
    Sterne JAE et al. RoB 2: a revised tool for assessing risk of bias
    in randomised trials. BMJ 2019; 366: l4898.
"""
from __future__ import annotations

from metascreener.core.enums import RoBDomain, RoBJudgement
from metascreener.module3_quality.tools.base import (
    DomainSchema,
    RoBToolSchema,
    SignalingQuestion,
)

# Standard response options for all RoB 2 signaling questions.
_RESPONSE_OPTIONS: list[str] = [
    "Yes",
    "Probably yes",
    "Probably no",
    "No",
    "No information",
]

# Standard judgement options for all RoB 2 domains.
_JUDGEMENT_OPTIONS: list[RoBJudgement] = [
    RoBJudgement.LOW,
    RoBJudgement.SOME_CONCERNS,
    RoBJudgement.HIGH,
]


def _build_domains() -> list[DomainSchema]:
    """Construct all five RoB 2 domains with their signaling questions.

    Returns:
        List of five ``DomainSchema`` instances ordered D1-D5.
    """
    d1_randomization = DomainSchema(
        domain=RoBDomain.ROB2_RANDOMIZATION,
        name="Randomization process",
        signaling_questions=[
            SignalingQuestion(
                id="1.1",
                text=(
                    "Was the allocation sequence random?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="1.2",
                text=(
                    "Was the allocation sequence concealed until participants "
                    "were enrolled and assigned to interventions?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="1.3",
                text=(
                    "Did baseline differences between intervention groups "
                    "suggest a problem with the randomization process?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d2_deviations = DomainSchema(
        domain=RoBDomain.ROB2_DEVIATIONS,
        name="Deviations from intended interventions",
        signaling_questions=[
            SignalingQuestion(
                id="2.1",
                text=(
                    "Were participants aware of their assigned intervention "
                    "during the trial?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.2",
                text=(
                    "Were carers and people delivering the interventions "
                    "aware of participants' assigned intervention during "
                    "the trial?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.3",
                text=(
                    "If Y/PY/NI to 2.1 or 2.2: Were there deviations from "
                    "the intended intervention that arose because of the "
                    "trial context?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.4",
                text=(
                    "If Y/PY to 2.3: Were these deviations likely to have "
                    "affected the outcome?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.5",
                text=(
                    "If Y/PY/NI to 2.4: Were these deviations from intended "
                    "intervention balanced between groups?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.6",
                text=(
                    "Was an appropriate analysis used to estimate the effect "
                    "of assignment to intervention?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.7",
                text=(
                    "If N/PN/NI to 2.6: Was there potential for a substantial "
                    "impact on the result?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d3_missing_data = DomainSchema(
        domain=RoBDomain.ROB2_MISSING_DATA,
        name="Missing outcome data",
        signaling_questions=[
            SignalingQuestion(
                id="3.1",
                text=(
                    "Were data for this outcome available for all, or nearly "
                    "all, participants randomized?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="3.2",
                text=(
                    "If N/PN/NI to 3.1: Is there evidence that the result "
                    "was not biased by missing outcome data?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="3.3",
                text=(
                    "If N/PN to 3.2: Could missingness in the outcome depend "
                    "on its true value?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="3.4",
                text=(
                    "If Y/PY/NI to 3.3: Is it likely that missingness in "
                    "the outcome depended on its true value?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d4_measurement = DomainSchema(
        domain=RoBDomain.ROB2_MEASUREMENT,
        name="Measurement of the outcome",
        signaling_questions=[
            SignalingQuestion(
                id="4.1",
                text=(
                    "Was the method of measuring the outcome inappropriate?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="4.2",
                text=(
                    "Could measurement or ascertainment of the outcome have "
                    "differed between intervention groups?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="4.3",
                text=(
                    "If N/PN/NI to 4.1 and 4.2: Were outcome assessors aware "
                    "of the intervention received by study participants?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="4.4",
                text=(
                    "If Y/PY/NI to 4.3: Could assessment of the outcome have "
                    "been influenced by knowledge of intervention received?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="4.5",
                text=(
                    "If Y/PY/NI to 4.4: Is it likely that assessment of the "
                    "outcome was influenced by knowledge of intervention "
                    "received?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d5_reporting = DomainSchema(
        domain=RoBDomain.ROB2_REPORTING,
        name="Selection of the reported result",
        signaling_questions=[
            SignalingQuestion(
                id="5.1",
                text=(
                    "Were the data that produced this result analysed in "
                    "accordance with a pre-specified analysis plan that was "
                    "finalized before unblinded outcome data were available "
                    "for analysis?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="5.2",
                text=(
                    "Is the numerical result being assessed likely to have "
                    "been selected, on the basis of the results, from "
                    "multiple eligible outcome measurements within the "
                    "outcome domain?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="5.3",
                text=(
                    "Is the numerical result being assessed likely to have "
                    "been selected, on the basis of the results, from "
                    "multiple eligible analyses of the data?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    return [
        d1_randomization,
        d2_deviations,
        d3_missing_data,
        d4_measurement,
        d5_reporting,
    ]


class RoB2Schema(RoBToolSchema):
    """Cochrane Risk of Bias 2 (RoB 2) tool schema for RCTs.

    Defines 5 domains with 22 signaling questions following the
    official Cochrane RoB 2 instrument. Overall judgement follows
    the worst-case rule: any HIGH yields HIGH; any SOME_CONCERNS
    yields SOME_CONCERNS; otherwise LOW.

    Example:
        >>> schema = RoB2Schema()
        >>> schema.tool_name
        'rob2'
        >>> len(schema.domains)
        5
    """

    def __init__(self) -> None:
        self._domains = _build_domains()

    @property
    def tool_name(self) -> str:
        """Short identifier for this tool.

        Returns:
            The string ``'rob2'``.
        """
        return "rob2"

    @property
    def domains(self) -> list[DomainSchema]:
        """All five RoB 2 assessment domains.

        Returns:
            Ordered list of domain schemas (D1-D5).
        """
        return list(self._domains)

    def get_overall_judgement(
        self, domain_judgements: list[RoBJudgement]
    ) -> RoBJudgement:
        """Compute overall RoB judgement from per-domain judgements.

        Applies the Cochrane RoB 2 worst-case rule:
        - Any HIGH in any domain yields HIGH overall.
        - Any SOME_CONCERNS (without HIGH) yields SOME_CONCERNS overall.
        - All LOW yields LOW overall.

        Args:
            domain_judgements: One judgement per domain (expects 5 values).

        Returns:
            The overall RoB judgement.
        """
        if RoBJudgement.HIGH in domain_judgements:
            return RoBJudgement.HIGH
        if RoBJudgement.SOME_CONCERNS in domain_judgements:
            return RoBJudgement.SOME_CONCERNS
        return RoBJudgement.LOW
