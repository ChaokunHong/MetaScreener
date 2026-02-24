"""Framework element definitions for each SR criteria framework.

Each framework specifies required/optional elements and human-readable labels.
"""
from __future__ import annotations

from metascreener.core.enums import CriteriaFramework

FRAMEWORK_ELEMENTS: dict[CriteriaFramework, dict[str, list[str] | dict[str, str]]] = {
    CriteriaFramework.PICO: {
        "required": ["population", "intervention"],
        "optional": ["comparison", "outcome"],
        "labels": {
            "population": "Population",
            "intervention": "Intervention",
            "comparison": "Comparison",
            "outcome": "Outcome",
        },
    },
    CriteriaFramework.PEO: {
        "required": ["population", "exposure"],
        "optional": ["outcome"],
        "labels": {
            "population": "Population",
            "exposure": "Exposure",
            "outcome": "Outcome",
        },
    },
    CriteriaFramework.SPIDER: {
        "required": ["sample", "phenomenon_of_interest"],
        "optional": ["design", "evaluation", "research_type"],
        "labels": {
            "sample": "Sample",
            "phenomenon_of_interest": "Phenomenon of Interest",
            "design": "Design",
            "evaluation": "Evaluation",
            "research_type": "Research Type",
        },
    },
    CriteriaFramework.PCC: {
        "required": ["population", "concept"],
        "optional": ["context"],
        "labels": {
            "population": "Population",
            "concept": "Concept",
            "context": "Context",
        },
    },
    CriteriaFramework.PIRD: {
        "required": ["population", "index_test"],
        "optional": ["reference_standard", "diagnosis"],
        "labels": {
            "population": "Population",
            "index_test": "Index Test",
            "reference_standard": "Reference Standard",
            "diagnosis": "Diagnosis/Target Condition",
        },
    },
    CriteriaFramework.PIF: {
        "required": ["population", "index_factor"],
        "optional": ["follow_up"],
        "labels": {
            "population": "Population",
            "index_factor": "Index/Prognostic Factor",
            "follow_up": "Follow-up/Outcome",
        },
    },
    CriteriaFramework.PECO: {
        "required": ["population", "exposure"],
        "optional": ["comparator", "outcome"],
        "labels": {
            "population": "Population",
            "exposure": "Exposure",
            "comparator": "Comparator",
            "outcome": "Outcome",
        },
    },
    CriteriaFramework.CUSTOM: {
        "required": [],
        "optional": [],
        "labels": {},
    },
}
