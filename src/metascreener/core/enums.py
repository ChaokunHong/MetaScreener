"""Core enumerations for MetaScreener 2.0."""
from enum import IntEnum, StrEnum


class Decision(StrEnum):
    """Screening decision for a single paper."""

    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class Tier(IntEnum):
    """Hierarchical decision routing tier (Layer 4).

    Lower value = higher priority.
    """

    ZERO = 0   # Rule override → AUTO-EXCLUDE
    ONE = 1    # All models agree + high confidence → AUTO
    TWO = 2    # Majority + mid confidence → AUTO-INCLUDE
    THREE = 3  # No consensus → HUMAN_REVIEW


class ConfidenceLevel(StrEnum):
    """Qualitative confidence level."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class StudyType(StrEnum):
    """Study design classification."""

    RCT = "rct"
    OBSERVATIONAL = "observational"
    DIAGNOSTIC = "diagnostic"
    REVIEW = "review"
    EDITORIAL = "editorial"
    LETTER = "letter"
    COMMENT = "comment"
    ERRATUM = "erratum"
    OTHER = "other"
    UNKNOWN = "unknown"


class RoBDomain(StrEnum):
    """Risk of Bias assessment domains (shared prefix convention)."""

    # RoB 2 domains (RCTs)
    ROB2_RANDOMIZATION = "rob2_d1_randomization"
    ROB2_DEVIATIONS = "rob2_d2_deviations"
    ROB2_MISSING_DATA = "rob2_d3_missing_data"
    ROB2_MEASUREMENT = "rob2_d4_measurement"
    ROB2_REPORTING = "rob2_d5_reporting"

    # ROBINS-I domains (observational)
    ROBINS_CONFOUNDING = "robins_d1_confounding"
    ROBINS_SELECTION = "robins_d2_selection"
    ROBINS_CLASSIFICATION = "robins_d3_classification"
    ROBINS_DEVIATIONS = "robins_d4_deviations"
    ROBINS_MISSING_DATA = "robins_d5_missing_data"
    ROBINS_MEASUREMENT = "robins_d6_measurement"
    ROBINS_REPORTING = "robins_d7_reporting"

    # QUADAS-2 domains (diagnostic)
    QUADAS_PATIENT_SELECTION = "quadas_d1_patient_selection"
    QUADAS_INDEX_TEST = "quadas_d2_index_test"
    QUADAS_REFERENCE_STANDARD = "quadas_d3_reference_standard"
    QUADAS_FLOW_TIMING = "quadas_d4_flow_timing"


class RoBJudgement(StrEnum):
    """Risk of Bias judgement for a single domain."""

    LOW = "low"
    HIGH = "high"
    UNCLEAR = "unclear"
    SOME_CONCERNS = "some_concerns"  # RoB 2 specific


class ExtractionFieldType(StrEnum):
    """Data type for extraction form fields."""

    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    LIST = "list"


class ScreeningStage(StrEnum):
    """Screening stage identifier."""

    TITLE_ABSTRACT = "ta"
    FULL_TEXT = "ft"
