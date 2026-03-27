"""Tests for terminology standardization."""
from __future__ import annotations

from metascreener.module2_extraction.plugins.models import TerminologyEntry
from metascreener.module2_extraction.plugins.terminology import TerminologyEngine


class TestTerminologyEngine:
    """Tests for the TerminologyEngine class."""

    def _make_engine(self) -> TerminologyEngine:
        """Create an engine with standard test entries.

        Returns:
            TerminologyEngine initialized with test terminology entries.
        """
        entries = [
            TerminologyEntry(
                canonical="Benzylpenicillin",
                aliases=["Pen G", "Penicillin G", "PCN", "penicillin"],
                metadata={
                    "drug_class": "Penicillins",
                    "aware_category": "Access",
                },
            ),
            TerminologyEntry(
                canonical="Amoxicillin + clavulanic acid",
                aliases=["Amox/Clav", "Augmentin", "Co-amoxiclav"],
                metadata={
                    "drug_class": "Beta-lactam/BLI",
                    "aware_category": "Access",
                },
            ),
        ]
        return TerminologyEngine(entries)

    def test_exact_match(self) -> None:
        """Test exact match on canonical term."""
        assert self._make_engine().standardize("Benzylpenicillin") == "Benzylpenicillin"

    def test_alias_match(self) -> None:
        """Test matching of aliases to canonical forms."""
        e = self._make_engine()
        assert e.standardize("Pen G") == "Benzylpenicillin"
        assert e.standardize("Augmentin") == "Amoxicillin + clavulanic acid"

    def test_case_insensitive(self) -> None:
        """Test case-insensitive matching."""
        e = self._make_engine()
        assert e.standardize("pen g") == "Benzylpenicillin"
        assert e.standardize("PENICILLIN") == "Benzylpenicillin"

    def test_no_match_returns_original(self) -> None:
        """Test that unknown terms are returned unchanged."""
        assert self._make_engine().standardize("UnknownDrug") == "UnknownDrug"

    def test_get_metadata(self) -> None:
        """Test metadata retrieval via alias lookup."""
        meta = self._make_engine().get_metadata("Pen G")
        assert meta is not None
        assert meta["drug_class"] == "Penicillins"

    def test_get_metadata_no_match(self) -> None:
        """Test metadata retrieval for non-existent term."""
        assert self._make_engine().get_metadata("UnknownDrug") is None

    def test_standardize_row(self) -> None:
        """Test row standardization with field name specification."""
        row = {"antibiotic": "Augmentin", "n_tested": 100}
        result = self._make_engine().standardize_row(
            row, field_names=["antibiotic"]
        )
        assert result["antibiotic"] == "Amoxicillin + clavulanic acid"
        assert result["n_tested"] == 100

    def test_empty_engine(self) -> None:
        """Test behavior of engine with no entries."""
        assert TerminologyEngine([]).standardize("anything") == "anything"
