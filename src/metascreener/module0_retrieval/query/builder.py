"""Convert ReviewCriteria / PICOCriteria to a BooleanQuery AST.

Semantic role mappings used to route element keys to query groups:

    population  ← {"population", "participants", "patients", "sample"}
    intervention← {"intervention", "exposure", "index_test", "phenomenon"}
    outcome     ← {"outcome", "evaluation", "research_type"}
    additional  ← {"comparison", "comparator", "context", "reference_standard"}
    exclusions  ← all element-level exclude terms + study_design_exclude
"""
from __future__ import annotations

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm

_POP_KEYS: frozenset[str] = frozenset({"population", "participants", "patients", "sample"})
_INT_KEYS: frozenset[str] = frozenset({"intervention", "exposure", "index_test", "phenomenon"})
_OUT_KEYS: frozenset[str] = frozenset({"outcome", "evaluation", "research_type"})
_CMP_KEYS: frozenset[str] = frozenset({"comparison", "comparator", "context", "reference_standard"})


def _terms_from_list(texts: list[str]) -> list[QueryTerm]:
    """Create QueryTerm objects from a list of text strings."""
    return [QueryTerm(text=t) for t in texts if t and t.strip()]


def build_query(criteria: object) -> BooleanQuery:
    """Convert *criteria* (ReviewCriteria or PICOCriteria) to a BooleanQuery.

    The function handles both legacy ``PICOCriteria`` instances and the
    newer framework-agnostic ``ReviewCriteria`` instances.  For
    ``PICOCriteria``, the PICO fields are mapped directly; for
    ``ReviewCriteria``, element keys are matched against the semantic
    role sets defined at module level.

    Args:
        criteria: A ``ReviewCriteria`` or ``PICOCriteria`` instance.

    Returns:
        A ``BooleanQuery`` AST ready for translation.
    """
    # Detect PICOCriteria by duck-typing (avoids circular imports).
    if hasattr(criteria, "population_include"):
        return _build_from_pico(criteria)
    return _build_from_review(criteria)


def _build_from_pico(pico: object) -> BooleanQuery:
    """Build a BooleanQuery directly from a PICOCriteria instance."""
    pop_terms = _terms_from_list(getattr(pico, "population_include", []))
    int_terms = _terms_from_list(getattr(pico, "intervention_include", []))
    out_terms = _terms_from_list(
        list(getattr(pico, "outcome_primary", []))
        + list(getattr(pico, "outcome_secondary", []))
    )
    cmp_terms = _terms_from_list(getattr(pico, "comparison_include", []))

    excl_terms = _terms_from_list(
        list(getattr(pico, "population_exclude", []))
        + list(getattr(pico, "intervention_exclude", []))
        + list(getattr(pico, "study_design_exclude", []))
    )

    return BooleanQuery(
        population=QueryGroup(terms=pop_terms),
        intervention=QueryGroup(terms=int_terms),
        outcome=QueryGroup(terms=out_terms),
        additional=QueryGroup(terms=cmp_terms),
        exclusions=QueryGroup(terms=excl_terms, operator="NOT"),
    )


def _build_from_review(criteria: object) -> BooleanQuery:
    """Build a BooleanQuery from a ReviewCriteria instance.

    Matches PilotSearcher behavior: only **required** elements are used
    (optional elements over-constrain the search). Each group is capped
    at ``_MAX_TERMS_PER_GROUP`` terms to keep queries manageable.
    """
    pop_terms: list[QueryTerm] = []
    int_terms: list[QueryTerm] = []
    out_terms: list[QueryTerm] = []
    cmp_terms: list[QueryTerm] = []
    excl_terms: list[QueryTerm] = []

    # Only use required elements (matches PilotSearcher behavior)
    required_keys: set[str] = set()
    framework = getattr(criteria, "framework", None)
    if framework:
        try:
            from metascreener.criteria.frameworks import FRAMEWORK_ELEMENTS  # noqa: PLC0415

            fw_info = FRAMEWORK_ELEMENTS.get(str(framework), {})
            required_keys = set(fw_info.get("required", []))
        except ImportError:
            pass

    elements: dict = getattr(criteria, "elements", {})
    for key, element in elements.items():
        # Skip optional elements to avoid over-constraining
        if required_keys and key not in required_keys:
            continue

        key_lower = key.lower()
        include_terms = _terms_from_list(getattr(element, "include", []))
        exclude_terms = _terms_from_list(getattr(element, "exclude", []))

        # Cap terms per group (matches PilotSearcher._MAX_TERMS_PER_ELEMENT)
        include_terms = include_terms[:_MAX_TERMS_PER_GROUP]

        if key_lower in _POP_KEYS:
            pop_terms.extend(include_terms)
        elif key_lower in _INT_KEYS:
            int_terms.extend(include_terms)
        elif key_lower in _OUT_KEYS:
            out_terms.extend(include_terms)
        elif key_lower in _CMP_KEYS:
            cmp_terms.extend(include_terms)
        else:
            # Unknown element: fold includes into population as fallback.
            pop_terms.extend(include_terms)

        excl_terms.extend(exclude_terms[:_MAX_TERMS_PER_GROUP])

    # Study-design exclusions from top-level field.
    study_excl = getattr(criteria, "study_design_exclude", [])
    excl_terms.extend(_terms_from_list(list(study_excl)))

    return BooleanQuery(
        population=QueryGroup(terms=pop_terms),
        intervention=QueryGroup(terms=int_terms),
        outcome=QueryGroup(terms=out_terms),
        additional=QueryGroup(terms=cmp_terms),
        exclusions=QueryGroup(terms=excl_terms, operator="NOT"),
    )

_MAX_TERMS_PER_GROUP: int = 8
