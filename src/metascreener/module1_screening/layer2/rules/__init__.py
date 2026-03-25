"""MetaScreener Layer 2 Rules — Individual hard and soft rule implementations."""
from __future__ import annotations

from metascreener.module1_screening.layer2.rules.base import Rule
from metascreener.module1_screening.layer2.rules.intervention import (
    AmbiguousInterventionRule,
)
from metascreener.module1_screening.layer2.rules.language import LanguageRule
from metascreener.module1_screening.layer2.rules.outcome import (
    OutcomePartialMatchRule,
)
from metascreener.module1_screening.layer2.rules.population import (
    PopulationPartialMatchRule,
)
from metascreener.module1_screening.layer2.rules.publication_type import (
    PublicationTypeRule,
)
from metascreener.module1_screening.layer2.rules.retraction import RetractionRule
from metascreener.module1_screening.layer2.rules.study_design import StudyDesignRule


def get_default_rules() -> list[Rule]:
    """Return the default set of 7 screening rules (4 hard + 3 soft).

    Returns:
        List of Rule instances in evaluation order.
    """
    return [
        # Hard rules (checked first)
        RetractionRule(),
        PublicationTypeRule(),
        LanguageRule(),
        StudyDesignRule(),
        # Soft rules
        PopulationPartialMatchRule(),
        OutcomePartialMatchRule(),
        AmbiguousInterventionRule(),
    ]


__all__ = ["Rule", "get_default_rules"]
