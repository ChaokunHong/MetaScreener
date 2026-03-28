"""Core enumerations for MetaScreener 2.0."""
from __future__ import annotations

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
    SOME_CONCERNS = "some_concerns"  # RoB 2 specific
    MODERATE = "moderate"            # ROBINS-I specific
    HIGH = "high"
    SERIOUS = "serious"              # ROBINS-I specific
    CRITICAL = "critical"            # ROBINS-I specific
    UNCLEAR = "unclear"


class ExtractionFieldType(StrEnum):
    """Data type for extraction form fields."""

    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    LIST = "list"
    CATEGORICAL = "categorical"


class SheetRole(StrEnum):
    """Role of a sheet within an extraction template."""

    DATA = "data"
    MAPPING = "mapping"
    REFERENCE = "reference"
    DOCUMENTATION = "documentation"


class SheetCardinality(StrEnum):
    """How many rows a sheet produces per study."""

    ONE_PER_STUDY = "one_per_study"
    MANY_PER_STUDY = "many_per_study"


class FieldRole(StrEnum):
    """Role of a field in extraction: what should happen to it."""

    EXTRACT = "extract"
    AUTO_CALC = "auto_calc"
    LOOKUP = "lookup"
    OVERRIDE = "override"
    METADATA = "metadata"
    QC_FLAG = "qc_flag"


class Confidence(StrEnum):
    """Confidence level for an extracted cell value."""

    VERIFIED = "verified"   # table direct read + all validations pass
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SINGLE = "single"
    FAILED = "failed"       # extraction failed

    def downgrade(self) -> "Confidence":
        """Return confidence one level lower (floors at FAILED)."""
        order = list(Confidence)
        idx = order.index(self)
        return order[min(idx + 1, len(order) - 1)]

    @property
    def needs_review(self) -> bool:
        """Whether this confidence level requires human review."""
        return self in (Confidence.LOW, Confidence.FAILED)


class ScreeningStage(StrEnum):
    """Screening stage identifier."""

    TITLE_ABSTRACT = "ta"
    FULL_TEXT = "ft"


class CriteriaFramework(StrEnum):
    """Systematic review criteria framework type."""

    PICO = "pico"
    PEO = "peo"
    SPIDER = "spider"
    PCC = "pcc"
    PIRD = "pird"
    PIF = "pif"
    PECO = "peco"
    CUSTOM = "custom"


class WizardMode(StrEnum):
    """Criteria wizard interaction mode."""

    SMART = "smart"
    GUIDED = "guided"


class CriteriaInputMode(StrEnum):
    """How criteria input is provided."""

    TEXT = "text"
    TOPIC = "topic"
    YAML = "yaml"
    EXAMPLES = "examples"


class DisagreementType(StrEnum):
    """Type of inter-model disagreement (informational)."""

    CONSENSUS = "consensus"
    DECISION_SPLIT = "decision_split"
    SCORE_DIVERGENCE = "score_divergence"
    CONFIDENCE_MISMATCH = "confidence_mismatch"
    RATIONALE_CONFLICT = "rationale_conflict"


class ConflictPattern(StrEnum):
    """Element-level conflict pattern from ECS analysis."""

    NONE = "none"
    POPULATION_CONFLICT = "population_conflict"
    INTERVENTION_CONFLICT = "intervention_conflict"
    OUTCOME_CONFLICT = "outcome_conflict"
    MULTI_ELEMENT_CONFLICT = "multi_element_conflict"


class FieldSemanticTag(StrEnum):
    """Semantic classification of extraction fields for numerical validation."""

    SAMPLE_SIZE_TOTAL = "n_total"
    SAMPLE_SIZE_ARM = "n_arm"
    EVENTS_ARM = "events_arm"
    MEAN = "mean"
    SD = "sd"
    SE = "se"
    MEDIAN = "median"
    IQR_LOWER = "iqr_lower"
    IQR_UPPER = "iqr_upper"
    PROPORTION = "proportion"
    EFFECT_ESTIMATE = "effect_estimate"
    CI_LOWER = "ci_lower"
    CI_UPPER = "ci_upper"
    P_VALUE = "p_value"
    AGE = "age"
    PERCENTAGE = "percentage"
    STUDY_ID = "study_id"
    INTERVENTION = "intervention"
    COMPARATOR = "comparator"
    OUTCOME = "outcome"
    FOLLOW_UP = "follow_up"
