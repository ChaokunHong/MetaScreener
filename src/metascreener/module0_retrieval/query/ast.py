"""Translate a BooleanQuery AST to provider-native query strings.

Supported providers
-------------------
- PubMed     : MeSH tags, quoted phrases, wildcards, NOT exclusions
- OpenAlex   : Plain text, quoted multi-word phrases, AND/OR/NOT
- EuropePMC  : Similar to PubMed (MeSH not supported; quoted phrases, NOT)
- Scopus     : TITLE-ABS-KEY() wrapper per group, AND/OR/NOT

Each translator follows the same pattern:

    1. Render terms within each non-empty group (OR-joined).
    2. Collect rendered group strings (AND-joined).
    3. Append NOT exclusion block.
    4. Return the final query string (empty string if no terms exist).
"""
from __future__ import annotations

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm


def truncate_query(query: BooleanQuery, max_terms_per_group: int = 8) -> BooleanQuery:
    """Truncate a query to fit APIs with query length limits.

    Keeps the first ``max_terms_per_group`` terms per group. This
    preserves the most important terms (typically placed first by the
    builder) while avoiding API timeouts from overly long queries.

    Args:
        query: Original boolean query.
        max_terms_per_group: Maximum terms to keep per group.

    Returns:
        A truncated copy of the query.
    """

    def _trunc(group: QueryGroup) -> QueryGroup:
        if len(group.terms) <= max_terms_per_group:
            return group
        return QueryGroup(
            terms=group.terms[:max_terms_per_group],
            operator=group.operator,
        )

    return BooleanQuery(
        population=_trunc(query.population),
        intervention=_trunc(query.intervention),
        outcome=_trunc(query.outcome),
        additional=_trunc(query.additional),
        exclusions=_trunc(query.exclusions),
    )


def _render_term_pubmed(term: QueryTerm) -> str:
    """Render a single term in PubMed syntax.

    Multi-word terms are left **unquoted** by default so that PubMed's
    Automatic Term Mapping (ATM) can expand them to MeSH synonyms.
    This dramatically increases recall vs exact-phrase matching.
    Only explicitly marked ``phrase=True`` terms are quoted.
    """
    text = term.text.strip()
    if term.wildcard:
        return f"{text}*"
    if term.mesh:
        return f"{text}[MeSH Terms]"
    if term.phrase:
        return f'"{text}"'
    # No quotes — let PubMed ATM auto-expand (matches PilotSearcher behavior)
    return text


def _render_term_plain(term: QueryTerm) -> str:
    """Render a term without database-specific modifiers (plain text)."""
    text = term.text.strip()
    if " " in text:
        return f'"{text}"'
    return text


def _render_term_europepmc(term: QueryTerm) -> str:
    """Render a single term in Europe PMC syntax (phrases quoted, no MeSH)."""
    text = term.text.strip()
    if term.wildcard:
        return f"{text}*"
    if term.phrase or " " in text:
        return f'"{text}"'
    return text


def _group_to_str_pubmed(group: QueryGroup) -> str:
    """Render a QueryGroup to a PubMed OR-block."""
    rendered = [_render_term_pubmed(t) for t in group.terms]
    return " OR ".join(rendered)


def _group_to_str_plain(group: QueryGroup) -> str:
    """Render a QueryGroup to a plain OR-block (OpenAlex style)."""
    rendered = [_render_term_plain(t) for t in group.terms]
    return " OR ".join(rendered)


def _group_to_str_europepmc(group: QueryGroup) -> str:
    """Render a QueryGroup to a Europe PMC OR-block."""
    rendered = [_render_term_europepmc(t) for t in group.terms]
    return " OR ".join(rendered)


def _active_content_groups(query: BooleanQuery) -> list[QueryGroup]:
    """Return the content groups (population, intervention, outcome, additional)."""
    return [query.population, query.intervention, query.outcome, query.additional]


def _has_terms(query: BooleanQuery) -> bool:
    """Return True if the query has any non-exclusion terms."""
    return any(g.terms for g in _active_content_groups(query))


def translate_pubmed(query: BooleanQuery) -> str:
    """Translate a BooleanQuery to a PubMed search string.

    Features: MeSH tags ([MeSH Terms]), quoted phrases, wildcard (*), NOT block.

    Args:
        query: The database-agnostic BooleanQuery AST.

    Returns:
        A PubMed-compatible search string, or ``""`` if no terms are present.
    """
    if not _has_terms(query) and not query.exclusions.terms:
        return ""

    parts: list[str] = []
    for group in _active_content_groups(query):
        if group.terms:
            block = _group_to_str_pubmed(group)
            parts.append(f"({block})" if " OR " in block else block)

    result = " AND ".join(parts)

    if query.exclusions.terms:
        not_block = _group_to_str_pubmed(query.exclusions)
        not_part = f"({not_block})" if " OR " in not_block else not_block
        result = f"{result} NOT {not_part}" if result else f"NOT {not_part}"

    return result


def translate_openalex(query: BooleanQuery) -> str:
    """Translate a BooleanQuery to an OpenAlex search string.

    OpenAlex does not support MeSH or wildcards.  Multi-word terms are quoted.

    Args:
        query: The database-agnostic BooleanQuery AST.

    Returns:
        An OpenAlex-compatible search string, or ``""`` if no terms are present.
    """
    if not _has_terms(query) and not query.exclusions.terms:
        return ""

    parts: list[str] = []
    for group in _active_content_groups(query):
        if group.terms:
            block = _group_to_str_plain(group)
            parts.append(f"({block})" if " OR " in block else block)

    result = " AND ".join(parts)

    if query.exclusions.terms:
        not_block = _group_to_str_plain(query.exclusions)
        not_part = f"({not_block})" if " OR " in not_block else not_block
        result = f"{result} NOT {not_part}" if result else f"NOT {not_part}"

    return result


def translate_europepmc(query: BooleanQuery) -> str:
    """Translate a BooleanQuery to a Europe PMC search string.

    Similar to PubMed syntax but without MeSH tags.  Phrases are quoted,
    wildcards are appended with *.

    Args:
        query: The database-agnostic BooleanQuery AST.

    Returns:
        A Europe PMC-compatible search string, or ``""`` if no terms are present.
    """
    if not _has_terms(query) and not query.exclusions.terms:
        return ""

    parts: list[str] = []
    for group in _active_content_groups(query):
        if group.terms:
            block = _group_to_str_europepmc(group)
            parts.append(f"({block})" if " OR " in block else block)

    result = " AND ".join(parts)

    if query.exclusions.terms:
        not_block = _group_to_str_europepmc(query.exclusions)
        not_part = f"({not_block})" if " OR " in not_block else not_block
        result = f"{result} NOT {not_part}" if result else f"NOT {not_part}"

    return result


def translate_scopus(query: BooleanQuery) -> str:
    """Translate a BooleanQuery to a Scopus search string.

    Each non-empty group is wrapped in TITLE-ABS-KEY(...).  Groups are
    AND-joined.  Exclusions are appended with AND NOT TITLE-ABS-KEY(...).

    Args:
        query: The database-agnostic BooleanQuery AST.

    Returns:
        A Scopus-compatible search string, or ``""`` if no terms are present.
    """
    if not _has_terms(query) and not query.exclusions.terms:
        return ""

    parts: list[str] = []
    for group in _active_content_groups(query):
        if group.terms:
            inner = _group_to_str_plain(group)
            parts.append(f"TITLE-ABS-KEY({inner})")

    result = " AND ".join(parts)

    if query.exclusions.terms:
        not_inner = _group_to_str_plain(query.exclusions)
        result = (
            f"{result} AND NOT TITLE-ABS-KEY({not_inner})"
            if result
            else f"NOT TITLE-ABS-KEY({not_inner})"
        )

    return result
