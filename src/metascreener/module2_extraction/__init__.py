"""Module 2: Data Extraction.

Public API includes both the legacy YAML-based extraction (v1) and the
new Excel-driven schema-based extraction (v2).
"""

# --- v1 (legacy, retained for backward compatibility) ---
from metascreener.module2_extraction.extractor import ExtractionEngine
from metascreener.module2_extraction.form_schema import (
    ExtractionForm,
    FieldDefinition,
    load_extraction_form,
)
from metascreener.module2_extraction.form_wizard import FormWizard
from metascreener.module2_extraction.validator import (
    ValidationWarning,
    validate_extraction,
)

# --- v2 (new Excel-driven extraction) ---
from metascreener.module2_extraction.compiler import compile_template

__all__ = [
    # v1
    "ExtractionEngine",
    "ExtractionForm",
    "FieldDefinition",
    "FormWizard",
    "ValidationWarning",
    "load_extraction_form",
    "validate_extraction",
    # v2
    "compile_template",
]
