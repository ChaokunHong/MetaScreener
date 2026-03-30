"""Step 2: Infer cross-sheet relationships and classify sheet roles."""

from __future__ import annotations

import structlog

from metascreener.core.models_extraction import SheetRelation
from metascreener.module2_extraction.compiler.scanner import RawSheetInfo

log = structlog.get_logger()

_DOCUMENTATION_KEYWORDS = {
    "dictionary", "guide", "instruction", "readme", "help", "notes", "changelog",
    "filling_guide", "data_dictionary", "how_to",
    "draft", "scratch", "temp", "test", "archive", "old", "backup",
}

_MAPPING_KEYWORDS = {
    "mapping", "mappings", "lookup", "reference_list", "reference_lists",
    "codebook", "codes",
}

def infer_sheet_roles(sheets: list[RawSheetInfo]) -> dict[str, str]:
    """Classify each sheet as data / mapping / reference / documentation.

    Args:
        sheets: List of raw sheet metadata from the scanner.

    Returns:
        Mapping of sheet_name → role string.
    """
    roles: dict[str, str] = {}
    for sheet in sheets:
        name_lower = sheet.sheet_name.lower().replace(" ", "_")
        if any(kw in name_lower for kw in _DOCUMENTATION_KEYWORDS):
            roles[sheet.sheet_name] = "documentation"
            continue
        if any(kw in name_lower for kw in _MAPPING_KEYWORDS):
            roles[sheet.sheet_name] = "mapping"
            continue
        has_formulas = any(f.has_formula for f in sheet.fields)
        has_dropdowns = any(f.dropdown_options for f in sheet.fields)
        n_cols = len(sheet.fields)
        if n_cols <= 5 and not has_formulas and not has_dropdowns and sheet.row_count > 10:
            roles[sheet.sheet_name] = "mapping"
            continue
        roles[sheet.sheet_name] = "data"
    log.info("sheet_roles_inferred", roles=roles)
    return roles

def infer_relationships(sheets: list[RawSheetInfo]) -> list[SheetRelation]:
    """Detect cross-sheet foreign key relationships.

    Identifies shared column names that look like keys (containing "id",
    "key", or "row") and uses formula presence and row counts to determine
    parent/child direction.

    Args:
        sheets: List of raw sheet metadata from the scanner.

    Returns:
        List of inferred SheetRelation objects.
    """
    col_names: dict[str, set[str]] = {}
    formula_cols: dict[str, set[str]] = {}
    for sheet in sheets:
        col_names[sheet.sheet_name] = {f.name for f in sheet.fields}
        formula_cols[sheet.sheet_name] = {f.name for f in sheet.fields if f.has_formula}

    all_sheet_names = list(col_names.keys())
    relations: list[SheetRelation] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, sheet_a_name in enumerate(all_sheet_names):
        for sheet_b_name in all_sheet_names[i + 1:]:
            shared = col_names[sheet_a_name] & col_names[sheet_b_name]
            fk_candidates = [
                c for c in shared
                if "id" in c.lower() or "key" in c.lower() or "row" in c.lower()
            ]
            for fk_col in fk_candidates:
                a_is_formula = fk_col in formula_cols[sheet_a_name]
                b_is_formula = fk_col in formula_cols[sheet_b_name]
                if a_is_formula and not b_is_formula:
                    parent, child = sheet_a_name, sheet_b_name
                elif b_is_formula and not a_is_formula:
                    parent, child = sheet_b_name, sheet_a_name
                else:
                    sheet_a = next(s for s in sheets if s.sheet_name == sheet_a_name)
                    sheet_b = next(s for s in sheets if s.sheet_name == sheet_b_name)
                    if sheet_a.row_count <= sheet_b.row_count:
                        parent, child = sheet_a_name, sheet_b_name
                    else:
                        parent, child = sheet_b_name, sheet_a_name
                pair = (parent, child)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    relations.append(
                        SheetRelation(
                            parent_sheet=parent,
                            child_sheet=child,
                            foreign_key=fk_col,
                            cardinality="1:N",
                        )
                    )
    log.info("relationships_inferred", count=len(relations))
    return relations
