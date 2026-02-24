"""ROBINS-I schema for non-randomized studies of interventions.

Implements the 7-domain, 24-signaling-question schema from the
ROBINS-I (Risk Of Bias In Non-randomized Studies - of Interventions)
tool for observational studies.

Reference:
    Sterne JAC et al. ROBINS-I: a tool for assessing risk of bias in
    non-randomised studies of interventions. BMJ 2016; 355: i4919.
"""
from __future__ import annotations

from metascreener.core.enums import RoBDomain, RoBJudgement
from metascreener.module3_quality.tools.base import (
    DomainSchema,
    RoBToolSchema,
    SignalingQuestion,
)

# Standard response options for all ROBINS-I signaling questions.
_RESPONSE_OPTIONS: list[str] = [
    "Yes",
    "Probably yes",
    "Probably no",
    "No",
    "No information",
]

# Standard judgement options for all ROBINS-I domains.
_JUDGEMENT_OPTIONS: list[RoBJudgement] = [
    RoBJudgement.LOW,
    RoBJudgement.MODERATE,
    RoBJudgement.SERIOUS,
    RoBJudgement.CRITICAL,
]

# Severity ranking for ROBINS-I judgements.
# UNCLEAR and SOME_CONCERNS are mapped to MODERATE level.
_ROBINS_SEVERITY: dict[RoBJudgement, int] = {
    RoBJudgement.LOW: 0,
    RoBJudgement.MODERATE: 1,
    RoBJudgement.UNCLEAR: 1,  # Treated as MODERATE
    RoBJudgement.SOME_CONCERNS: 1,  # Treated as MODERATE
    RoBJudgement.SERIOUS: 2,
    RoBJudgement.HIGH: 2,  # Mapped to SERIOUS level
    RoBJudgement.CRITICAL: 3,
}


def _build_domains() -> list[DomainSchema]:
    """Construct all seven ROBINS-I domains with their signaling questions.

    Returns:
        List of seven ``DomainSchema`` instances ordered D1-D7.
    """
    d1_confounding = DomainSchema(
        domain=RoBDomain.ROBINS_CONFOUNDING,
        name="Bias due to confounding",
        signaling_questions=[
            SignalingQuestion(
                id="1.1",
                text=(
                    "Is there potential for confounding of the effect "
                    "of intervention in this study?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="1.2",
                text=(
                    "Was the analysis based on splitting participants' "
                    "follow up time according to intervention received?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="1.3",
                text=(
                    "Were intervention discontinuations or switches likely "
                    "to be related to factors that are prognostic for the "
                    "outcome?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="1.4",
                text=(
                    "Did the authors use an appropriate analysis method "
                    "that controlled for all the important confounding "
                    "domains?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d2_selection = DomainSchema(
        domain=RoBDomain.ROBINS_SELECTION,
        name="Bias in selection of participants into the study",
        signaling_questions=[
            SignalingQuestion(
                id="2.1",
                text=(
                    "Was selection of participants into the study "
                    "related to intervention and outcome?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.2",
                text=(
                    "Was the start of follow-up and start of intervention "
                    "coincident for most subjects?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.3",
                text=(
                    "Were adjustment techniques used to correct for the "
                    "presence of selection biases?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="2.4",
                text=(
                    "Were post-baseline variables that influenced selection "
                    "also adjusted for in the analyses?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d3_classification = DomainSchema(
        domain=RoBDomain.ROBINS_CLASSIFICATION,
        name="Bias in classification of interventions",
        signaling_questions=[
            SignalingQuestion(
                id="3.1",
                text="Were intervention groups clearly defined?",
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="3.2",
                text=(
                    "Was the information used to define intervention groups "
                    "recorded at the start of the intervention?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="3.3",
                text=(
                    "Could classification of intervention status have been "
                    "affected by knowledge of the outcome or risk of the "
                    "outcome?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d4_deviations = DomainSchema(
        domain=RoBDomain.ROBINS_DEVIATIONS,
        name="Bias due to deviations from intended interventions",
        signaling_questions=[
            SignalingQuestion(
                id="4.1",
                text=(
                    "Were there deviations from the intended intervention "
                    "beyond what would be expected in usual practice?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="4.2",
                text=(
                    "If Y/PY: Were these deviations from intended "
                    "intervention unbalanced between groups and likely "
                    "to have affected the outcome?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="4.3",
                text=(
                    "Were important co-interventions balanced across "
                    "intervention groups?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="4.4",
                text=(
                    "Was the intervention implemented successfully for "
                    "most participants?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d5_missing_data = DomainSchema(
        domain=RoBDomain.ROBINS_MISSING_DATA,
        name="Bias due to missing data",
        signaling_questions=[
            SignalingQuestion(
                id="5.1",
                text=(
                    "Were outcome data available for all, or nearly all, "
                    "participants?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="5.2",
                text=(
                    "Were participants excluded due to missing data on "
                    "intervention status?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="5.3",
                text=(
                    "Were participants excluded due to missing data on "
                    "other variables needed for the analysis?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d6_measurement = DomainSchema(
        domain=RoBDomain.ROBINS_MEASUREMENT,
        name="Bias in measurement of outcomes",
        signaling_questions=[
            SignalingQuestion(
                id="6.1",
                text=(
                    "Could the outcome measure have been influenced by "
                    "knowledge of the intervention received?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="6.2",
                text=(
                    "Were outcome assessors aware of the intervention "
                    "received by study participants?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="6.3",
                text=(
                    "Were the methods of outcome assessment comparable "
                    "across intervention groups?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    d7_reporting = DomainSchema(
        domain=RoBDomain.ROBINS_REPORTING,
        name="Bias in selection of the reported result",
        signaling_questions=[
            SignalingQuestion(
                id="7.1",
                text=(
                    "Is the reported effect estimate likely to be selected, "
                    "on the basis of the results, from multiple outcome "
                    "measurements within the outcome domain?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="7.2",
                text=(
                    "Is the reported effect estimate likely to be selected, "
                    "on the basis of the results, from multiple analyses "
                    "of the intervention-outcome relationship?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
            SignalingQuestion(
                id="7.3",
                text=(
                    "Is the reported effect estimate likely to be selected, "
                    "on the basis of the results, from different subgroups?"
                ),
                response_options=_RESPONSE_OPTIONS,
            ),
        ],
        judgement_options=_JUDGEMENT_OPTIONS,
    )

    return [
        d1_confounding,
        d2_selection,
        d3_classification,
        d4_deviations,
        d5_missing_data,
        d6_measurement,
        d7_reporting,
    ]


class ROBINSISchema(RoBToolSchema):
    """ROBINS-I tool schema for non-randomized studies of interventions.

    Defines 7 domains with 24 signaling questions following the official
    ROBINS-I instrument. Overall judgement follows the worst-case rule:
    CRITICAL > SERIOUS > MODERATE > LOW. UNCLEAR is treated at MODERATE
    severity level.

    Example:
        >>> schema = ROBINSISchema()
        >>> schema.tool_name
        'robins_i'
        >>> len(schema.domains)
        7
    """

    def __init__(self) -> None:
        self._domains = _build_domains()

    @property
    def tool_name(self) -> str:
        """Short identifier for this tool.

        Returns:
            The string ``'robins_i'``.
        """
        return "robins_i"

    @property
    def domains(self) -> list[DomainSchema]:
        """All seven ROBINS-I assessment domains.

        Returns:
            Ordered list of domain schemas (D1-D7).
        """
        return list(self._domains)

    def get_overall_judgement(
        self, domain_judgements: list[RoBJudgement]
    ) -> RoBJudgement:
        """Compute overall RoB judgement from per-domain judgements.

        Applies the ROBINS-I worst-case (strictest domain) rule:
        - Any CRITICAL in any domain yields CRITICAL overall.
        - Any SERIOUS (without CRITICAL) yields SERIOUS overall.
        - Any MODERATE (without SERIOUS or CRITICAL) yields MODERATE overall.
        - All LOW yields LOW overall.

        Args:
            domain_judgements: One judgement per domain (expects 7 values).

        Returns:
            The overall RoB judgement.
        """
        max_rank = max(
            self.get_severity_rank(j) for j in domain_judgements
        )
        # Map rank back to the canonical ROBINS-I judgement.
        _rank_to_judgement: dict[int, RoBJudgement] = {
            0: RoBJudgement.LOW,
            1: RoBJudgement.MODERATE,
            2: RoBJudgement.SERIOUS,
            3: RoBJudgement.CRITICAL,
        }
        return _rank_to_judgement.get(max_rank, RoBJudgement.MODERATE)

    def get_severity_rank(self, judgement: RoBJudgement) -> int:
        """Return numeric severity rank for ROBINS-I judgements.

        ROBINS-I uses a 4-level severity scale: LOW (0), MODERATE (1),
        SERIOUS (2), CRITICAL (3). UNCLEAR and SOME_CONCERNS are mapped
        to MODERATE severity (rank 1).

        Args:
            judgement: A RoB judgement value.

        Returns:
            Integer severity rank (0-3).
        """
        return _ROBINS_SEVERITY.get(judgement, 1)
