"""Step 3: AI-enhanced field understanding.

Uses an LLM to semantically classify fields and generate descriptions.
Falls back to heuristic classification when LLM is unavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from metascreener.core.enums import FieldRole
from metascreener.module2_extraction.compiler.scanner import RawSheetInfo

if TYPE_CHECKING:
    from metascreener.llm.base import BaseLLMBackend

log = structlog.get_logger()

_VALID_ROLES = {r.value for r in FieldRole}

_ENHANCE_PROMPT = """\
You are analyzing an Excel template for systematic review data extraction.

Sheet name: {sheet_name}
Columns (name | detected_type | has_formula | has_dropdown):
{field_table}

Sample data (first rows):
{sample_data}

For each column, determine:
1. "role": one of "extract" (LLM must fill from PDF), "auto_calc" (formula, \
do not touch), "lookup" (filled from mapping table), "override" (hidden, \
special cases), "metadata" (like extractor initials, dates), "qc_flag" \
(auto quality check)
2. "description": one-sentence description of what this field captures
3. "required": true/false — is this field essential for the review?

Also determine the sheet's "cardinality": "one_per_study" (one row per paper) \
or "many_per_study" (multiple rows per paper, e.g. one row per pathogen).

Return ONLY valid JSON:
{{
  "fields": [
    {{"name": "...", "role": "...", "description": "...", "required": true/false}},
    ...
  ],
  "cardinality": "one_per_study" | "many_per_study"
}}"""


@dataclass
class FieldEnhancement:
    """AI-enhanced understanding of a field."""

    role: FieldRole
    description: str
    required: bool


@dataclass
class SheetEnhancement:
    """AI-enhanced understanding of a sheet."""

    fields: dict[str, FieldEnhancement] = field(default_factory=dict)
    cardinality: str = "one_per_study"


def _build_prompt(sheet: RawSheetInfo) -> str:
    """Build the enhancement prompt for a sheet."""
    rows = []
    for f in sheet.fields:
        dropdown = f"options={f.dropdown_options}" if f.dropdown_options else "no"
        rows.append(f"  {f.name} | {f.inferred_type} | formula={f.has_formula} | {dropdown}")
    field_table = "\n".join(rows)

    sample_lines = []
    for f in sheet.fields:
        if f.sample_values:
            vals = ", ".join(str(v) for v in f.sample_values[:3])
            sample_lines.append(f"  {f.name}: {vals}")
    sample_data = "\n".join(sample_lines) if sample_lines else "  (no sample data)"

    return _ENHANCE_PROMPT.format(
        sheet_name=sheet.sheet_name,
        field_table=field_table,
        sample_data=sample_data,
    )


def _heuristic_role(f_info: RawSheetInfo | object) -> FieldRole:
    """Fallback heuristic when AI is unavailable."""
    if hasattr(f_info, "has_formula") and f_info.has_formula:  # noqa: ARG001
        return FieldRole.AUTO_CALC
    name = getattr(f_info, "name", "")
    name_lower = str(name).lower()
    if "flag" in name_lower or "qc" in name_lower:
        return FieldRole.QC_FLAG
    if "override" in name_lower:
        return FieldRole.OVERRIDE
    if name_lower in {"extractor_initials", "verifier_initials", "extraction_date"}:
        return FieldRole.METADATA
    return FieldRole.EXTRACT


def _heuristic_required(name: str) -> bool:
    """Heuristic: only key identifier fields are required."""
    name_lower = name.lower()
    # Only a few core fields should be required by default
    required_patterns = {
        "first_author", "publication_year", "study_design", "country",
        "pathogen_species", "antibiotic", "n_tested", "n_resistant",
        "risk_factor", "effect_measure", "effect_value",
    }
    return name_lower in required_patterns


def _heuristic_cardinality(sheet: RawSheetInfo) -> str:
    """Heuristic: guess cardinality from sheet name and row count."""
    name_lower = sheet.sheet_name.lower().replace(" ", "_")
    # Sheets with these patterns typically have multiple rows per study
    many_patterns = [
        "resistance", "pathogen", "molecular", "risk_factor",
        "outcome", "antibiotic", "isolate", "specimen",
    ]
    if any(p in name_lower for p in many_patterns):
        return "many_per_study"
    # If row count is much higher than typical single-study sheets
    if sheet.row_count > 200:
        return "many_per_study"
    return "one_per_study"


def _heuristic_enhancement(sheet: RawSheetInfo) -> SheetEnhancement:
    """Pure heuristic enhancement — no LLM needed."""
    fields: dict[str, FieldEnhancement] = {}
    for f in sheet.fields:
        role = _heuristic_role(f)
        fields[f.name] = FieldEnhancement(
            role=role,
            description=f.name.replace("_", " "),
            required=_heuristic_required(f.name) if role == FieldRole.EXTRACT else False,
        )
    cardinality = _heuristic_cardinality(sheet)
    return SheetEnhancement(fields=fields, cardinality=cardinality)


def parse_enhancement_response(
    raw: dict[str, Any],
    sheet: RawSheetInfo,
) -> SheetEnhancement:
    """Parse LLM response into SheetEnhancement, with heuristic fallback."""
    known_names = {f.name for f in sheet.fields}
    field_map = {f.name: f for f in sheet.fields}
    fields: dict[str, FieldEnhancement] = {}

    for item in raw.get("fields", []):
        name = item.get("name", "")
        if name not in known_names:
            continue
        role_str = item.get("role", "")
        if role_str in _VALID_ROLES:
            role = FieldRole(role_str)
        else:
            role = _heuristic_role(field_map[name])
        fields[name] = FieldEnhancement(
            role=role,
            description=item.get("description", name.replace("_", " ")),
            required=bool(item.get("required", False)),
        )

    cardinality = raw.get("cardinality", "one_per_study")
    if cardinality not in {"one_per_study", "many_per_study"}:
        cardinality = "one_per_study"

    return SheetEnhancement(fields=fields, cardinality=cardinality)


async def enhance_fields(
    sheet: RawSheetInfo,
    *,
    backend: BaseLLMBackend | None = None,
    data_dictionary: dict[str, str] | None = None,
) -> SheetEnhancement:
    """Enhance field understanding using LLM, with heuristic fallback.

    Args:
        sheet: Raw sheet info from the scanner.
        backend: LLM backend with an async ``generate`` method.
        data_dictionary: Optional mapping of field names to known descriptions.

    Returns:
        SheetEnhancement with per-field roles, descriptions, and cardinality.
    """
    if backend is None:
        return _heuristic_enhancement(sheet)

    prompt = _build_prompt(sheet)
    try:
        raw_response = await backend.generate(prompt)
        parsed = json.loads(raw_response)
        enhancement = parse_enhancement_response(parsed, sheet)
        # Fill any fields the LLM missed with heuristics
        for f in sheet.fields:
            if f.name not in enhancement.fields:
                enhancement.fields[f.name] = FieldEnhancement(
                    role=_heuristic_role(f),
                    description=f.name.replace("_", " "),
                    required=False,
                )
        log.info(
            "ai_enhancement_succeeded",
            sheet=sheet.sheet_name,
            fields_enhanced=len(enhancement.fields),
        )
        return enhancement
    except Exception:
        log.warning(
            "ai_enhancement_failed_using_heuristics",
            sheet=sheet.sheet_name,
            exc_info=True,
        )
        return _heuristic_enhancement(sheet)
