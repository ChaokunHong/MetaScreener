"""Unit tests for BooleanQuery → provider-native query translators."""
from __future__ import annotations

from metascreener.module0_retrieval.models import BooleanQuery, QueryGroup, QueryTerm


def _sample_query() -> BooleanQuery:
    return BooleanQuery(
        population=QueryGroup(
            terms=[
                QueryTerm(text="diabetes", mesh=True),
                QueryTerm(text="type 2 diabetes", phrase=True),
            ]
        ),
        intervention=QueryGroup(terms=[QueryTerm(text="metformin", mesh=True)]),
        outcome=QueryGroup(terms=[QueryTerm(text="mortality")]),
        exclusions=QueryGroup(terms=[QueryTerm(text="animal")], operator="NOT"),
    )


def test_translate_pubmed():
    from metascreener.module0_retrieval.query.ast import translate_pubmed

    result = translate_pubmed(_sample_query())
    assert "diabetes[MeSH Terms]" in result
    assert '"type 2 diabetes"' in result
    assert "NOT" in result


def test_translate_pubmed_wildcard():
    from metascreener.module0_retrieval.query.ast import translate_pubmed

    q = BooleanQuery(population=QueryGroup(terms=[QueryTerm(text="transmissi", wildcard=True)]))
    result = translate_pubmed(q)
    assert "transmissi*" in result


def test_translate_openalex():
    from metascreener.module0_retrieval.query.ast import translate_openalex

    result = translate_openalex(_sample_query())
    assert "diabetes" in result
    assert "metformin" in result


def test_translate_europepmc():
    from metascreener.module0_retrieval.query.ast import translate_europepmc

    result = translate_europepmc(_sample_query())
    assert "diabetes" in result
    assert "NOT" in result


def test_translate_scopus():
    from metascreener.module0_retrieval.query.ast import translate_scopus

    result = translate_scopus(_sample_query())
    assert "TITLE-ABS-KEY" in result


def test_translate_empty_query():
    from metascreener.module0_retrieval.query.ast import translate_pubmed

    assert translate_pubmed(BooleanQuery()) == ""
